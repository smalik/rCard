"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ResumePage } from "../../lib/resumes";

// Sets up the person's resume as they wrote it, from a file's kept cards.
export function MakeResume({ importId }: { importId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function make() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/resumes/as-written", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ import_id: importId }),
      });
      const data = (await response.json().catch(() => null)) as
        | (ResumePage & { error?: string })
        | null;
      if (!response.ok || !data?.resume) {
        setError(data?.error ?? "That didn't go through. Try again in a moment.");
        setBusy(false);
        return;
      }
      router.push(`/resumes/${encodeURIComponent(data.resume.id)}`);
    } catch {
      setError("The connection dropped. Check you're online and try again.");
      setBusy(false);
    }
  }

  return (
    <>
      {error && (
        <p className="attention small" role="alert">
          {error}
        </p>
      )}
      <button className="button primary" type="button" disabled={busy} onClick={make}>
        {busy ? "Setting it up…" : "Set up my resume"}
      </button>
    </>
  );
}
