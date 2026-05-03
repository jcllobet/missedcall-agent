import { clerkClient } from "@clerk/nextjs/server";

const PROFILE_KEY = "missedcallAgent";

type Metadata = Record<string, unknown>;

type ClerkUserLike = {
  id: string;
  primaryPhoneNumber?: { phoneNumber?: string | null } | null;
  privateMetadata?: Metadata;
};

export type AssistantProfile = {
  profileId: string;
  ownerPhoneNumber: string;
  twilioNumber: string;
  forwardingPhoneNumber: string;
  assistantName: string;
  greeting: string;
  systemPrompt: string;
  slackWebhookUrl: string;
  updatedAt: string;
};

export type RuntimeProfile = AssistantProfile & {
  enabled: boolean;
};

function defaultGreeting(assistantName: string): string {
  return `${assistantName} here. They can't pick up. What do you need from them? I'll help or pass along a message.`;
}

function defaultPrompt(assistantName: string): string {
  return `You are ${assistantName}, an AI secretary handling voicemail so missed calls become useful instead of annoying. The person you represent cannot pick up right now, so you are speaking on their behalf.

Sound like a sharp founder-operator, not a receptionist. Be direct, calm, curious, and useful. Get to the point of what the caller wants and surface the main points upfront. Less is more. Avoid polished call-center language. The caller should feel like they reached a lightweight assistant, not a generic support desk.

Your job is to understand why the caller reached out, help when you can, and leave the shortest useful version of what happened.

Goals:
- Identify why the caller wanted to speak with the person you represent.
- Capture the caller's name, preferred follow-up method, what they expect, and when follow-up is needed.
- Help with simple questions when the answer is obvious from context.
- Turn vague asks into a concrete next step.
- If the person really wants a human follow-up, say you have flagged it and it will be reviewed after the call.

Rules:
- Be brief, conversational, and concrete.
- Ask one question at a time.
- Keep the conversation moving without sounding rushed.
- Say they are busy at the moment, but you will pass along the message and ask when follow-up is needed.
- If the caller wants email follow-up, ask for the email address and spell it back to confirm it is correct.
- Do not pretend to transfer, schedule, or confirm anything unless the system actually supports it.
- Do not pretend the person you represent is live on the call.
- If the request is unclear, ask for the practical version: what do you need, why does it matter, and what should happen next.
- If the call is obviously spam, do not reveal personal information. Keep them talking briefly, then end the call.

Conversation outline:
1. The greeting is already handled. Listen to what the caller wants.
2. If you can answer or help directly, do that first.
3. If you cannot, capture the useful follow-up details.
4. Confirm the next step and end the call without padding.
5. Answer one or two follow-up questions if needed, then end the call.`;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

export function normalizePhoneNumber(value: string): string {
  const digits = value.replace(/[^\d]/g, "");
  if (!digits) {
    return "";
  }

  if (digits.length === 10) {
    return `+1${digits}`;
  }

  return `+${digits}`;
}

function profileMetadata(user: ClerkUserLike): Metadata {
  const value = user.privateMetadata?.[PROFILE_KEY];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Metadata)
    : {};
}

export function profileFromUser(user: ClerkUserLike): AssistantProfile {
  const metadata = profileMetadata(user);
  const ownerPhoneNumber = user.primaryPhoneNumber?.phoneNumber || "";
  const assistantName = stringValue(metadata.assistantName, "AI Assistant");

  return {
    profileId: user.id,
    ownerPhoneNumber,
    twilioNumber: stringValue(metadata.twilioNumber),
    forwardingPhoneNumber: stringValue(metadata.forwardingPhoneNumber, ownerPhoneNumber),
    assistantName,
    greeting: stringValue(metadata.greeting, defaultGreeting(assistantName)),
    systemPrompt: stringValue(metadata.systemPrompt, defaultPrompt(assistantName)),
    slackWebhookUrl: stringValue(metadata.slackWebhookUrl),
    updatedAt: stringValue(metadata.updatedAt),
  };
}

export async function getAssistantProfileForUser(
  userId: string,
): Promise<AssistantProfile> {
  const client = await clerkClient();
  const user = await client.users.getUser(userId);
  return profileFromUser(user);
}

