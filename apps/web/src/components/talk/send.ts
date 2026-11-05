// The browser's side of the conversation: each call goes to Plytos's own
// server, which checks it and passes it to the private API.

export type Sent<T> = { ok: true; data: T } | { ok: false; error: string };

export async function send<T>(url: string, body?: unknown): Promise<Sent<T>> {
  try {
    const response = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = (await response.json().catch(() => null)) as (T & { error?: string }) | null;
    if (response.ok && data) return { ok: true, data };
    return { ok: false, error: data?.error ?? "That didn't go through. Try again in a moment." };
  } catch {
    return { ok: false, error: "The connection dropped. Check you're online and try again." };
  }
}
