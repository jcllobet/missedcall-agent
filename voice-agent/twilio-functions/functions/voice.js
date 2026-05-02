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

async function runtimeProfile(context, event) {
  const fallbackProfile = {
    profileId: "",
    twilioNumber: context.TWILIO_PHONE_NUMBER,
    forwardingPhoneNumber: context.JAN_PHONE_NUMBER,
    assistantName: "AI Assistant",
  };

  if (!context.PRODUCT_API_BASE_URL || !context.PRODUCT_API_KEY || !event.To) {
    return fallbackProfile;
  }

  const url = new URL("/api/runtime/profiles/by-number", context.PRODUCT_API_BASE_URL);
  url.searchParams.set("to", event.To);
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${context.PRODUCT_API_KEY}` },
  });

  if (response.status === 404) {
    return fallbackProfile;
  }
  if (!response.ok) {
    throw new Error(`Profile lookup failed: ${response.status}`);
  }
  return response.json();
}

async function pipecatCloudWsUrl(context) {
  if (!context.PIPECAT_CLOUD_SERVICE_HOST || !context.PCC_PUBLIC_KEY) {
    throw new Error("PIPECAT_CLOUD_SERVICE_HOST and PCC_PUBLIC_KEY are required");
  }

  const agentName = context.PIPECAT_CLOUD_SERVICE_HOST.split(".")[0];
  const response = await fetch(`https://api.pipecat.daily.co/v1/public/${agentName}/start`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${context.PCC_PUBLIC_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ transport: "websocket" }),
  });

  if (!response.ok) {
    throw new Error(`Pipecat Cloud /start failed: ${response.status}`);
  }

  const data = await response.json();
  if (!data.wsUrl || !data.token) {
    throw new Error("Pipecat Cloud /start did not return wsUrl and token");
  }
  return `${String(data.wsUrl).replace(/\/$/, "")}/${data.token}`;
}

async function aiStream(twiml, context, event, fallbackReason) {
  const connect = twiml.connect();
  const stream = connect.stream({
    url: await pipecatCloudWsUrl(context),
  });
  stream.parameter({ name: "fallback_reason", value: fallbackReason });
  stream.parameter({ name: "caller", value: event.From || "" });
  stream.parameter({ name: "profile_id", value: event.profile_id || "" });
  stream.parameter({ name: "inbound_call_sid", value: event.CallSid || event.caller || "" });
  stream.parameter({ name: "dial_call_sid", value: event.DialCallSid || "" });
}

async function redirectCallerToAi(context, callerSid, fallbackReason, profileId) {
  if (!callerSid || !context.getTwilioClient) {
    return;
  }

  const client = context.getTwilioClient();
  await client.calls(callerSid).update({
    url: voiceUrl(context, {
      force_ai: "1",
      fallback_reason: fallbackReason,
      profile_id: profileId || "",
    }),
    method: "POST",
  });
}

exports.handler = async function handler(context, event, callback) {
  const twiml = new Twilio.twiml.VoiceResponse();

  try {
    if (event.force_ai === "1") {
      await aiStream(twiml, context, event, event.fallback_reason || "jan_not_accepted");
      return callback(null, twiml);
    }

    if (event.jan_call_status === "1") {
      const callStatus = String(event.CallStatus || "").toLowerCase();
      if (FAILED_JAN_STATUSES.has(callStatus)) {
        await redirectCallerToAi(
          context,
          event.caller,
          `jan_${callStatus.replace(/-/g, "_")}`,
          event.profile_id,
        );
      }
      return callback(null, twiml);
    }

    if (event.amd_status === "1") {
      const answeredBy = String(event.AnsweredBy || "").toLowerCase();
      if (answeredBy && answeredBy !== "human") {
        await redirectCallerToAi(context, event.caller, `jan_${answeredBy}`, event.profile_id);
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

      await aiStream(twiml, context, event, `queue_${event.QueueResult || "timeout"}`);
      return callback(null, twiml);
    }

    if (event.screen === "prompt") {
      const gather = twiml.gather({
        action: voicePath({
          screen: "result",
          queue: event.queue || "",
          caller: event.caller || "",
          profile_id: event.profile_id || "",
        }),
        method: "POST",
        numDigits: 1,
        timeout: 6,
        input: "dtmf",
        actionOnEmptyResult: true,
      });
      gather.say("Incoming call. Press 1 to accept.");
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

      await redirectCallerToAi(context, event.caller, "jan_not_accepted", event.profile_id);
      twiml.hangup();
      return callback(null, twiml);
    }

    const profile = await runtimeProfile(context, event);
    if (!profile.forwardingPhoneNumber || !profile.twilioNumber) {
      twiml.say("This voicemail assistant is not configured yet. Please try again later.");
      twiml.hangup();
      return callback(null, twiml);
    }

    const callerSid = event.CallSid;
    const queue = queueName(callerSid);
    const profileParam = profile.profileId ? { profile_id: profile.profileId } : {};
    const client = context.getTwilioClient();
    await client.calls.create({
      to: profile.forwardingPhoneNumber,
      from: profile.twilioNumber,
      url: voiceUrl(context, {
        screen: "prompt",
        queue,
        caller: callerSid || "",
        ...profileParam,
      }),
      method: "POST",
      timeout: Number.parseInt(context.HUMAN_RING_TIMEOUT_SECONDS || "10", 10),
      statusCallback: voiceUrl(context, {
        jan_call_status: "1",
        queue,
        caller: callerSid || "",
        ...profileParam,
      }),
      statusCallbackMethod: "POST",
      statusCallbackEvent: ["completed"],
      machineDetection: "Enable",
      asyncAmd: true,
      asyncAmdStatusCallback: voiceUrl(context, {
        amd_status: "1",
        queue,
        caller: callerSid || "",
        ...profileParam,
      }),
      asyncAmdStatusCallbackMethod: "POST",
    });

    twiml.enqueue(
      {
        action: voicePath({ queue_result: "1", ...profileParam }),
        method: "POST",
        waitUrl: voicePath({ wait: "1" }),
        waitUrlMethod: "POST",
      },
      queue,
    );
    return callback(null, twiml);
  } catch (error) {
    return callback(error);
  }
};
