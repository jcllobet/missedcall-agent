import { NextRequest } from "next/server";
import { findProfileByTwilioNumber } from "@/lib/assistant-profile";
import { isRuntimeAuthorized } from "@/lib/runtime-auth";

export async function GET(request: NextRequest) {
  if (!isRuntimeAuthorized(request)) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const twilioNumber = request.nextUrl.searchParams.get("to") || "";
  const profile = await findProfileByTwilioNumber(twilioNumber);

  if (!profile || !profile.enabled) {
    return Response.json({ error: "Profile not found" }, { status: 404 });
  }

  return Response.json({
    profileId: profile.profileId,
    twilioNumber: profile.twilioNumber,
    forwardingPhoneNumber: profile.forwardingPhoneNumber,
    assistantName: profile.assistantName,
    greeting: profile.greeting,
    slackWebhookUrl: profile.slackWebhookUrl,
  });
}
