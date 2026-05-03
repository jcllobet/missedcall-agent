"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({
  label = "Save profile",
  pendingLabel = "Saving...",
}: {
  label?: string;
  pendingLabel?: string;
}) {
  const { pending } = useFormStatus();

  return (
    <button
      className="h-11 rounded-md bg-[#0f5132] px-5 text-sm font-semibold text-white transition hover:bg-[#0b3d26] disabled:cursor-not-allowed disabled:opacity-60"
      disabled={pending}
      type="submit"
    >
      {pending ? pendingLabel : label}
    </button>
  );
}
