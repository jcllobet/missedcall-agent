import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { updateAssistantProfile } from "./actions";
import { SubmitButton } from "./submit-button";
import { getAssistantProfileForUser } from "@/lib/assistant-profile";

function Field({
  label,
  name,
  defaultValue,
  placeholder,
  help,
  type = "text",
  required = false,
  minLength,
  maxLength,
}: {
  label: string;
  name: string;
  defaultValue: string;
  placeholder?: string;
  help?: string;
  type?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-[#273244]">{label}</span>
      <input
        className="h-11 rounded-md border border-[#cfd7cb] bg-white px-3 text-sm text-[#111827] outline-none transition placeholder:text-[#8b9688] focus:border-[#0f5132] focus:ring-2 focus:ring-[#0f5132]/15"
        defaultValue={defaultValue}
        name={name}
        placeholder={placeholder}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
        type={type}
      />
      {help ? <span className="text-xs leading-5 text-[#667064]">{help}</span> : null}
    </label>
  );
}

function TextArea({
  label,
  name,
  defaultValue,
  rows,
  help,
  required = false,
  minLength,
  maxLength,
}: {
  label: string;
  name: string;
  defaultValue: string;
  rows: number;
  help?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-[#273244]">{label}</span>
      <textarea
        className="resize-y rounded-md border border-[#cfd7cb] bg-white px-3 py-3 text-sm leading-6 text-[#111827] outline-none transition placeholder:text-[#8b9688] focus:border-[#0f5132] focus:ring-2 focus:ring-[#0f5132]/15"
        defaultValue={defaultValue}
        name={name}
        rows={rows}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
      />
      {help ? <span className="text-xs leading-5 text-[#667064]">{help}</span> : null}
    </label>
  );
}

function StepPill({ active, children }: { active: boolean; children: React.ReactNode }) {
  return (
    <span
      className={`rounded-md px-3 py-1 text-xs font-semibold ${
        active ? "bg-[#0f5132] text-white" : "bg-[#edf2ea] text-[#667064]"
      }`}
    >
      {children}
    </span>
  );
}

function SignedOutHome() {
  return (
    <main>
      <section className="border-b border-[#d9dfd3] bg-[#f6f7f3]">
        <div className="mx-auto grid w-full max-w-6xl gap-7 px-5 py-8 md:grid-cols-[1fr_440px] md:items-center md:py-28">
          <div className="max-w-2xl">
            <p className="mb-4 text-sm font-semibold uppercase text-[#0f5132]">
              AI VOICEMAIL THAT ACTUALLY HELPS
            </p>
            <h1 className="text-3xl font-semibold leading-tight text-[#111827] sm:text-6xl">
              Stop giving every website your real phone number.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-[#4b5563] sm:text-lg sm:leading-8">
              Get a number with an AI secretary that answers when you do not,
              figures out what the caller wants, and sends you the useful parts.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                className="flex h-11 items-center rounded-md bg-[#0f5132] px-5 text-sm font-semibold text-white transition hover:bg-[#0b3d26]"
                href="/sign-up"
              >
                Create your AI voicemail
              </Link>
              <Link
                className="flex h-11 items-center rounded-md border border-[#cfd7cb] bg-white px-5 text-sm font-semibold text-[#273244] transition hover:bg-[#edf2ea]"
                href="/sign-in"
              >
                Sign in
              </Link>
            </div>
            <p className="mt-3 text-sm leading-6 text-[#667064]">
              Phone-number signup. No email, no social login.
            </p>
          </div>

          <div className="grid gap-3 rounded-lg border border-[#cfd7cb] bg-white p-4 shadow-sm md:gap-4 md:p-5">
            <div className="flex items-center justify-between border-b border-[#e3e8df] pb-3">
              <div>
                <p className="text-xs font-semibold uppercase text-[#667064]">
                  LIVE MISSED CALL
                </p>
                <p className="mt-1 font-mono text-sm text-[#111827]">+1 415 555 0198</p>
              </div>
              <span className="rounded-md bg-[#dcefe3] px-2 py-1 text-xs font-semibold text-[#0f5132]">
                screened
              </span>
            </div>
            <div className="grid gap-3 text-sm leading-6 md:gap-4">
              <div className="border-l-2 border-[#0f5132] pl-3 text-[#4b5563]">
                <p className="font-medium text-[#111827]">AI Secretary</p>
                <p className="mt-1">
                  Jan cannot pick up. What is this about?
                </p>
              </div>
              <div className="border-l-2 border-[#93a38d] pl-3 text-[#4b5563]">
                <p className="font-medium text-[#111827]">Caller</p>
                <p className="mt-1">
                  There is an unpaid IRS invoice. He must call today to avoid
                  penalties.
                </p>
              </div>
              <div className="border-t border-[#e3e8df] pt-4">
                <p className="text-xs font-semibold uppercase text-[#667064]">
                  SPAM RECAP
                </p>
                <p className="mt-2 text-[#4b5563]">
                  Claimed IRS debt with urgency. No invoice number or written
                  notice provided.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-6xl gap-4 px-5 py-10 md:grid-cols-3">
        <div className="rounded-lg border border-[#d9dfd3] bg-white p-4 md:p-5">
          <p className="text-sm font-semibold text-[#111827]">Fake tax urgency</p>
          <p className="mt-2 text-sm leading-6 text-[#4b5563]">
            Unpaid IRS invoice, pay today, penalties start immediately.
          </p>
        </div>
        <div className="rounded-lg border border-[#d9dfd3] bg-white p-4 md:p-5">
          <p className="text-sm font-semibold text-[#111827]">Warranty calls</p>
          <p className="mt-2 text-sm leading-6 text-[#4b5563]">
            Vehicle coverage expiring, press one to speak with an agent.
          </p>
        </div>
        <div className="rounded-lg border border-[#d9dfd3] bg-white p-4 md:p-5">
          <p className="text-sm font-semibold text-[#111827]">Account scares</p>
          <p className="mt-2 text-sm leading-6 text-[#4b5563]">
            Package stuck, bank account verification, or another urgent account
            scare.
          </p>
        </div>
      </section>
    </main>
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { userId } = await auth();

  if (!userId) {
    return <SignedOutHome />;
  }

  const profile = await getAssistantProfileForUser(userId);
  const params = (await searchParams) || {};
  const step = params.step === "prompt" ? "prompt" : "numbers";
  const saved = params.saved === "1";

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-8">
      <div className="mb-7 flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-semibold uppercase text-[#0f5132]">
            ASSISTANT PROFILE
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-[#111827]">
            Set up your AI voicemail
          </h1>
        </div>
        <p className="max-w-xl text-sm leading-6 text-[#4b5563]">
          Start with the number callers use and the phone that should ring first.
          Then tune what the assistant says.
        </p>
      </div>

      <div className="mb-5 flex gap-2">
        <StepPill active={step === "numbers"}>1. Numbers</StepPill>
        <StepPill active={step === "prompt"}>2. Greeting and prompt</StepPill>
      </div>

      {step === "numbers" ? (
        <form
          action={updateAssistantProfile}
          className="rounded-lg border border-[#d9dfd3] bg-white p-5 shadow-sm"
        >
          <input name="intent" type="hidden" value="next" />
          <div className="grid gap-5 md:grid-cols-2">
            <Field
              defaultValue={profile.twilioNumber}
              help="The Twilio number assigned to this user. Use the number callers should save."
              label="Send calls from"
              name="twilioNumber"
              placeholder="+15551234567"
              required
              type="tel"
            />
            <Field
              defaultValue={profile.forwardingPhoneNumber}
              help={`Defaults to the phone used at signup${
                profile.ownerPhoneNumber ? `: ${profile.ownerPhoneNumber}` : "."
              }`}
              label="Forward calls to"
              name="forwardingPhoneNumber"
              placeholder="+15557654321"
              required
              type="tel"
            />
            <Field
              defaultValue={profile.assistantName}
              label="Assistant name"
              maxLength={80}
              minLength={2}
              name="assistantName"
              placeholder="AI Assistant"
              required
            />
            <Field
              defaultValue={profile.slackWebhookUrl}
              help="Optional. Leave blank if recaps stay in the shared Slack path."
              label="Slack webhook"
              name="slackWebhookUrl"
              placeholder="https://hooks.slack.com/services/..."
              type="url"
            />
          </div>

          <div className="mt-6 flex flex-col gap-3 border-t border-[#d9dfd3] pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="font-mono text-xs text-[#667064]">Profile ID: {profile.profileId}</p>
            <SubmitButton label="Next" pendingLabel="Saving..." />
          </div>
        </form>
      ) : (
        <form
          action={updateAssistantProfile}
          className="rounded-lg border border-[#d9dfd3] bg-white p-5 shadow-sm"
        >
          <input name="intent" type="hidden" value="savePrompt" />
          <div className="mb-5 flex flex-col justify-between gap-2 border-b border-[#d9dfd3] pb-5 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm font-semibold text-[#111827]">{profile.assistantName}</p>
              <p className="mt-1 text-sm text-[#667064]">
                {profile.twilioNumber || "No Twilio number yet"} to{" "}
                {profile.forwardingPhoneNumber || profile.ownerPhoneNumber || "no forwarding number yet"}
              </p>
            </div>
            <Link
              className="text-sm font-semibold text-[#0f5132] hover:text-[#0b3d26]"
              href="/"
            >
              Edit numbers
            </Link>
          </div>

          {saved ? (
            <p className="mb-4 rounded-md bg-[#dcefe3] px-3 py-2 text-sm font-medium text-[#0f5132]">
              Saved.
            </p>
          ) : null}

          <div className="grid gap-5">
            <TextArea
              defaultValue={profile.greeting}
              help="The first thing the AI says. Keep it short enough to feel like a real voicemail pickup."
              label="Greeting"
              maxLength={500}
              minLength={20}
              name="greeting"
              required
              rows={3}
            />
            <TextArea
              defaultValue={profile.systemPrompt}
              help="Edit the behavior freely. The runtime still appends required voice, privacy, and call-ending guardrails so the agent keeps working."
              label="Prompt"
              maxLength={8000}
              minLength={200}
              name="systemPrompt"
              required
              rows={18}
            />
          </div>

          <div className="mt-6 flex flex-col gap-3 border-t border-[#d9dfd3] pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-[#667064]">
              Required runtime guardrails are applied after this prompt.
            </p>
            <SubmitButton label="Save greeting and prompt" pendingLabel="Saving..." />
          </div>
        </form>
      )}
    </main>
  );
}
