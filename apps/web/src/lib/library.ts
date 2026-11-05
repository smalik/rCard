// The person's library of cards, shaped for the purpose-specific cards on
// screen: experience (employer > titles > accomplishments), education,
// awards, credentials, skills, projects and activities. Pure functions only,
// so the shaping is tested without a browser.

import type { CardContent, CardKind, FactValue } from "./cards";

export type AttachmentKind = "paper" | "repo" | "link";

export type Attachment = {
  kind: AttachmentKind;
  url: string;
  title: string;
  note: string;
};

export type LibraryContent = CardContent & { attachments: Attachment[] };

export type LibraryCard = {
  id: string;
  kind: CardKind;
  status: "draft" | "approved" | "archived";
  parent_id: string | null;
  sort_key: number | null;
  created_at: string;
  // Null once the card's text was redacted.
  content: LibraryContent | null;
  version_id: string;
  version: number;
  version_author: "person" | "ai" | "reviewer";
  updated_at: string;
  variants: number;
  variants_behind: number;
};

export type EngagementView = { card: LibraryCard; items: LibraryCard[] };

export type PositionView = {
  card: LibraryCard;
  engagements: EngagementView[];
  // Accomplishments and projects under the title, in the person's order.
  items: LibraryCard[];
};

export type ExperienceView = {
  card: LibraryCard;
  positions: PositionView[];
  engagements: EngagementView[];
  // Accomplishments that sit on the employer itself, such as wins that span
  // several titles there.
  items: LibraryCard[];
};

export type LibraryView = {
  experience: ExperienceView[];
  education: LibraryCard[];
  awards: LibraryCard[];
  credentials: LibraryCard[];
  skills: LibraryCard[];
  projects: LibraryCard[];
  activities: LibraryCard[];
  // Accomplishments that sit on no job yet.
  highlights: LibraryCard[];
  // Every card none of the above shows, such as a summary, a title whose
  // employer was left out, or work under a project, so nothing kept is hidden.
  other: LibraryCard[];
};

const ITEM_KINDS: ReadonlySet<CardKind> = new Set(["accomplishment", "project"]);

/** Orders siblings the way the person placed them; unplaced ones after, oldest first. */
export function bySortKey(a: LibraryCard, b: LibraryCard): number {
  if (a.sort_key !== b.sort_key) {
    if (a.sort_key === null) return 1;
    if (b.sort_key === null) return -1;
    return a.sort_key - b.sort_key;
  }
  return a.created_at.localeCompare(b.created_at);
}

export function buildLibrary(cards: readonly LibraryCard[]): LibraryView {
  const children = new Map<string, LibraryCard[]>();
  for (const card of cards) {
    if (card.parent_id === null) continue;
    const list = children.get(card.parent_id) ?? [];
    list.push(card);
    children.set(card.parent_id, list);
  }
  for (const list of children.values()) list.sort(bySortKey);
  const under = (card: LibraryCard, kinds: ReadonlySet<CardKind>) =>
    (children.get(card.id) ?? []).filter((c) => kinds.has(c.kind));
  const engagementsOf = (card: LibraryCard): EngagementView[] =>
    under(card, new Set(["engagement"])).map((e) => ({ card: e, items: under(e, ITEM_KINDS) }));

  const view: LibraryView = {
    experience: [],
    education: [],
    awards: [],
    credentials: [],
    skills: [],
    projects: [],
    activities: [],
    highlights: [],
    other: [],
  };
  const top = cards.filter((c) => c.parent_id === null).sort(bySortKey);
  for (const card of top) {
    switch (card.kind) {
      case "employment":
      case "role":
        view.experience.push({
          card,
          positions: under(card, new Set(["position"])).map((p) => ({
            card: p,
            engagements: engagementsOf(p),
            items: under(p, ITEM_KINDS),
          })),
          engagements: engagementsOf(card),
          items: under(card, ITEM_KINDS),
        });
        break;
      case "education":
        view.education.push(card);
        break;
      case "credential":
        view.credentials.push(card);
        break;
      case "skill":
        view.skills.push(card);
        break;
      case "project":
        view.projects.push(card);
        break;
      case "activity":
        view.activities.push(card);
        break;
      case "accomplishment":
        (fact(card, "award") ? view.awards : view.highlights).push(card);
        break;
      default:
        break;
    }
  }

  const shown = new Set<string>();
  for (const job of view.experience) {
    shown.add(job.card.id);
    const engagements = [...job.engagements, ...job.positions.flatMap((p) => p.engagements)];
    for (const c of [
      ...job.positions.flatMap((p) => [p.card, ...p.items]),
      ...engagements.flatMap((e) => [e.card, ...e.items]),
      ...job.items,
    ]) {
      shown.add(c.id);
    }
  }
  for (const list of [
    view.education,
    view.awards,
    view.credentials,
    view.skills,
    view.projects,
    view.activities,
    view.highlights,
  ]) {
    for (const c of list) shown.add(c.id);
  }
  view.other = [...cards].filter((c) => !shown.has(c.id)).sort(bySortKey);
  return view;
}

