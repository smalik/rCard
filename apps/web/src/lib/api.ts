import "server-only";

import type { CardContent, CardKind } from "./cards";
import {
  type Answer,
  FILENAME_HEADER,
  type ImportSummary,
  type MatchChoice,
  type Progress,
} from "./imports";
import type { LibraryCard, LibraryContent } from "./library";
import type {
  ParentChanges,
  ProposedResume,
  RenderedResume,
  ResumeContent,
  ResumeDetail,
  ResumeHeader,
  ResumePage,
  Resumes,
  ResumeVersionPage,
} from "./resumes";
import type { Session } from "./session";
import type { CheckInPlan, CheckIns, Message, Proposal, Thread } from "./talk";

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

async function apiRequest(path: string, session: Session, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
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
  return response;
}

async function apiFetch<T>(path: string, session: Session, init: RequestInit = {}): Promise<T> {
  return (await (await apiRequest(path, session, init)).json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  };
}

export function listCards(session: Session): Promise<CardSummary[]> {
  return apiFetch<CardSummary[]>("/v1/cards", session);
}

// Every card the person keeps, with its content, in their own order.
export function getLibrary(session: Session): Promise<LibraryCard[]> {
  return apiFetch<LibraryCard[]>("/v1/library", session);
}

export async function reorderCards(
  session: Session,
  parentId: string | null,
  cardIds: string[],
): Promise<void> {
  await apiRequest(
    "/v1/cards/reorder",
    session,
    json({ parent_id: parentId, card_ids: cardIds }),
  );
}

// What Plytos wrote when the person asked it to sum a job up again.
export type Rewritten = { headline: boolean; stories: number; dropped: number };

export async function rewriteSummaries(
  session: Session,
  cardId: string,
  replaceOwn: boolean,
): Promise<Rewritten> {
  return apiFetch<Rewritten>(
    `/v1/cards/${encodeURIComponent(cardId)}/summaries`,
    session,
    json({ replace_own: replaceOwn }),
  );
}

export type CardVersion = {
  id: string;
  number: number;
  author_kind: "person" | "ai" | "reviewer";
  created_at: string;
  redacted: boolean;
};

// Saves the person's edit as the card's next main version, on top of the
// version they started from.
export async function saveCardVersion(
  session: Session,
  id: string,
  baseVersionId: string,
  content: LibraryContent,
): Promise<void> {
  await apiRequest(
    `/v1/cards/${encodeURIComponent(id)}/versions`,
    session,
    json({ base_version_id: baseVersionId, content }),
  );
}

export function cardHistory(session: Session, id: string): Promise<CardVersion[]> {
  return apiFetch<CardVersion[]>(`/v1/cards/${encodeURIComponent(id)}/versions`, session);
}

// Keeps a resume, encrypted with the person's key, to be read in the
// background. Returns its status at once; the reading follows. The file name
// goes in a header, already URL-encoded, never in a URL.
export function createImport(
  session: Session,
  file: ArrayBuffer,
  encodedFilename: string,
): Promise<unknown> {
  return apiFetch<unknown>("/v1/imports", session, {
    method: "POST",
    body: file,
    headers: {
      "Content-Type": "application/octet-stream",
      [FILENAME_HEADER]: encodedFilename,
    },
  });
}

export function listImports(session: Session): Promise<ImportSummary[]> {
  return apiFetch<ImportSummary[]>("/v1/imports", session);
}

export function getImport(session: Session, id: string): Promise<unknown> {
  return apiFetch<unknown>(`/v1/imports/${encodeURIComponent(id)}`, session);
}

// Where a reading is, without what was read. Cheap enough to ask often.
export function getImportStatus(session: Session, id: string): Promise<unknown> {
  return apiFetch<unknown>(`/v1/imports/${encodeURIComponent(id)}/status`, session);
}

// Tries a reading that failed once more.
export function readAgain(session: Session, id: string): Promise<unknown> {
  return apiFetch<unknown>(`/v1/imports/${encodeURIComponent(id)}/read-again`, session, {
    method: "POST",
  });
}

// The person's original file, exactly as they gave it.
export async function getOriginal(
  session: Session,
  id: string,
): Promise<{ data: ArrayBuffer; type: string; name: string }> {
  const response = await apiRequest(`/v1/imports/${encodeURIComponent(id)}/original`, session, {
    headers: { Accept: "*/*" },
  });
  let name = "resume";
  try {
    name = decodeURIComponent(response.headers.get(FILENAME_HEADER) ?? "") || name;
  } catch {
    // A name that doesn't decode falls back to "resume".
  }
  return {
    data: await response.arrayBuffer(),
    type: response.headers.get("content-type") ?? "application/octet-stream",
    name,
  };
}

