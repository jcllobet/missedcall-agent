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

const DEFAULT_GREETING =
  "Jan's Assistant here. He can't pick up. What do you need from him? I'll help or pass him a message.";

const DEFAULT_PROMPT =
  "You are a concise AI voicemail assistant. Understand why the caller reached out, capture their name, preferred follow-up method, what they need, and when the owner should follow up. Be direct, conversational, and brief. Ask one question at a time. Do not pretend to schedule, transfer, or confirm anything unless the system supports it.";

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

export function normalizePhoneNumber(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }

  const prefix = trimmed.startsWith("+") ? "+" : "";
  return prefix + trimmed.replace(/[^\d]/g, "");
}

function profileMetadata(user: ClerkUserLike): Metadata {
  const value = user.privateMetadata?.[PROFILE_KEY];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Metadata)
    : {};
}

export function profileFromUser(user: ClerkUserLike): AssistantProfile {
  const metadata = profileMetadata(user);

  return {
    profileId: user.id,
    ownerPhoneNumber: user.primaryPhoneNumber?.phoneNumber || "",
    twilioNumber: stringValue(metadata.twilioNumber),
    forwardingPhoneNumber: stringValue(metadata.forwardingPhoneNumber),
    assistantName: stringValue(metadata.assistantName, "Jan's Assistant"),
    greeting: stringValue(metadata.greeting, DEFAULT_GREETING),
    systemPrompt: stringValue(metadata.systemPrompt, DEFAULT_PROMPT),
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
  const current = profileFromUser(user);
  const twilioNumber = normalizePhoneNumber(String(formData.get("twilioNumber") || ""));
  const forwardingPhoneNumber = normalizePhoneNumber(
    String(formData.get("forwardingPhoneNumber") || ""),
  );

  if (twilioNumber) {
    const existing = await findProfileByTwilioNumber(twilioNumber);
    if (existing && existing.profileId !== userId) {
      throw new Error("That Twilio number is already assigned to another profile.");
    }
  }

  const nextProfile = {
    ...current,
    twilioNumber,
    forwardingPhoneNumber,
    assistantName: String(formData.get("assistantName") || "").trim() || "AI Assistant",
    greeting: String(formData.get("greeting") || "").trim() || DEFAULT_GREETING,
    systemPrompt: String(formData.get("systemPrompt") || "").trim() || DEFAULT_PROMPT,
    slackWebhookUrl: String(formData.get("slackWebhookUrl") || "").trim(),
    updatedAt: new Date().toISOString(),
  };

  await client.users.updateUserMetadata(userId, {
    privateMetadata: {
      ...user.privateMetadata,
      [PROFILE_KEY]: nextProfile,
    },
  });
}
