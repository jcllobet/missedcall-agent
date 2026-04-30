exports.handler = function handler(context, event, callback) {
  const twiml = new Twilio.twiml.VoiceResponse();
  const status = event.DialCallStatus;

  if (status) {
    if (status === "completed" || status === "answered") {
      twiml.hangup();
      return callback(null, twiml);
    }

    const connect = twiml.connect();
    const stream = connect.stream({
      url: context.PIPECAT_CLOUD_WS_URL || "wss://api.pipecat.daily.co/ws/twilio",
    });
    stream.parameter({
      name: "_pipecatCloudServiceHost",
      value: context.PIPECAT_CLOUD_SERVICE_HOST,
    });
    stream.parameter({
      name: "fallback_reason",
      value: `jan_${String(status).replace(/-/g, "_")}`,
    });
    stream.parameter({ name: "caller", value: event.From || "" });
    stream.parameter({ name: "inbound_call_sid", value: event.CallSid || "" });
    stream.parameter({ name: "dial_call_sid", value: event.DialCallSid || "" });
    return callback(null, twiml);
  }

  const dial = twiml.dial({
    timeout: Number.parseInt(context.HUMAN_RING_TIMEOUT_SECONDS || "10", 10),
    action: "/voice",
    method: "POST",
    answerOnBridge: true,
    callerId: context.TWILIO_PHONE_NUMBER,
  });
  dial.number(context.JAN_PHONE_NUMBER);
  return callback(null, twiml);
};
