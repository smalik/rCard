"use client";

import { faTrashCan } from "@fortawesome/free-solid-svg-icons";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "../../../components/icon";

// Deletes the original file and everything read from it, after one check.
// Cards the person already approved stay.
export function DeleteImport({ id, approved }: { id: string; approved: number }) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/import/${id}/delete`, { method: "POST" });
      if (!response.ok) throw new Error("delete failed");
      router.replace("/import");
      router.refresh();
    } catch {
      setBusy(false);
      setError("That didn't delete. Try again in a moment.");
    }
  }

  if (!asking) {
    return (
      <button className="text-button small danger" type="button" onClick={() => setAsking(true)}>
        <Icon icon={faTrashCan} size={12} />
        Delete the file and this import
      </button>
    );
  }
  return (
    <div className="confirm" role="group" aria-label="Delete this import">
      <p className="small-copy">
        This deletes your original file, what we read from it, and any cards you haven&apos;t
        approved.{" "}
        {approved > 0
          ? `The ${approved === 1 ? "card" : `${approved} cards`} you approved stay.`
          : "It can't be undone."}
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button className="chip-button danger" type="button" onClick={remove} disabled={busy}>
          {busy ? "Deleting…" : "Delete it"}
        </button>
        <button className="text-button small" type="button" onClick={() => setAsking(false)}>
          Keep it
        </button>
      </div>
    </div>
  );
}