export function fact(card: LibraryCard, key: string): string {
  const value: FactValue | undefined = card.content?.facts[key];
  if (typeof value === "string") return value.trim();
  if (typeof value === "number") return String(value);
  return "";
}

export function listFact(card: LibraryCard, key: string): string[] {
  const value = card.content?.facts[key];
  if (Array.isArray(value)) return value.filter((v) => v.trim() !== "");
  if (typeof value === "string" && value.trim() !== "") return [value.trim()];
  return [];
}

export function headline(card: LibraryCard): string {
  return card.content?.framing.headline ?? "Hidden (redacted)";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2005-06" reads "Jun 2005"; "2005" stays "2005"; "present" reads "Present". */
export function formatDate(value: string): string {
  const text = value.trim();
  if (/^(present|current|now)$/i.test(text)) return "Present";
  const m = /^(\d{4})(?:-(\d{1,2}))?/.exec(text);
  if (!m) return text;
  const month = m[2] ? MONTHS[Number(m[2]) - 1] : undefined;
  return month ? `${month} ${m[1]}` : m[1]!;
}

export function dateRange(start: string, end: string): string {
  if (!start && !end) return "";
  if (!start) return formatDate(end);
  if (!end) return formatDate(start);
  return `${formatDate(start)} – ${formatDate(end)}`;
}

export function cardDates(card: LibraryCard): string {
  const date = fact(card, "date");
  return date ? formatDate(date) : dateRange(fact(card, "start"), fact(card, "end"));
}

/** How long ago something changed, in a few words. */
export function relativeTime(iso: string, now: Date): string {
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  const date = new Date(iso);
  return `${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

export type Evidence = { figures: number; attachments: number; level: 0 | 1 | 2 | 3 };

/** How well an accomplishment is backed: numbers, things to show, and a story. */
export function evidence(card: LibraryCard): Evidence {
  const figures = listFact(card, "figures").length;
  const attachments = card.content?.attachments.length ?? 0;
  const told = (card.content?.framing.body.trim().length ?? 0) >= 40;
  const level = ((figures > 0 ? 1 : 0) + (attachments > 0 ? 1 : 0) + (told ? 1 : 0)) as
    | 0
    | 1
    | 2
    | 3;
  return { figures, attachments, level };
}

/** What a web address most likely points at. */
export function attachmentKindFor(url: string): AttachmentKind {
  let host = "";
  let path = "";
  try {
    const parsed = new URL(url);
    host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    path = parsed.pathname.toLowerCase();
  } catch {
    return "link";
  }
  if (/(^|\.)(github\.com|gitlab\.com|bitbucket\.org|codeberg\.org)$/.test(host)) return "repo";
  if (
    /(^|\.)(doi\.org|arxiv\.org|ssrn\.com|acm\.org|ieee\.org|researchgate\.net|scholar\.google\.com|pubmed\.ncbi\.nlm\.nih\.gov|semanticscholar\.org|biorxiv\.org)$/.test(
      host,
    ) ||
    path.endsWith(".pdf")
  ) {
    return "paper";
  }
  return "link";
}

/** A web address the API accepts: http or https, with a host. */
export function isWebAddress(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    return (parsed.protocol === "https:" || parsed.protocol === "http:") && parsed.host !== "";
  } catch {
    return false;
  }
}

/** A copy of `list` with the item at `from` moved to `to`. */
export function move<T>(list: readonly T[], from: number, to: number): T[] {
  const next = [...list];
  if (from < 0 || from >= next.length || to < 0 || to >= next.length) return next;
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as T);
  return next;
}

/** Cards that are new, or whose content moved on, since the last look. */
export function changedSince(
  before: readonly LibraryCard[],
  after: readonly LibraryCard[],
): Set<string> {
  const seen = new Map(before.map((c) => [c.id, c.version_id]));
  return new Set(after.filter((c) => seen.get(c.id) !== c.version_id).map((c) => c.id));
}

const FACT_KEY = /^[a-z][a-z0-9_]{0,63}$/;
const ATTACHMENT_KINDS: readonly AttachmentKind[] = ["paper", "repo", "link"];
export const MAX_ATTACHMENTS = 20;

function isFactValue(value: unknown): value is FactValue {
  return (
    typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value)) ||
    (Array.isArray(value) && value.every((v) => typeof v === "string"))
  );
}

function cleanAttachment(raw: unknown): Attachment | null {
  if (typeof raw !== "object" || raw === null) return null;
  const a = raw as Record<string, unknown>;
  const kind = ATTACHMENT_KINDS.find((k) => k === a.kind);
  const url = typeof a.url === "string" ? a.url.trim() : "";
  const title = typeof a.title === "string" ? a.title.trim() : "";
  const note = typeof a.note === "string" ? a.note.trim() : "";
  if (!kind || !isWebAddress(url) || url.length > 2000) return null;
  if (title.length < 1 || title.length > 200 || note.length > 500) return null;
  return { kind, url, title, note };
}

/** A card's content as the browser sent it, or null when it isn't one. */
export function cleanContent(raw: unknown): LibraryContent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const c = raw as Record<string, unknown>;
  const framing = c.framing as Record<string, unknown> | undefined;
  const headline = typeof framing?.headline === "string" ? framing.headline.trim() : "";
  const body = typeof framing?.body === "string" ? framing.body.trim() : "";
  if (headline.length < 1 || headline.length > 200 || body.length > 5000) return null;
  const shown = framing?.shown_facts;
  if (shown !== undefined && shown !== null && !Array.isArray(shown)) return null;

  const facts: Record<string, FactValue> = {};
  if (typeof c.facts !== "object" || c.facts === null || Array.isArray(c.facts)) return null;
  for (const [key, value] of Object.entries(c.facts)) {
    if (!FACT_KEY.test(key) || !isFactValue(value)) return null;
    facts[key] = value;
  }
  const rawAttachments = c.attachments ?? [];
  if (!Array.isArray(rawAttachments) || rawAttachments.length > MAX_ATTACHMENTS) return null;
  const attachments = rawAttachments.map(cleanAttachment);
  if (attachments.some((a) => a === null)) return null;
  const parent = c.parent;
  if (parent !== undefined && parent !== null && typeof parent !== "string") return null;

  return {
    parent: (parent as string | null | undefined) ?? null,
    facts,
    framing: {
      headline,
      body,
      shown_facts: Array.isArray(shown) ? shown.filter((s): s is string => typeof s === "string") : null,
    },
    attachments: attachments as Attachment[],
  };
}

function monthIndex(value: string, now: Date, end: boolean): number | null {
  const text = value.trim();
  if (/^(present|current|now)$/i.test(text)) return now.getUTCFullYear() * 12 + now.getUTCMonth();
  const m = /^(\d{4})(?:-(\d{1,2}))?/.exec(text);
  if (!m) return null;
  const month = m[2] ? Number(m[2]) - 1 : end ? 11 : 0;
  return Number(m[1]) * 12 + month;
}

/** How long a stint ran, as "4 yrs 7 mos". Empty when the dates don't say. */
export function tenure(start: string, end: string, now: Date): string {
  const from = monthIndex(start, now, false);
  const to = end ? monthIndex(end, now, true) : null;
  if (from === null || to === null || to < from) return "";
  const months = to - from + 1;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [];
  if (years > 0) parts.push(`${years} ${years === 1 ? "yr" : "yrs"}`);
  if (rest > 0) parts.push(`${rest} ${rest === 1 ? "mo" : "mos"}`);
  return parts.join(" ");
}

/** The library with one parent's children put in a new order. */
export function withOrder(
  cards: readonly LibraryCard[],
  parentId: string | null,
  ids: readonly string[],
): LibraryCard[] {
  const place = new Map(ids.map((id, i) => [id, i]));
  return cards.map((c) =>
    c.parent_id === parentId && place.has(c.id) ? { ...c, sort_key: place.get(c.id)! } : c,
  );
}