// A page of the person's PDF as a picture, to check what was read from it.
export async function getPage(
  session: Session,
  id: string,
  page: number,
): Promise<{ data: ArrayBuffer; type: string }> {
  const response = await apiRequest(`/v1/imports/${encodeURIComponent(id)}/pages/${page}`, session, {
    headers: { Accept: "image/jpeg" },
  });
  return {
    data: await response.arrayBuffer(),
    type: response.headers.get("content-type") ?? "image/jpeg",
  };
}

export async function deleteImport(session: Session, id: string): Promise<void> {
  await apiRequest(`/v1/imports/${encodeURIComponent(id)}`, session, {
    method: "DELETE",
  });
}

export function settleQuestion(
  session: Session,
  id: string,
  body: { finding: number; answer: Answer; value: string | null },
): Promise<Progress> {
  return apiFetch<Progress>(`/v1/imports/${encodeURIComponent(id)}/settle`, session, json(body));
}

export function decideCard(
  session: Session,
  id: string,
  ref: string,
  state: "later" | "dropped" | "pending",
): Promise<Progress> {
  return apiFetch<Progress>(
    `/v1/imports/${encodeURIComponent(id)}/cards/${encodeURIComponent(ref)}/decision`,
    session,
    json({ state }),
  );
}

export function placeCard(
  session: Session,
  id: string,
  ref: string,
  parentRef: string | null,
): Promise<Progress> {
  return apiFetch<Progress>(
    `/v1/imports/${encodeURIComponent(id)}/cards/${encodeURIComponent(ref)}/place`,
    session,
    json({ parent_ref: parentRef }),
  );
}

// The person's correction to a proposed card's words or dates before it's kept,
// or null to take it back.
export function fixCard(
  session: Session,
  id: string,
  ref: string,
  content: CardContent | null,
): Promise<Progress> {
  return apiFetch<Progress>(
    `/v1/imports/${encodeURIComponent(id)}/cards/${encodeURIComponent(ref)}/fix`,
    session,
    json({ content }),
  );
}

// Approves a proposed card. One that matches the person's own card carries on
// as it (see MatchChoice); `choice` null leaves that to the API's default.
export function approveCard(
  session: Session,
  id: string,
  ref: string,
  content: CardContent | null,
  choice: MatchChoice | null = null,
): Promise<{ card: { id: string }; progress: Progress }> {
  return apiFetch(
    `/v1/imports/${encodeURIComponent(id)}/cards/${encodeURIComponent(ref)}/approve`,
    session,
    json({ content, choice }),
  );
}

// Decides a group of proposed cards at once, such as a job and what's under it:
// keeps some (in the person's words where they changed them), leaves some out,
// sets some aside. All or nothing. Answers with the import as it now stands.
export function keepGroup(
  session: Session,
  id: string,
  body: {
    keep: { ref: string; content: CardContent | null; choice: MatchChoice | null }[];
    leave_out: string[];
    later: string[];
  },
): Promise<unknown> {
  return apiFetch<unknown>(`/v1/imports/${encodeURIComponent(id)}/keep`, session, json(body));
}

// The person's cards that an import's proposed cards stand for, as things stand.
export function getMatches(session: Session, id: string): Promise<unknown> {
  return apiFetch<unknown>(`/v1/imports/${encodeURIComponent(id)}/matches`, session);
}

// -- the conversation ---------------------------------------------------------

export function getConversation(session: Session, limit = 60): Promise<Message[]> {
  return apiFetch<Message[]>(`/v1/conversation?limit=${limit}`, session);
}

// The thread, the resumes it shares and the check-in plan, read together.
export async function getThread(session: Session): Promise<Thread> {
  const [messages, resumes, check_ins] = await Promise.all([
    getConversation(session),
    listImports(session),
    apiFetch<CheckIns>("/v1/check-ins", session),
  ]);
  return { messages, resumes, check_ins };
}

// Sets when Plytos checks in, or turns check-ins off. Plytos says what
// changed in the conversation.
export function setCheckIns(
  session: Session,
  plan: CheckInPlan,
): Promise<{ check_ins: CheckIns; message: Message }> {
  return apiFetch("/v1/check-ins", session, { ...json(plan), method: "PUT" });
}

// The person shares a resume in the conversation. It's kept like any import and
// read in the background; Plytos answers with what it found once it's read.
// The name goes in a header.
export function shareResume(
  session: Session,
  file: ArrayBuffer,
  encodedFilename: string,
): Promise<{ messages: Message[]; resume: ImportSummary }> {
  return apiFetch("/v1/conversation/resume", session, {
    method: "POST",
    body: file,
    headers: {
      "Content-Type": "application/octet-stream",
      [FILENAME_HEADER]: encodedFilename,
    },
  });
}

// Saves what the person said. The Listener reads it and answers shortly after.
export function say(session: Session, text: string): Promise<Message> {
  return apiFetch<Message>("/v1/conversation", session, json({ text }));
}

export function keepProposal(
  session: Session,
  id: string,
  content: CardContent | null,
): Promise<{ proposal: Proposal; card: { id: string } }> {
  return apiFetch(`/v1/proposals/${encodeURIComponent(id)}/keep`, session, json({ content }));
}

