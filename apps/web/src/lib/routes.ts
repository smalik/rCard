import "server-only";

import { ApiError } from "./api";
import { isSameOrigin } from "./same-origin";
import { currentSession, type Session } from "./session";

// Helpers for the route handlers the browser calls. Each one checks the
// request came from Plytos and that someone is signed in, then passes the
// work to the private API.

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const CARD_REF = /^card-\d{1,4}$/;

export function problem(status: number, message: string): Response {
  return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}

export function ok(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export function isImportId(id: string): boolean {
  return UUID.test(id);
}

export function isId(id: string): boolean {
  return UUID.test(id);
}

export function isCardRef(ref: string): boolean {
  return CARD_REF.test(ref);
}

// The session for a request from Plytos's own pages, or the response to send instead.
export async function guard(
  request: Request,
  signedOut = "Sign in to bring in a resume.",
): Promise<Session | Response> {
  if (!isSameOrigin(request)) return problem(403, "This request has to come from Plytos.");
  const session = await currentSession();
  if (!session) return problem(401, signedOut);
  return session;
}

export async function readJson(request: Request, max = 64 * 1024): Promise<unknown> {
  const text = await request.text();
  if (text.length > max) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

// Turns an API failure into a message for the person. Only the API's own
// plain-text explanations are passed on, never validation errors, which can
// echo what was sent.
export function apiProblem(error: unknown, gone = "That import isn't here any more."): Response {
  if (!(error instanceof ApiError)) throw error;
  if (error.status === 404) return problem(404, gone);
  if ((error.status === 409 || error.status === 413 || error.status === 422) && error.detail) {
    return problem(error.status, error.detail);
  }
  if (error.status === 410) return problem(410, "This import can't be read any more.");
  return problem(502, "Plytos couldn't do that just now. Try again in a moment.");
}

// Reads the request body, giving up as soon as it passes the size limit.
export async function readCapped(request: Request, max: number): Promise<Uint8Array | null> {
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}
