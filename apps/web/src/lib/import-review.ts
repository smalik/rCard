// The import review: what the browser gets back from a resume preview, and
// the pure logic behind the review screen. Nothing here is stored; the person
// decides which cards to keep, and only those are saved.

import {
  BODY_MAX,
  type CardContent,
  type CardKind,
  type FactValue,
  HEADLINE_MAX,
} from "./cards";

export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
export const MAX_ACCEPT_CARDS = 300;
export const FILENAME_HEADER = "X-Plytos-Filename";

export type Severity = "fix" | "improve" | "note";

export type FindingLocation = { block: number | null; excerpt: string };

export type Finding = {
  rule: string;
  severity: Severity;
  category: string;
  // "cards": the problem is in the words or facts, so it travels into the
  // cards. "document": it's about this file's layout or formatting.
  about: "cards" | "document";
  title: string;
  detail: string;
  locations: FindingLocation[];
};

export type ProposedCard = {
  ref: string;
  kind: CardKind;
  content: CardContent;
  role_ref: string | null;
  source_blocks: number[];
  needs_check: string[];
};

export type ImportPreview = {
  file: { format: string; pages: number | null; words: number };
  cards: ProposedCard[];
  findings: Finding[];
};

// Picks what the review screen needs from the API's import result. The full
// text of the resume and its contact details stay on the server.
export function toPreview(result: unknown): ImportPreview {
  const raw = (result ?? {}) as {
    facts?: { format?: string; pages?: number | null; word_count?: number };
    cards?: ProposedCard[];
    findings?: Finding[];
  };
  return {
    file: {
      format: raw.facts?.format ?? "unknown",
      pages: raw.facts?.pages ?? null,
      words: raw.facts?.word_count ?? 0,
    },
    cards: (raw.cards ?? []).map((card) => ({
      ref: card.ref,
      kind: card.kind,
      content: card.content,
      role_ref: card.role_ref ?? null,
      source_blocks: card.source_blocks ?? [],
      needs_check: card.needs_check ?? [],
    })),
    findings: (raw.findings ?? []).map((finding) => ({
      rule: finding.rule,
      severity: finding.severity,
      category: finding.category,
      about: finding.about === "cards" ? "cards" : "document",
      title: finding.title,
      detail: finding.detail,
      locations: finding.locations ?? [],
    })),
  };
}

// --- Findings ---------------------------------------------------------------

export const SEVERITY_LABELS: Record<Severity, string> = {
  fix: "Fix",
  improve: "Improve",
  note: "Note",
};

const SEVERITY_ORDER: Record<Severity, number> = { fix: 0, improve: 1, note: 2 };

export function isAboutCards(finding: Finding): boolean {
  return finding.about === "cards";
}

export function bySeverity(findings: Finding[]): Finding[] {
  return findings
    .map((finding, i) => ({ finding, i }))
    .sort(
      (a, b) =>
        SEVERITY_ORDER[a.finding.severity] - SEVERITY_ORDER[b.finding.severity] || a.i - b.i,
    )
    .map(({ finding }) => finding);
}