export function dismissProposal(session: Session, id: string): Promise<Proposal> {
  return apiFetch<Proposal>(`/v1/proposals/${encodeURIComponent(id)}/dismiss`, session, {
    method: "POST",
  });
}

// -- resumes ------------------------------------------------------------------

function resumePath(id: string, rest = ""): string {
  return `/v1/resumes/${encodeURIComponent(id)}${rest}`;
}

export function listResumes(session: Session): Promise<Resumes> {
  return apiFetch<Resumes>("/v1/resumes", session);
}

// Makes the person's resume as they wrote it, from the cards they kept from a
// file. Asking again for the same file returns the one made.
export function makeAsWritten(session: Session, importId: string): Promise<ResumePage> {
  return apiFetch<ResumePage>("/v1/resumes/as-written", session, json({ import_id: importId }));
}

export type LatestContact = { resumeId: string; resumeName: string; baseVersionId: string; header: ResumeHeader };

// The contact details at the top of the resume changed most recently, read in
// one request for the contact card. Null when there's no resume yet.
export async function getLatestContact(session: Session): Promise<LatestContact | null> {
  type Sent = { resume_id: string; resume_name: string; base_version_id: string; header: ResumeHeader };
  const contact = await apiFetch<Sent | null>("/v1/resumes/latest/contact", session);
  if (!contact) return null;
  return {
    resumeId: contact.resume_id,
    resumeName: contact.resume_name,
    baseVersionId: contact.base_version_id,
    header: contact.header,
  };
}

export function getResume(session: Session, id: string): Promise<ResumePage> {
  return apiFetch<ResumePage>(resumePath(id), session);
}

export function getResumeVersion(
  session: Session,
  id: string,
  number: number,
): Promise<ResumeVersionPage> {
  return apiFetch<ResumeVersionPage>(resumePath(id, `/versions/${number}`), session);
}

// How a change would read, without saving it.
export function previewResume(
  session: Session,
  id: string,
  content: ResumeContent,
): Promise<RenderedResume> {
  return apiFetch<RenderedResume>(resumePath(id, "/preview"), session, json(content));
}

export function saveResume(
  session: Session,
  id: string,
  baseVersionId: string,
  content: ResumeContent,
): Promise<ResumePage> {
  return apiFetch<ResumePage>(
    resumePath(id, "/versions"),
    session,
    json({ base_version_id: baseVersionId, content }),
  );
}

export function restoreResume(
  session: Session,
  id: string,
  number: number,
  baseVersionId: string,
): Promise<ResumePage> {
  return apiFetch<ResumePage>(
    resumePath(id, "/restore"),
    session,
    json({ number, base_version_id: baseVersionId }),
  );
}

export function nameResumeVersion(
  session: Session,
  id: string,
  number: number,
  name: string,
): Promise<ResumeDetail> {
  return apiFetch<ResumeDetail>(resumePath(id, `/versions/${number}/name`), session, json({ name }));
}

export function renameResume(session: Session, id: string, name: string): Promise<ResumeDetail> {
  return apiFetch<ResumeDetail>(resumePath(id), session, { ...json({ name }), method: "PATCH" });
}

export function parentChanges(session: Session, id: string): Promise<ParentChanges> {
  return apiFetch<ParentChanges>(resumePath(id, "/parent-changes"), session);
}

// Takes the chosen changes from the resume this one was made from; no keys
// passes on them all. It settles only up to the parent version reviewed.
export function takeChanges(
  session: Session,
  id: string,
  keys: string[],
  baseVersionId: string,
  parentVersionId: string | null,
): Promise<ResumePage> {
  return apiFetch<ResumePage>(
    resumePath(id, "/take"),
    session,
    json({ keys, base_version_id: baseVersionId, parent_version_id: parentVersionId }),
  );
}

// A version for a target, made by hand: it starts the same as this resume.
export function copyResume(
  session: Session,
  id: string,
  name: string,
  target: string,
): Promise<ResumePage> {
  return apiFetch<ResumePage>(
    resumePath(id, "/copies"),
    session,
    json({ name, target, target_kind: "custom" }),
  );
}

// Asks Plytos in the conversation for a version of this resume. The
// Assembler answers there.
export function askForVersion(session: Session, id: string, text: string): Promise<Message> {
  return apiFetch<Message>(resumePath(id, "/ask"), session, json({ text }));
}

export function getProposedResume(session: Session, id: string): Promise<ProposedResume> {
  return apiFetch<ProposedResume>(`/v1/proposals/${encodeURIComponent(id)}/resume`, session);
}

export function keepResume(
  session: Session,
  id: string,
): Promise<{ proposal: Proposal; resume: ResumeDetail }> {
  return apiFetch(`/v1/proposals/${encodeURIComponent(id)}/keep-resume`, session, json({}));
}
