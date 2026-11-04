// The browser's side of the import actions: each posts to Plytos's own server,
// which checks the request and passes it to the private API.

import type { CardMatch, Progress } from "../../../lib/imports";

// A card decision also says which of the person's cards the rest now match.
export type Outcome =
  | { ok: true; progress: Progress; matches?: Record<string, CardMatch> }
  | { ok: false; error: string };

export async function post(url: string, body: unknown): Promise<Outcome> {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = (await response.json().catch(() => null)) as
      | (Progress & { error?: string })
      | { progress: Progress; matches: Record<string, CardMatch>; error?: string }
      | null;
    if (response.ok && data) {
      return "progress" in data
        ? { ok: true, progress: data.progress, matches: data.matches }
        : { ok: true, progress: data };
    }
    return {
      ok: false,
      error: data?.error ?? "That didn't save. Try again in a moment.",
    };
  } catch {
    return {
      ok: false,
      error: "The connection dropped. Check you're online and try again.",
    };
  }
}
