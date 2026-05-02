"use server";

import { auth } from "@clerk/nextjs/server";
import { revalidatePath } from "next/cache";
import { saveAssistantProfile } from "@/lib/assistant-profile";

export async function updateAssistantProfile(formData: FormData) {
  const { userId } = await auth();
  if (!userId) {
    throw new Error("You must be signed in to update an assistant profile.");
  }

  await saveAssistantProfile(userId, formData);
  revalidatePath("/");
}
