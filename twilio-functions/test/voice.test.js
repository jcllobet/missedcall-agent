const assert = require("node:assert/strict");
const test = require("node:test");

global.Twilio = {
  twiml: {
    VoiceResponse: class VoiceResponse {
      constructor() {
        this.parts = [];
      }

      say(text) {
        this.parts.push(`<Say>${text}</Say>`);
      }

      pause(attrs) {
        this.parts.push(`<Pause${attrsString(attrs)}/>`);
      }

      hangup() {
        this.parts.push("<Hangup/>");
      }

      leave() {
        this.parts.push("<Leave/>");
      }

      gather(attrs) {
        const gather = new Gather(attrs);
        this.parts.push(gather);
        return gather;
      }

      dial(attrs) {
        const dial = new Dial(attrs);
        this.parts.push(dial);
        return dial;
      }

      enqueue(attrs, value) {
        this.parts.push(`<Enqueue${attrsString(attrs)}>${value}</Enqueue>`);
      }

      connect() {
        const connect = new Connect();
        this.parts.push(connect);
        return connect;
      }

      toString() {
        return `<Response>${this.parts.map(String).join("")}</Response>`;
      }
    },
  },
};

class Gather {
  constructor(attrs) {
    this.attrs = attrs;
    this.parts = [];
  }

  say(text) {
    this.parts.push(`<Say>${text}</Say>`);
  }

  toString() {
    return `<Gather${attrsString(this.attrs)}>${this.parts.join("")}</Gather>`;
  }
}

class Dial {
  constructor(attrs) {
    this.attrs = attrs;
    this.parts = [];
  }

  queue(value) {
    this.parts.push(`<Queue>${value}</Queue>`);
  }

  toString() {
    return `<Dial${attrsString(this.attrs)}>${this.parts.join("")}</Dial>`;
  }
}

class Connect {
  constructor() {
    this.parts = [];
  }

  stream(attrs) {
    const stream = new Stream(attrs);
    this.parts.push(stream);
    return stream;
  }

  toString() {
    return `<Connect>${this.parts.map(String).join("")}</Connect>`;
  }
}

class Stream {
  constructor(attrs) {
    this.attrs = attrs;
    this.parts = [];
  }

  parameter(attrs) {
    this.parts.push(`<Parameter${attrsString(attrs)}/>`);
  }

  toString() {
    return `<Stream${attrsString(this.attrs)}>${this.parts.join("")}</Stream>`;
  }
}

function attrsString(values = {}) {
  return Object.entries(values)
    .map(([key, value]) => ` ${key}="${value}"`)
    .join("");
}

const { handler } = require("../functions/voice");

function makeContext(overrides = {}) {
  const createdCalls = [];
  const updatedCalls = [];
  const calls = (sid) => ({
    update: async (payload) => {
      updatedCalls.push({ sid, payload });
      return {};
    },
  });
  calls.create = async (payload) => {
    createdCalls.push(payload);
    return {};
  };

  return {
    context: {
      DOMAIN_NAME: "example-123.twil.io",
      PIPECAT_CLOUD_SERVICE_HOST: "jan-ai-voicemail.jan-agent-swarm",
      PIPECAT_CLOUD_WS_URL: "wss://api.pipecat.daily.co/ws/twilio",
      TWILIO_PHONE_NUMBER: "+15550000000",
      JAN_PHONE_NUMBER: "+15551111111",
      getTwilioClient: () => ({ calls }),
      ...overrides,
    },
    createdCalls,
    updatedCalls,
  };
}

function invoke(event, overrides) {
  const state = makeContext(overrides);
  return new Promise((resolve, reject) => {
    handler(state.context, event, (error, response) => {
      if (error) {
        reject(error);
        return;
      }
      resolve({ twiml: String(response), ...state });
    });
  });
}

test("initial call parks caller in queue and starts separate Jan screening call", async () => {
  const { twiml, createdCalls } = await invoke({
    CallSid: "CA_inbound",
    From: "+15552222222",
  });

  assert.match(twiml, /<Enqueue action="\/voice\?queue_result=1"/);
  assert.match(twiml, /waitUrl="\/voice\?wait=1"/);
  assert.match(twiml, /jan_CA_inbound/);
  assert.equal(createdCalls.length, 1);
  assert.equal(createdCalls[0].to, "+15551111111");
  assert.equal(createdCalls[0].from, "+15550000000");
  assert.match(createdCalls[0].url, /\/voice\?screen=prompt/);
  assert.match(createdCalls[0].url, /queue=jan_CA_inbound/);
  assert.match(createdCalls[0].statusCallback, /\/voice\?jan_call_status=1/);
  assert.deepEqual(createdCalls[0].statusCallbackEvent, ["completed"]);
  assert.equal(createdCalls[0].machineDetection, "Enable");
  assert.equal(createdCalls[0].asyncAmd, true);
  assert.match(createdCalls[0].asyncAmdStatusCallback, /\/voice\?amd_status=1/);
});

