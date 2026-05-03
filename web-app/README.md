# missedcall-agent web app

Minimal Clerk-protected profile editor for the shared Twilio and Pipecat voice
runtime.

## Setup

Copy the env template:

```bash
cp .env.example .env.local
```

Required values:

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/
NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/
RUNTIME_API_KEY=
```

`RUNTIME_API_KEY` is not a Clerk setting. It is any random shared secret you
choose for the voice runtime to call this app's profile lookup endpoints without
a user browser session. Use the same value as `PRODUCT_API_KEY` in
`../voice-agent`.

In Clerk Dashboard, configure authentication so phone number is the only allowed
sign-up and sign-in method. This must be enforced in the dashboard, not only in
the app UI, so Clerk-hosted routes cannot expose email or OAuth:

- Enable phone number / SMS verification.
- Disable email address for sign-up and sign-in.
- Disable password auth if it is enabled.
- Disable every social and OAuth provider.
- Confirm the hosted Clerk sign-in page no longer shows email, password, Google,
  or any other OAuth provider.

Run locally:

```bash
npm run dev
```

## Manual Twilio Assignment

For this MVP, buy and configure Twilio numbers manually. Give the user their
assigned Twilio number, then have them save it in the app with their forwarding
number and assistant prompt.

Point every Twilio number at the same voice Function. The Function looks up the
profile by the called number.

## Runtime API

The voice runtime calls:

```text
GET /api/runtime/profiles/by-number?to=+15551234567
GET /api/runtime/profiles/:profileId
```

Both endpoints require:

```http
Authorization: Bearer <RUNTIME_API_KEY>
```
