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

// Bullets show the featured lines, a paragraph the person's own words.
export type HighlightStyle = "bullets" | "paragraph" | "both";

export const HIGHLIGHT_STYLES: { value: HighlightStyle; label: string }[] = [
  { value: "bullets", label: "Bullets" },
  { value: "paragraph", label: "Paragraph" },
  { value: "both", label: "Both" },
];

export const HIGHLIGHTS_MAX = 12;
export const HIGHLIGHT_PARAGRAPH_MAX = 1500;

// Lines featured again near the top. Each sits under a job first.
export type ResumeHighlights = { style: HighlightStyle; paragraph: string; items: ResumeItem[] };

export type ResumeContent = {
  header: ResumeHeader;
  entries: ResumeEntry[];
  context: ResumeItem[];
  // Left out when the resume has no highlights section.
  highlights?: ResumeHighlights | null;
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
  // Where it sits, for a highlight or a line waiting for a job: "Title · Employer".
  where?: string;
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

export type RenderedHighlights = { style: HighlightStyle; paragraph: string; items: RenderedItem[] };

export type RenderedResume = {
  header: ResumeHeader;
  highlights?: RenderedHighlights | null;
  entries: RenderedEntry[];
  sections: RenderedSection[];
  // Employments in the library this resume leaves out.
  left_out: { card: string; employer: string; dates: string }[];
  // Cards outside the career tree, such as a degree, that it leaves out.
  // Older API answers may not carry it.
  left_out_context?: RenderedItem[];
  // Accomplishments this resume has outside any job on it. They don't show
  // until they're under one; `where` names the job a card already sits under.
  unplaced?: RenderedItem[];
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

// A resume made from this one that deleting a version reaches.
export type DeletionBranch = {
  id: string;
  name: string;
  made_from: number | null;
  caught_up_with: number | null;
  // Where it counts from if it stays; null when it will stand on its own.
  recenters_on: number | null;
};

export type DeletionPlan = {
  numbers: number[];
  // The version the resume goes back to, when the one it's at is deleted.
  back_to: number | null;
  deletes_resume: boolean;
  branches: DeletionBranch[];
};

// The resume after a deletion; null when its last version went.
export type Deleted = { resume: ResumePage | null };

export type ResumeChange = { key: string; kind: string; card: string };

export type LabeledChange = { change: ResumeChange; label: string };

// The changes, and the parent's version they run to, sent back when taking them.
export type ParentChanges = { parent_version_id: string | null; changes: LabeledChange[] };

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

// The versions still there, newest first; deleted ones keep only their number.
export function keptVersions(versions: ResumeVersion[]): ResumeVersion[] {
  return [...versions].reverse().filter((v) => !v.redacted);
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

// Brings a card outside the career tree in, at the end of its section.
export function switchOnContext(content: ResumeContent, item: string): ResumeContent {
  const next = copy(content);
  if (!next.context.some((i) => i.card === item)) next.context.push({ card: item, wording: "auto" });
  return next;
}

// Moves one line up or down among the lines shown with it (`group`, in the
// order they show), keeping every other line where it was. Lines sit in the
// content in one list per employment (or one for context); only the places
// the group holds in that list change hands.
function reorderIn(items: ResumeItem[], group: string[], item: string, by: -1 | 1): ResumeItem[] {
  const at = group.indexOf(item);
  const to = at + by;
  if (at < 0 || to < 0 || to >= group.length) return items;
  const order = [...group];
  [order[at], order[to]] = [order[to]!, order[at]!];
  const byCard = new Map(items.map((i) => [i.card, i]));
  const members = new Set(group);
  let next = 0;
  return items.map((i) => (members.has(i.card) ? byCard.get(order[next++]!)! : i));
}

export function moveLine(
  content: ResumeContent,
  entry: string,
  group: string[],
  item: string,
  by: -1 | 1,
): ResumeContent {
  const next = copy(content);
  const target = next.entries.find((e) => e.card === entry);
  if (!target || !group.every((card) => target.items.some((i) => i.card === card))) return next;
  target.items = reorderIn(target.items, group, item, by);
  return next;
}

export function moveContextLine(
  content: ResumeContent,
  group: string[],
  item: string,
  by: -1 | 1,
): ResumeContent {
  const next = copy(content);
  if (!group.every((card) => next.context.some((i) => i.card === card))) return next;
  next.context = reorderIn(next.context, group, item, by);
  return next;
}

// -- highlights ----------------------------------------------------------------

function highlightsOf(content: ResumeContent): ResumeHighlights {
  return content.highlights ?? { style: "bullets", paragraph: "", items: [] };
}

// Turns the highlights section on, in bullets, or off. Off forgets what it held.
export function showHighlights(content: ResumeContent, on: boolean): ResumeContent {
  const next = copy(content);
  next.highlights = on ? highlightsOf(next) : null;
  return next;
}

export function setHighlightStyle(content: ResumeContent, style: HighlightStyle): ResumeContent {
  const next = copy(content);
  next.highlights = { ...highlightsOf(next), style };
  return next;
}

export function setHighlightParagraph(content: ResumeContent, paragraph: string): ResumeContent {
  const next = copy(content);
  next.highlights = { ...highlightsOf(next), paragraph: paragraph.slice(0, HIGHLIGHT_PARAGRAPH_MAX) };
  return next;
}

// Features a line from under a job, at the end, with the wording it has there.
export function feature(content: ResumeContent, card: string): ResumeContent {
  const next = copy(content);
  const highlights = highlightsOf(next);
  if (highlights.items.length >= HIGHLIGHTS_MAX || highlights.items.some((i) => i.card === card)) {
    return next;
  }
  const there = next.entries.flatMap((e) => e.items).find((i) => i.card === card);
  highlights.items.push(there ? { ...there } : { card, wording: "auto" });
  next.highlights = highlights;
  return next;
}

export function unfeature(content: ResumeContent, card: string): ResumeContent {
  const next = copy(content);
  if (next.highlights) next.highlights.items = next.highlights.items.filter((i) => i.card !== card);
  return next;
}

export function moveHighlight(content: ResumeContent, card: string, by: -1 | 1): ResumeContent {
  const next = copy(content);
  if (!next.highlights) return next;
  const group = next.highlights.items.map((i) => i.card);
  next.highlights.items = reorderIn(next.highlights.items, group, card, by);
  return next;
}

// A line that waited outside any job now shows under one: it leaves the
// context and comes in at the end of that job, bringing the job in if the
// resume had left it out.
export function placeLine(content: ResumeContent, card: string, entry: string): ResumeContent {
  const next = copy(content);
  const item = next.context.find((i) => i.card === card) ?? { card, wording: "auto" };
  next.context = next.context.filter((i) => i.card !== card);
  const target = next.entries.find((e) => e.card === entry);
  if (!target) next.entries.push({ card: entry, fold_earlier: false, items: [item] });
  else if (!target.items.some((i) => i.card === card)) target.items.push(item);
  return next;
}

export function setHeader(content: ResumeContent, header: ResumeHeader): ResumeContent {
  const next = copy(content);
  next.header = { ...header, links: header.links.filter((l) => l.trim()).slice(0, 5) };
  return next;
}

export function sameContent(a: ResumeContent, b: ResumeContent): boolean {
  const strip = (c: ResumeContent) => JSON.stringify({ ...c, note: null });
  return strip(a) === strip(b);
}

// -- saying it plainly --------------------------------------------------------

// What a line shows. A headline cut short shows the whole text kept in its
// detail; a skills card shows its skills; education and the like show their
// details under the line. An accomplishment's extra context stays off the page.
export function lineParts(item: RenderedItem): { text: string; detail: string } {
  const detail = item.detail.trim();
  if (!detail) return { text: item.text, detail: "" };
  if (item.text.endsWith("…") && detail.startsWith(item.text.slice(0, -1).trimEnd())) {
    return { text: detail, detail: "" };
  }
  if (item.kind === "skill") {
    return { text: item.text === "Skills" ? detail : `${item.text}: ${detail}`, detail: "" };
  }
  if (item.kind === "accomplishment" || item.kind === "project" || item.kind === "story") {
    return { text: item.text, detail: "" };
  }
  return { text: item.text, detail };
}

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
  const { header, entries, context, highlights } = value as Record<string, unknown>;
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
  if (highlights !== undefined && highlights !== null) {
    if (typeof highlights !== "object" || Array.isArray(highlights)) return null;
    const { style, paragraph, items } = highlights as Record<string, unknown>;
    if (!HIGHLIGHT_STYLES.some((s) => s.value === style)) return null;
    if (typeof paragraph !== "string" || paragraph.length > HIGHLIGHT_PARAGRAPH_MAX) return null;
    if (!Array.isArray(items) || items.length > HIGHLIGHTS_MAX || !items.every(isItem)) return null;
  }
  return value as ResumeContent;
}

// One line of text the browser sent, trimmed; null if empty or too long.
export function cleanLine(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed && trimmed.length <= max ? trimmed : null;
}
