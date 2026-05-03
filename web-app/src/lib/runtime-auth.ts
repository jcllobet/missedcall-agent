import { NextRequest } from "next/server";

export function isRuntimeAuthorized(request: NextRequest): boolean {
  const expected = process.env.RUNTIME_API_KEY;
  if (!expected) {
    return false;
  }

  const authorization = request.headers.get("authorization") || "";
  const bearer = authorization.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length)
    : "";
  const apiKey = request.headers.get("x-runtime-api-key") || bearer;

  return apiKey === expected;
}
