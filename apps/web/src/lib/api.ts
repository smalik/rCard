import "server-only";

import type { CardKind } from "./cards";
import { type AcceptBody, FILENAME_HEADER } from "./import-review";
import type { Session } from "./session";

// The API is private: only this server talks to it, never the browser.
const API_URL = process.env.PLYTOS_API_URL ?? "http://localhost:8000";

export type CardSummary = {
  id: string;
  kind: CardKind;
  status: "draft" | "approved" | "archived";
  headline: string | null;
  main_version: number;
  variants: number;
  variants_behind: number;
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    // The API's own explanation, when it gave one as plain text. Validation
    // errors echo their input, so those never become a detail.
    readonly detail: string | null = null,
  ) {
    super(message);
  }
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

// On Cloud Run, the metadata server issues an ID token that proves this
// request comes from the web service's identity.
async function serviceIdentityToken(): Promise<string | null> {
  if (!process.env.K_SERVICE) return null;
  const url =
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity" +
    `?audience=${encodeURIComponent(API_URL)}`;
  const response = await fetch(url, { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!response.ok) throw new ApiError(response.status, "could not get a service identity token");
  return response.text();
}

async function apiFetch<T>(path: string, session: Session, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const token = await serviceIdentityToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (process.env.PLYTOS_ENV === "dev") headers.set("X-Plytos-Dev-User", session.subject);

  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `${init.method ?? "GET"} ${path} failed`,
      await errorDetail(response),
    );
  }
  return (await response.json()) as T;
}

export function listCards(session: Session): Promise<CardSummary[]> {
  return apiFetch<CardSummary[]>("/v1/cards", session);
}

// Reads a resume and returns proposed cards and an audit. The API stores
// nothing. The file name goes in a header, already URL-encoded, never in a URL.
export function previewImport(
  session: Session,
  file: ArrayBuffer,
  encodedFilename: string,
): Promise<unknown> {
  return apiFetch<unknown>("/v1/imports/preview", session, {
    method: "POST",
    body: file,
    headers: {
      "Content-Type": "application/octet-stream",
      [FILENAME_HEADER]: encodedFilename,
    },
  });
}

// Saves the cards the person kept, all or none.
export function acceptImport(session: Session, body: AcceptBody): Promise<{ id: string }[]> {
  return apiFetch<{ id: string }[]>("/v1/imports/accept", session, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}
