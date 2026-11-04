// Resumes: types shared by the server and the browser, and the small pure
// helpers the resume screens use. A resume is a selection over the person's
// cards, with its own versions. See docs/data-model.md.

import type { CardKind, Framing } from "./cards";
import type { ImportSummary } from "./imports";
import type { Proposal } from "./talk";

// "auto" uses the wording made for the resume's target, "main" the card's own,
// and a target ID that target's.
export type Wording = string;

export type ResumeItem = { card: string; wording?: Wording; version?: string | null };

export type ResumeEntry = { card: string; fold_earlier?: boolean; items: ResumeItem[] };

export type ResumeHeader = {
  name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  links: string[];
  summary: string;
};

export type ResumeContent = {
  header: ResumeHeader;
  entries: ResumeEntry[];
  context: ResumeItem[];
  note?: string | null;
};

export type ResumeVersion = {
  id: string;
  number: number;
  author_kind: "person" | "ai" | "reviewer";
  author_ref: string | null;
  created_at: string;
  synced_parent_version_id: string | null;
  redacted: boolean;
  // Names the person gave it, newest first.
  names: string[];
  note: string | null;
};

export type ResumeSummary = {
  id: string;
  name: string;
  target_id: string | null;
  target_name: string | null;
  parent_id: string | null;
  import_id: string | null;
  head_number: number;
  created_at: string;
  updated_at: string;
};

export type ResumeDetail = ResumeSummary & {
  parent_name: string | null;
  head: ResumeVersion;
  content: ResumeContent;
  versions: ResumeVersion[];
  // Changes in the resume it was made from that it hasn't taken or passed on.
  parent_changes: number;
};

export type RenderedItem = {
  card: string;
  kind: CardKind;
  text: string;
  detail: string;
  wording: "main" | "target" | "pinned";
  date: string;
};

export type RenderedRole = { card: string | null; title: string; dates: string; items: RenderedItem[] };

export type RenderedEntry = {
  card: string;
  employer: string;
  location: string;
  dates: string;
  fold_earlier: boolean;
  earlier_titles: string[];
  roles: RenderedRole[];
  // Accomplishments in this employment that the resume leaves out.
  hidden: RenderedItem[];
};

export type RenderedSection = { kind: CardKind; label: string; items: RenderedItem[] };

export type RenderedResume = {
  header: ResumeHeader;
  entries: RenderedEntry[];
  sections: RenderedSection[];
  // Employments in the library this resume leaves out.
  left_out: { card: string; employer: string; dates: string }[];
  // Lines whose card is gone, so they can't show.
  missing: number;
};

export type ResumePage = { resume: ResumeDetail; page: RenderedResume };

export type ResumeVersionPage = {
  version: ResumeVersion;
  content: ResumeContent;
  page: RenderedResume;
};

export type Resumes = { resumes: ResumeSummary[]; ready: ImportSummary[] };

export type ResumeChange = { key: string; kind: string; card: string };

export type LabeledChange = { change: ResumeChange; label: string };

// A version the Assembler proposes, made from another resume for a target.
export type NewResume = {
  name: string;
  target: string;
  target_kind: string;
  parent_id: string;
  parent_version_id: string;
  content: ResumeContent;
  rewordings: { card: string; framing: Framing }[];
};

export type ProposedResume = {
  proposal: Proposal;
  parent_name: string | null;
  page: RenderedResume;
};

export const RESUME_NAME_MAX = 120;
export const TARGET_MAX = 200;

// -- changing which lines show ------------------------------------------------

function copy(content: ResumeContent): ResumeContent {
  return structuredClone(content);
}

export function switchOff(content: ResumeContent, item: string): ResumeContent {
  const next = copy(content);
  for (const entry of next.entries) entry.items = entry.items.filter((i) => i.card !== item);
  next.context = next.context.filter((i) => i.card !== item);
  return next;
}

// Switches a line on under its employment, at the end.
export function switchOn(content: ResumeContent, entry: string, item: string): ResumeContent {
  const next = copy(content);
  const target = next.entries.find((e) => e.card === entry);
  if (target && !target.items.some((i) => i.card === item)) {
    target.items.push({ card: item, wording: "auto" });
  }
  return next;
}

