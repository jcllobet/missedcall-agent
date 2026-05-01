function absoluteUrl(context, path) {
  const baseUrl = context.PUBLIC_BASE_URL || `https://${context.DOMAIN_NAME}`;
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

function voicePath(params) {
  return `/voice?${new URLSearchParams(params).toString()}`;
}

function voiceUrl(context, params) {
  return absoluteUrl(context, voicePath(params));
}

function queueName(callSid) {
  return `jan_${String(callSid || Date.now()).replace(/[^a-zA-Z0-9_]/g, "_")}`.slice(0, 64);
}

const FAILED_JAN_STATUSES = new Set(["busy", "failed", "no-answer", "canceled"]);

function aiStream(twiml, context, event, fallbackReason) {
  const connect = twiml.connect();
  const stream = connect.stream({
    url: context.PIPECAT_CLOUD_WS_URL || "wss://api.pipecat.daily.co/ws/twilio",
  });
  stream.parameter({
    name: "_pipecatCloudServiceHost",
    value: context.PIPECAT_CLOUD_SERVICE_HOST,
  });
  stream.parameter({ name: "fallback_reason", value: fallbackReason });
  stream.parameter({ name: "caller", value: event.From || "" });
  stream.parameter({ name: "inbound_call_sid", value: event.CallSid || event.caller || "" });
  stream.parameter({ name: "dial_call_sid", value: event.DialCallSid || "" });
}

async function redirectCallerToAi(context, callerSid, fallbackReason) {
  if (!callerSid || !context.getTwilioClient) {
    return;
  }

  const client = context.getTwilioClient();
  await client.calls(callerSid).update({
    url: voiceUrl(context, { force_ai: "1", fallback_reason: fallbackReason }),
    method: "POST",
  });
}

exports.handler = async function handler(context, event, callback) {
  const twiml = new Twilio.twiml.VoiceResponse();

  try {
    if (event.force_ai === "1") {
      aiStream(twiml, context, event, event.fallback_reason || "jan_not_accepted");
      return callback(null, twiml);
    }

    if (event.jan_call_status === "1") {
      const callStatus = String(event.CallStatus || "").toLowerCase();
      if (FAILED_JAN_STATUSES.has(callStatus)) {
        await redirectCallerToAi(context, event.caller, `jan_${callStatus.replace(/-/g, "_")}`);
      }
      return callback(null, twiml);
    }

    if (event.amd_status === "1") {
      const answeredBy = String(event.AnsweredBy || "").toLowerCase();
      if (answeredBy && answeredBy !== "human") {
        await redirectCallerToAi(context, event.caller, `jan_${answeredBy}`);
      }
      return callback(null, twiml);
    }

    if (event.wait === "1") {
      const maxWaitSeconds = Number.parseInt(
        context.AI_FAILSAFE_WAIT_SECONDS || context.HUMAN_RING_TIMEOUT_SECONDS || "10",
        10,
      );
      const queueTime = Number.parseInt(event.QueueTime || "0", 10);

      if (queueTime >= maxWaitSeconds) {
        twiml.leave();
        return callback(null, twiml);
      }

      twiml.say("Trying Jan now.");
      twiml.pause({ length: 5 });
      return callback(null, twiml);
    }

    if (event.QueueResult || event.queue_result === "1") {
      if (event.QueueResult === "bridged") {
        twiml.hangup();
        return callback(null, twiml);
      }

      aiStream(twiml, context, event, `queue_${event.QueueResult || "timeout"}`);
      return callback(null, twiml);
    }

    if (event.screen === "prompt") {
      const gather = twiml.gather({
        action: voicePath({
          screen: "result",
          queue: event.queue || "",
          caller: event.caller || "",
        }),
        method: "POST",
        numDigits: 1,
        timeout: 6,
        input: "dtmf",
        actionOnEmptyResult: true,
      });
      gather.say("Call for Jan. Press 1 to accept.");
      twiml.hangup();
      return callback(null, twiml);
    }

    if (event.screen === "result") {
      if (event.Digits === "1") {
        twiml.say("Connecting.");
        const dial = twiml.dial({
          timeout: 5,
          action: voicePath({ agent_done: "1", queue: event.queue || "" }),
          method: "POST",
        });
        dial.queue(event.queue);
        return callback(null, twiml);
      }

      await redirectCallerToAi(context, event.caller, "jan_not_accepted");
      twiml.hangup();
      return callback(null, twiml);
    }

    const callerSid = event.CallSid;
    const queue = queueName(callerSid);
    const client = context.getTwilioClient();
    await client.calls.create({
      to: context.JAN_PHONE_NUMBER,
      from: context.TWILIO_PHONE_NUMBER,
      url: voiceUrl(context, { screen: "prompt", queue, caller: callerSid || "" }),
      method: "POST",
      timeout: Number.parseInt(context.HUMAN_RING_TIMEOUT_SECONDS || "10", 10),
      statusCallback: voiceUrl(context, { jan_call_status: "1", queue, caller: callerSid || "" }),
      statusCallbackMethod: "POST",
      statusCallbackEvent: ["completed"],
      machineDetection: "Enable",
      asyncAmd: true,
      asyncAmdStatusCallback: voiceUrl(context, { amd_status: "1", queue, caller: callerSid || "" }),
      asyncAmdStatusCallbackMethod: "POST",
    });

    twiml.enqueue(
      {
        action: "/voice?queue_result=1",
        method: "POST",
        waitUrl: "/voice?wait=1",
        waitUrlMethod: "POST",
      },
      queue,
    );
    return callback(null, twiml);
  } catch (error) {
    return callback(error);
  }
};
