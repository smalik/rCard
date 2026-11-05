"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ResumePage } from "@/lib/resumes";

import { send } from "./send";

/** Makes the resume as written from the cards kept from a file, then opens it. */
export function useMakeResume(importId: string) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function make() {
    setBusy(true);
    setError(null);
    const result = await send<ResumePage>("/resumes/as-written", { import_id: importId });
    if (!result.ok) {
      setBusy(false);
      setError(result.error);
      return;
    }
    router.push(`/resumes/${encodeURIComponent(result.data.resume.id)}`);
  }

  return { make, busy, error };
}
