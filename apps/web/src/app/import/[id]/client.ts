// The browser's side of the import actions: each posts to Plytos's own server,
// which checks the request and passes it to the private API.

import type { Progress } from "../../../lib/imports";

export type Outcome = { ok: true; progress: Progress } | { ok: false; error: string };

export async function post(url: string, body: unknown): Promise<Outcome> {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = (await response.json().catch(() => null)) as
      | (Progress & { error?: string })
      | null;
    if (response.ok && data) return { ok: true, progress: data };
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
