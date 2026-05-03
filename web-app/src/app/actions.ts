"use server";

import { auth } from "@clerk/nextjs/server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { saveAssistantProfile } from "@/lib/assistant-profile";

export async function updateAssistantProfile(formData: FormData) {
  const { userId } = await auth();
  if (!userId) {
    throw new Error("You must be signed in to update an assistant profile.");
  }

  await saveAssistantProfile(userId, formData);
  revalidatePath("/");
  if (formData.get("intent") === "next") {
    redirect("/?step=prompt");
  }
  if (formData.get("intent") === "savePrompt") {
    redirect("/?step=prompt&saved=1");
  }
}
