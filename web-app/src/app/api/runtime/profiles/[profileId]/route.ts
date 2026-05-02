import { NextRequest } from "next/server";
import { getRuntimeProfileById } from "@/lib/assistant-profile";
import { isRuntimeAuthorized } from "@/lib/runtime-auth";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ profileId: string }> },
) {
  if (!isRuntimeAuthorized(request)) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { profileId } = await params;
  const profile = await getRuntimeProfileById(profileId);

  if (!profile || !profile.enabled) {
    return Response.json({ error: "Profile not found" }, { status: 404 });
  }

  return Response.json(profile);
}