export function severityCounts(findings: Finding[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { fix: 0, improve: 0, note: 0 };
  for (const finding of findings) counts[finding.severity] += 1;
  return counts;
}

export function findingKey(finding: Finding, index: number): string {
  return `${finding.rule}#${index}`;
}

function normalize(text: string): string {
  return text.replace(/…$/, "").replace(/\s+/g, " ").trim().toLowerCase();
}

// How many cards were built from each line. A paragraph can become several
// cards, one per sentence.
function cardsPerBlock(cards: ProposedCard[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const card of cards) {
    for (const block of card.source_blocks) counts.set(block, (counts.get(block) ?? 0) + 1);
  }
  return counts;
}

// Whether a finding's location is about this card. When several cards came
// from the same line, the excerpt has to match the card's own words.
function locationMatches(
  card: ProposedCard,
  location: FindingLocation,
  perBlock: Map<number, number>,
): boolean {
  if (location.block === null || !card.source_blocks.includes(location.block)) return false;
  if ((perBlock.get(location.block) ?? 0) <= 1) return true;
  const excerpt = normalize(location.excerpt);
  const text = normalize(`${card.content.framing.headline} ${card.content.framing.body}`);
  if (!excerpt || !text) return false;
  return text.includes(excerpt.slice(0, 60)) || excerpt.includes(text.slice(0, 60));
}

// The cards a finding is about: those built from the lines it points at.
export function cardsForFinding(finding: Finding, cards: ProposedCard[]): string[] {
  const perBlock = cardsPerBlock(cards);
  return cards
    .filter((card) => finding.locations.some((loc) => locationMatches(card, loc, perBlock)))
    .map((card) => card.ref);
}

export type CardFinding = { finding: Finding; excerpts: string[] };

// The findings to show on a card: only ones about its words, with the
// excerpts that came from the card's own lines.
export function findingsForCard(
  card: ProposedCard,
  findings: Finding[],
  cards: ProposedCard[],
): CardFinding[] {
  const perBlock = cardsPerBlock(cards);
  const out: CardFinding[] = [];
  for (const finding of bySeverity(findings)) {
    if (!isAboutCards(finding)) continue;
    const excerpts = finding.locations
      .filter((loc) => locationMatches(card, loc, perBlock))
      .map((loc) => loc.excerpt);
    if (excerpts.length > 0) out.push({ finding, excerpts: [...new Set(excerpts)] });
  }
  return out;
}

// --- Grouping ---------------------------------------------------------------

// A role group's title comes from its role card, which the person can edit,
// so the screen reads it from the current decision rather than storing it.
export type CardGroup = {
  key: string;
  title: string;
  roleCard: string | null;
  refs: string[];
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatMonth(value: FactValue | undefined): string | null {
  if (typeof value !== "string" || !value) return null;
  if (value === "present") return "Present";
  const match = /^(\d{4})(?:-(\d{2}))?$/.exec(value);
  if (!match) return value;
  const month = match[2] ? MONTHS[Number(match[2]) - 1] : undefined;
  return month ? `${month} ${match[1]}` : (match[1] ?? value);
}

export function dateSpan(facts: Record<string, FactValue>): string | null {
  const start = formatMonth(facts.start);
  const end = formatMonth(facts.end);
  if (start && end) return `${start} – ${end}`;
  return start ?? end;
}

// The line under a role's heading: its dates, the agency for a client
// engagement, and the kind of employment.
export function roleSubtitle(content: CardContent): string | null {
  const facts = content.facts;
  const parts = [dateSpan(facts)];
  if (facts.client && typeof facts.employer === "string") parts.push(`through ${facts.employer}`);
  if (typeof facts.employment_type === "string") parts.push(facts.employment_type);
  const text = parts.filter(Boolean).join(" · ");
  return text || null;
}

function otherGroup(card: ProposedCard): { key: string; title: string } {
  if (card.kind === "story") return { key: "summary", title: "Summary" };
  if (card.kind === "skill") return { key: "skills", title: "Skills" };
  if (card.kind === "education") return { key: "education", title: "Education" };
  if (card.kind === "credential") return { key: "credentials", title: "Certifications" };
  if (card.kind === "project") return { key: "projects", title: "Projects" };
  if (card.content.facts.award !== undefined) return { key: "awards", title: "Awards" };
  return { key: "highlights", title: "Highlights" };
}

const GROUP_ORDER = [
  "summary",
  "highlights",
  "roles",
  "skills",
  "education",
  "credentials",
  "projects",
  "awards",
];

// Groups cards the way a resume reads: summary and highlights, then each role
// with its accomplishments, then skills, education and the rest.
export function groupCards(cards: ProposedCard[]): CardGroup[] {
  const roles = new Map<string, CardGroup>();
  const others = new Map<string, CardGroup>();
  for (const card of cards) {
    if (card.role_ref) {
      let group = roles.get(card.role_ref);
      if (!group) {
        group = { key: card.role_ref, title: "Role", roleCard: null, refs: [] };
        roles.set(card.role_ref, group);
      }
      if (card.kind === "role") {
        group.title = card.content.framing.headline;
        group.roleCard = card.ref;
        group.refs.unshift(card.ref);
      } else {
        group.refs.push(card.ref);
      }
      continue;
    }
    const { key, title } = otherGroup(card);
    const group = others.get(key) ?? { key, title, roleCard: null, refs: [] };
    group.refs.push(card.ref);
    others.set(key, group);
  }
  const out: CardGroup[] = [];
  for (const key of GROUP_ORDER) {
    if (key === "roles") out.push(...roles.values());
    else if (others.has(key)) out.push(others.get(key)!);
  }
  return out;
}

// --- Decisions --------------------------------------------------------------

export type Decision = { keep: boolean; edited: boolean; content: CardContent };
export type Decisions = Record<string, Decision>;

export function initialDecisions(cards: ProposedCard[]): Decisions {
  return Object.fromEntries(
    cards.map((card) => [card.ref, { keep: true, edited: false, content: card.content }]),
  );
}

const DATE_FACT = /^(\d{4})(-(0[1-9]|1[0-2]))?$/;

// Plain-language problems that would stop a card from saving.
export function contentProblems(content: CardContent): string[] {
  const problems: string[] = [];
  const headline = content.framing.headline.trim();
  if (!headline) problems.push("Add a headline.");
  if (headline.length > HEADLINE_MAX) {
    problems.push(`Keep the headline under ${HEADLINE_MAX} characters.`);
  }
  if (content.framing.body.length > BODY_MAX) {
    problems.push(`Keep the description under ${BODY_MAX} characters.`);
  }
  for (const key of ["start", "end", "date"]) {
    const value = content.facts[key];
    if (value === undefined) continue;
    const ok =
      typeof value === "string" &&
      (DATE_FACT.test(value) || (key === "end" && value === "present"));
    if (!ok) {
      problems.push(
        key === "end"
          ? "Write the end date as a year and month, like 2021-03, or as present."
          : `Write the ${key === "date" ? "date" : "start date"} as a year and month, like 2021-03.`,
      );
    }
  }
  return problems;
}

export type AcceptBody = { cards: { kind: CardKind; content: CardContent }[] };

export function keptCards(cards: ProposedCard[], decisions: Decisions): ProposedCard[] {
  return cards.filter((card) => decisions[card.ref]?.keep);
}

export function acceptBody(cards: ProposedCard[], decisions: Decisions): AcceptBody {
  return {
    cards: keptCards(cards, decisions).map((card) => {
      const content = decisions[card.ref]!.content;
      return {
        kind: card.kind,
        content: {
          facts: content.facts,
          framing: { ...content.framing, headline: content.framing.headline.trim() },
        },
      };
    }),
  };
}

// --- Editing facts ----------------------------------------------------------

const FACT_LABELS: Record<string, string> = {
  title: "Title",
  employer: "Employer",
  client: "Client",
  agency: "Agency",
  start: "Start",
  end: "End",
  location: "Location",
  employment_type: "Employment type",
  role_type: "Role type",
  workstream: "Workstream",
  figures: "Numbers",
  award: "Award",
  date: "Date",
  name: "Name",
  institution: "School",
  degree: "Degree",
  category: "Category",
  skills: "Skills",
  use: "Used as",
};

export const FACT_HINTS: Record<string, string> = {
  start: "Year and month, like 2021-03",
  end: "Year and month, or present",
  date: "Year and month, like 2021-03",
  figures: "Separate with commas",
  skills: "Separate with commas",
};

export function factLabel(key: string): string {
  return FACT_LABELS[key] ?? key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}

export function factToText(value: FactValue): string {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

// Reads an edited fact back, keeping the kind of value it had. An empty
// field removes the fact.
export function textToFact(text: string, original: FactValue): FactValue | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  if (Array.isArray(original)) {
    const items = trimmed
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return items.length > 0 ? items : undefined;
  }
  if (typeof original === "number" && /^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

// The facts worth showing on a card. Inside a role group, the employer,
// title and dates are already in the group's heading.
const ROLE_CONTEXT = new Set(["employer", "client", "title", "start", "end"]);
const DATE_KEYS = new Set(["start", "end", "date"]);

export function isRoleContext(card: ProposedCard, key: string): boolean {
  return card.role_ref !== null && ROLE_CONTEXT.has(key);
}

export function visibleFacts(card: ProposedCard, content: CardContent): [string, string][] {
  return Object.entries(content.facts)
    .filter(([key]) => key !== "use")
    .filter(([key]) => !isRoleContext(card, key))
    .filter(([key]) => !(card.kind === "skill" && key === "skills"))
    .map(([key, value]) => [
      factLabel(key),
      DATE_KEYS.has(key) ? (formatMonth(value) ?? "") : factToText(value),
    ]);
}