async function listUsers(): Promise<ClerkUserLike[]> {
  const client = await clerkClient();
  const result = await client.users.getUserList({ limit: 100 });
  return Array.isArray(result) ? result : result.data;
}

export async function findProfileByTwilioNumber(
  twilioNumber: string,
): Promise<RuntimeProfile | null> {
  const normalized = normalizePhoneNumber(twilioNumber);
  if (!normalized) {
    return null;
  }

  for (const user of await listUsers()) {
    const profile = profileFromUser(user);
    if (normalizePhoneNumber(profile.twilioNumber) === normalized) {
      return {
        ...profile,
        twilioNumber: normalized,
        enabled: Boolean(profile.forwardingPhoneNumber && profile.systemPrompt),
      };
    }
  }

  return null;
}

export async function getRuntimeProfileById(
  profileId: string,
): Promise<RuntimeProfile | null> {
  const client = await clerkClient();

  try {
    const user = await client.users.getUser(profileId);
    const profile = profileFromUser(user);
    return {
      ...profile,
      enabled: Boolean(profile.forwardingPhoneNumber && profile.systemPrompt),
    };
  } catch {
    return null;
  }
}

export async function saveAssistantProfile(
  userId: string,
  formData: FormData,
): Promise<void> {
  const client = await clerkClient();
  const user = await client.users.getUser(userId);
  const metadata = profileMetadata(user);
  const current = profileFromUser(user);
  const nextProfile = { ...current };

  if (formData.has("twilioNumber")) {
    nextProfile.twilioNumber = normalizePhoneNumber(String(formData.get("twilioNumber") || ""));
    if (!isValidPhoneNumber(nextProfile.twilioNumber)) {
      throw new Error("Enter the assigned Twilio number in E.164 format.");
    }
    const existing = await findProfileByTwilioNumber(nextProfile.twilioNumber);
    if (existing && existing.profileId !== userId) {
      throw new Error("That Twilio number is already assigned to another profile.");
    }
  }

  if (formData.has("forwardingPhoneNumber")) {
    nextProfile.forwardingPhoneNumber = normalizePhoneNumber(
      String(formData.get("forwardingPhoneNumber") || ""),
    );
    if (!isValidPhoneNumber(nextProfile.forwardingPhoneNumber)) {
      throw new Error("Enter the forwarding number in E.164 format.");
    }
  }

  if (formData.has("assistantName")) {
    nextProfile.assistantName =
      boundedText(String(formData.get("assistantName") || ""), 2, 80) || "AI Assistant";
    if (!metadata.greeting && !formData.has("greeting")) {
      nextProfile.greeting = defaultGreeting(nextProfile.assistantName);
    }
    if (!metadata.systemPrompt && !formData.has("systemPrompt")) {
      nextProfile.systemPrompt = defaultPrompt(nextProfile.assistantName);
    }
  }

  if (formData.has("greeting")) {
    nextProfile.greeting = boundedText(String(formData.get("greeting") || ""), 20, 500);
  }

  if (formData.has("systemPrompt")) {
    nextProfile.systemPrompt = boundedText(String(formData.get("systemPrompt") || ""), 200, 8000);
  }

  if (formData.has("slackWebhookUrl")) {
    const slackWebhookUrl = String(formData.get("slackWebhookUrl") || "").trim();
    if (slackWebhookUrl && !slackWebhookUrl.startsWith("https://hooks.slack.com/services/")) {
      throw new Error("Slack webhook must be a hooks.slack.com URL.");
    }
    nextProfile.slackWebhookUrl = slackWebhookUrl;
  }

  nextProfile.updatedAt = new Date().toISOString();

  await client.users.updateUserMetadata(userId, {
    privateMetadata: {
      ...user.privateMetadata,
      [PROFILE_KEY]: nextProfile,
    },
  });
}

function isValidPhoneNumber(value: string): boolean {
  return /^\+\d{10,15}$/.test(value);
}

function boundedText(value: string, minLength: number, maxLength: number): string {
  const trimmed = value.trim();
  if (trimmed.length < minLength) {
    throw new Error(`Enter at least ${minLength} characters.`);
  }
  if (trimmed.length > maxLength) {
    throw new Error(`Keep this under ${maxLength} characters.`);
  }
  return trimmed;
}