test("Jan screening prompt gathers one digit without bridging the caller", async () => {
  const { twiml } = await invoke({
    screen: "prompt",
    queue: "jan_CA_inbound",
    caller: "CA_inbound",
  });

  assert.match(twiml, /<Gather/);
  assert.match(twiml, /actionOnEmptyResult="true"/);
  assert.match(twiml, /Press 1 to accept/);
  assert.match(twiml, /<Hangup\/>/);
  assert.doesNotMatch(twiml, /<Queue>/);
});

test("pressing one dequeues caller into Jan call", async () => {
  const { twiml } = await invoke({
    screen: "result",
    queue: "jan_CA_inbound",
    caller: "CA_inbound",
    Digits: "1",
  });

  assert.match(twiml, /Connecting/);
  assert.match(twiml, /<Dial/);
  assert.match(twiml, /<Queue>jan_CA_inbound<\/Queue>/);
});

[
  ["no keypress", {}],
  ["wrong digit", { Digits: "2" }],
].forEach(([name, digitEvent]) => {
  test(`${name} redirects queued caller to AI and hangs up Jan leg`, async () => {
    const { twiml, updatedCalls } = await invoke({
      screen: "result",
      queue: "jan_CA_inbound",
      caller: "CA_inbound",
      ...digitEvent,
    });

    assert.match(twiml, /<Hangup\/>/);
    assert.equal(updatedCalls.length, 1);
    assert.equal(updatedCalls[0].sid, "CA_inbound");
    assert.match(updatedCalls[0].payload.url, /force_ai=1/);
    assert.match(updatedCalls[0].payload.url, /jan_not_accepted/);
  });
});

test("queue wait timeout leaves queue so action can route to AI", async () => {
  const { twiml } = await invoke({
    wait: "1",
    QueueTime: "10",
  });

  assert.match(twiml, /<Leave\/>/);
});

[
  ["person does not pick up", "no-answer", "jan_no_answer"],
  ["person rejects call", "busy", "jan_busy"],
  ["phone is in airplane mode or unreachable", "failed", "jan_failed"],
  ["carrier cancels the Jan leg", "canceled", "jan_canceled"],
].forEach(([name, callStatus, reason]) => {
  test(`${name} redirects queued caller to AI`, async () => {
    const { twiml, updatedCalls } = await invoke({
      jan_call_status: "1",
      queue: "jan_CA_inbound",
      caller: "CA_inbound",
      CallStatus: callStatus,
    });

    assert.equal(twiml, "<Response></Response>");
    assert.equal(updatedCalls.length, 1);
    assert.equal(updatedCalls[0].sid, "CA_inbound");
    assert.match(updatedCalls[0].payload.url, /force_ai=1/);
    assert.match(updatedCalls[0].payload.url, new RegExp(reason));
  });
});

test("completed Jan screening call status does not redirect by itself", async () => {
  const { twiml, updatedCalls } = await invoke({
    jan_call_status: "1",
    queue: "jan_CA_inbound",
    caller: "CA_inbound",
    CallStatus: "completed",
  });

  assert.equal(twiml, "<Response></Response>");
  assert.equal(updatedCalls.length, 0);
});

[
  ["voicemail greeting start", "machine_start", "jan_machine_start"],
  ["voicemail beep", "machine_end_beep", "jan_machine_end_beep"],
  ["voicemail silence", "machine_end_silence", "jan_machine_end_silence"],
  ["voicemail other ending", "machine_end_other", "jan_machine_end_other"],
  ["fax", "fax", "jan_fax"],
  ["unknown non-human", "unknown", "jan_unknown"],
].forEach(([name, answeredBy, reason]) => {
  test(`AMD ${name} redirects queued caller to AI`, async () => {
    const { twiml, updatedCalls } = await invoke({
      amd_status: "1",
      queue: "jan_CA_inbound",
      caller: "CA_inbound",
      AnsweredBy: answeredBy,
    });

    assert.equal(twiml, "<Response></Response>");
    assert.equal(updatedCalls.length, 1);
    assert.equal(updatedCalls[0].sid, "CA_inbound");
    assert.match(updatedCalls[0].payload.url, /force_ai=1/);
    assert.match(updatedCalls[0].payload.url, new RegExp(reason));
  });
});

test("AMD human result does not redirect queued caller", async () => {
  const { twiml, updatedCalls } = await invoke({
    amd_status: "1",
    queue: "jan_CA_inbound",
    caller: "CA_inbound",
    AnsweredBy: "human",
  });

  assert.equal(twiml, "<Response></Response>");
  assert.equal(updatedCalls.length, 0);
});

test("queue result that was not bridged streams caller to Pipecat", async () => {
  const { twiml } = await invoke({
    queue_result: "1",
    QueueResult: "leave",
    From: "+15552222222",
    CallSid: "CA_inbound",
  });

  assert.match(twiml, /<Connect><Stream url="wss:\/\/api\.pipecat\.daily\.co\/ws\/twilio">/);
  assert.match(twiml, /name="fallback_reason" value="queue_leave"/);
});

test("force-ai redirect streams caller to Pipecat", async () => {
  const { twiml } = await invoke({
    force_ai: "1",
    fallback_reason: "jan_not_accepted",
    CallSid: "CA_inbound",
  });

  assert.match(twiml, /<Connect><Stream/);
  assert.match(twiml, /name="fallback_reason" value="jan_not_accepted"/);
});