export function leaveOut(content: ResumeContent, entry: string): ResumeContent {
  const next = copy(content);
  next.entries = next.entries.filter((e) => e.card !== entry);
  return next;
}

// Brings an employment back, with nothing switched on under it yet.
export function bringBack(content: ResumeContent, entry: string): ResumeContent {
  const next = copy(content);
  if (!next.entries.some((e) => e.card === entry)) {
    next.entries.push({ card: entry, fold_earlier: false, items: [] });
  }
  return next;
}

export function setFold(content: ResumeContent, entry: string, fold: boolean): ResumeContent {
  const next = copy(content);
  const target = next.entries.find((e) => e.card === entry);
  if (target) target.fold_earlier = fold;
  return next;
}

// Moves an employment up or down one place.
export function move(content: ResumeContent, entry: string, by: -1 | 1): ResumeContent {
  const next = copy(content);
  const at = next.entries.findIndex((e) => e.card === entry);
  const to = at + by;
  if (at < 0 || to < 0 || to >= next.entries.length) return next;
  const [moved] = next.entries.splice(at, 1);
  next.entries.splice(to, 0, moved!);
  return next;
}

export function sameContent(a: ResumeContent, b: ResumeContent): boolean {
  const strip = (c: ResumeContent) => JSON.stringify({ ...c, note: null });
  return strip(a) === strip(b);
}

// -- saying it plainly --------------------------------------------------------

// Who made a version: the person, or the agent that drafted it.
export function versionAuthor(version: ResumeVersion): string {
  if (version.author_kind === "person") return "You";
  if (version.author_kind === "ai") {
    return version.author_ref === "assembler" ? "Assembler" : "Plytos";
  }
  return "A reviewer";
}

// "Version 3 · Sent to Contoso".
export function versionLabel(version: ResumeVersion): string {
  const name = version.names[0];
  return name ? `Version ${version.number} · ${name}` : `Version ${version.number}`;
}

// What a resume is for: a target, or the person's own.
export function resumeFor(resume: ResumeSummary): string {
  return resume.target_name ? `For ${resume.target_name}` : "Your own, as you wrote it";
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

// "3 jobs · 9 lines · 2 reworded", for a proposed resume.
export function proposalSize(resume: NewResume): string {
  const lines =
    resume.content.entries.reduce((n, e) => n + e.items.length, 0) + resume.content.context.length;
  const parts = [count(resume.content.entries.length, "job", "jobs"), count(lines, "line", "lines")];
  if (resume.rewordings.length > 0) parts.push(`${resume.rewordings.length} reworded`);
  return parts.join(" · ");
}

// "2 changes", for a parent's changes not yet taken.
export function changesLabel(n: number): string {
  return count(n, "change", "changes");
}

// What the person asks Plytos for, from a resume's page.
export function askText(resumeName: string, forWhom: string): string {
  return `Make a version of ${resumeName} for ${forWhom.trim()}`;
}

// A resume's content the browser sent, checked before it goes to the API;
// null if it isn't one. The API checks every field again.
export function cleanContent(value: unknown): ResumeContent | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const { header, entries, context } = value as Record<string, unknown>;
  if (typeof header !== "object" || header === null || Array.isArray(header)) return null;
  if (!Array.isArray(entries) || !Array.isArray(context)) return null;
  if (entries.length > 200 || context.length > 500) return null;
  const isItem = (i: unknown) =>
    typeof i === "object" && i !== null && typeof (i as { card?: unknown }).card === "string";
  for (const e of entries) {
    if (!isItem(e) || !Array.isArray((e as { items?: unknown }).items)) return null;
    if (!(e as { items: unknown[] }).items.every(isItem)) return null;
  }
  if (!context.every(isItem)) return null;
  return value as ResumeContent;
}

// One line of text the browser sent, trimmed; null if empty or too long.
export function cleanLine(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed && trimmed.length <= max ? trimmed : null;
}
