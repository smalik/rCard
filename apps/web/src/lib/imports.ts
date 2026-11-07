// Bringing a resume in: what the browser gets about an import, and the pure
// logic behind the Start, Reading, Check and Approve screens.
//
// The import (the original file, what was read and the person's progress) is
// kept on the server, encrypted with the person's own key. A proposed card
// becomes a card only when the person approves it.

import {
  BODY_MAX,
  type CardContent,
  type CardKind,
  type FactValue,
  HEADLINE_MAX,
  numbersIn,
} from "./cards";

export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
export const MAX_PASTE_CHARS = 60_000;
export const FILENAME_HEADER = "X-Plytos-Filename";

// What the file picker offers: Word, PDF and plain text.
export const ACCEPT_RESUME =
  ".docx,.pdf,.txt,application/pdf,text/plain," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

// Why a picked file can't be read, in words for the person, or null.
export function fileProblem(file: { name: string; size: number }): string | null {
  const name = file.name.toLowerCase();
  if (name.endsWith(".doc")) {
    return "That's an older Word file. Save it as .docx or PDF first, then try again.";
  }
  if (!/\.(docx|pdf|txt)$/.test(name)) return "Plytos can read Word (.docx), PDF and text files.";
  if (file.size > MAX_IMPORT_BYTES) return "Resumes over 5 MB aren't supported.";
  if (file.size === 0) return "The file is empty.";
  return null;
}
// Cards per sitting: start with the strongest few, and do the rest any time.
export const BATCH_SIZE = 10;

export type Severity = "fix" | "improve" | "note";

export type FindingLocation = {
  block: number | null;
  excerpt: string;
  figure: string | null;
};

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

// One line of the resume a card came from, so the person can see its source.
// `picture`: read from a picture in the file (a scanned page, a screenshot).
export type SourceLine = { block: number; page: number | null; text: string; picture: boolean };

// A question about where a card belongs, asked when the checks disagree
// with how the resume was read. The person answers before it's saved.
export type PlaceChoice = { parent_ref: string | null; label: string };
export type Placement = {
  question: string;
  reason: string;
  // Where it sits now comes first.
  choices: PlaceChoice[];
  // Where the reading had it, when Plytos moved it.
  moved_from: string | null;
};

export type Proposal = {
  ref: string;
  kind: CardKind;
  content: CardContent;
  // The proposed card this one sits under: a position's employment, an
  // accomplishment's position. See parentRef for where the person put it.
  parent_ref: string | null;
  role_ref: string | null;
  source_blocks: number[];
  source: SourceLine[];
  needs_check: string[];
  placement: Placement | null;
};

export type Answer = "chosen" | "as_is" | "on_card" | "later";
export type Settlement = {
  answer: Answer;
  value: string | null;
  changed: string[];
};
export type CardState = "approved" | "later" | "dropped";
export type CardDecision = { state: CardState; card_id: string | null };

export type Progress = {
  settled: Record<string, Settlement>;
  cards: Record<string, CardDecision>;
  // Proposed wording after the person's answers, by card ref.
  edits: Record<string, CardContent>;
  // Where the person says a card belongs: the card it sits under, by ref.
  moves: Record<string, string | null>;
};

export type ImportFileInfo = {
  format: "docx" | "pdf" | "text";
  size: number;
  name: string;
  pages: number | null;
  words: number;
};

// One of the person's cards that a proposed card stands for: bringing a resume
// in again carries on the same cards instead of making duplicates.
export type CardMatch = {
  card_id: string;
  // The card's headline now, so the person knows which card it is.
  headline: string;
  // The import says nothing the card doesn't already: approving just links them.
  same: boolean;
};

// For a card that matches one of theirs: save it as that card's next version,
// keep theirs as it is, or make a separate card.
export type MatchChoice = "update" | "keep" | "separate";

export type Review = {
  id: string;
  file: ImportFileInfo;
  cards: Proposal[];
  findings: Finding[];
  // Positions in `findings` of the questions to settle before approving.
  toSettle: number[];
  progress: Progress;
  // Contact details found in the file. They stay in the import, never on cards.
  contactKept: boolean;
  // The model that sorted the resume's lines, or null when the built-in rules did.
  readBy: string | null;
  // The person's cards that proposed cards stand for, by ref.
  matches: Record<string, CardMatch>;
};

// An upload is kept at once and read in the background. While it's read, the
// stage says which part is under way.
export type ImportState = "reading" | "read" | "failed";
export type ReadingStage = "file" | "pictures" | "structure" | "checks";

export type ImportSummary = {
  id: string;
  created_at: string;
  updated_at: string;
  state: ImportState;
  stage: ReadingStage | null;
  file: { format: string; size: number; name: string };
  cards: number;
  approved: number;
  later: number;
  dropped: number;
  to_settle: number;
};

// Where a reading is, as the API says it. error_code is a short word such as
// "unreadable", never anything from the file.
export type ImportStatus = {
  id: string;
  state: ImportState;
  stage: ReadingStage | null;
  error_code: string | null;
  file: { format: string; size: number; name: string };
};

// What the Reading screen polls for: the status, and once it's read, the review.
export type ReadingStatus = ImportStatus & { review: Review | null };

// The stages of a reading, in order, as the person sees them.
export const READING_STAGES: { stage: ReadingStage; label: string }[] = [
  { stage: "file", label: "Opening your file" },
  { stage: "pictures", label: "Reading any pictures and scans" },
  { stage: "structure", label: "Sorting lines into jobs and titles" },
  { stage: "checks", label: "Checking where each line belongs" },
];

// How far a reading has got, from 0 to 1, by the stage it's at. Sorting the
// lines takes longest, so it gets the widest stretch.
const STAGE_SPAN: Record<ReadingStage, [number, number]> = {
  file: [0.04, 0.1],
  pictures: [0.1, 0.22],
  structure: [0.22, 0.48],
  checks: [0.48, 0.6],
};

export function stageSpan(stage: ReadingStage | null): [number, number] {
  return STAGE_SPAN[stage ?? "file"];
}

// Which stages are done, under way, or still to come. A file without pictures
// skips that stage; it shows as done once the reading is past it.
export function stageStates(
  stage: ReadingStage | null,
  read: boolean,
): ("done" | "working" | "pending")[] {
  const at = read ? READING_STAGES.length : READING_STAGES.findIndex((s) => s.stage === (stage ?? "file"));
  return READING_STAGES.map((_, i) => (i < at ? "done" : i === at ? "working" : "pending"));
}

// Why a reading failed, in words for the person.
export function failureText(code: string | null): string {
  if (code === "unreadable") {
    return "Plytos couldn't open that file. If it's a scan or a PDF that won't open, try a Word copy, or paste the text instead.";
  }
  return "Plytos couldn't finish reading it. That's on our side, not your file. Try again in a moment.";
}

export function toStatus(raw: unknown): ImportStatus {
  const status = (raw ?? {}) as Partial<ImportStatus>;
  const state = status.state === "read" || status.state === "failed" ? status.state : "reading";
  const stage = READING_STAGES.some((s) => s.stage === status.stage)
    ? (status.stage as ReadingStage)
    : null;
  return {
    id: String(status.id ?? ""),
    state,
    stage,
    error_code: typeof status.error_code === "string" ? status.error_code : null,
    file: {
      format: status.file?.format ?? "text",
      size: status.file?.size ?? 0,
      name: status.file?.name ?? "resume",
    },
  };
}

// --- Shaping the API's import for the browser ------------------------------

type RawImport = {
  id?: string;
  file?: { format?: string; size?: number; name?: string };
  result?: {
    facts?: { pages?: number | null; word_count?: number };
    contact?: {
      emails?: unknown[];
      phones?: unknown[];
      location?: string | null;
    };
    blocks?: { index: number; text: string; page?: number | null; where?: string }[];
    read_by?: string | null;
    cards?: (Omit<Proposal, "source" | "placement"> & {
      source_blocks?: number[];
      placement?: Placement | null;
    })[];
    findings?: (Omit<Finding, "locations"> & {
      locations?: Partial<FindingLocation>[];
    })[];
  };
  progress?: Partial<Progress>;
  to_settle?: number[];
  matches?: unknown;
};

// Keeps only well-formed matches from the API.
export function toMatches(raw: unknown): Record<string, CardMatch> {
  if (typeof raw !== "object" || raw === null) return {};
  const matches: Record<string, CardMatch> = {};
  for (const [ref, value] of Object.entries(raw as Record<string, unknown>)) {
    const m = value as Partial<CardMatch> | null;
    if (typeof m?.card_id === "string" && typeof m.headline === "string") {
      matches[ref] = { card_id: m.card_id, headline: m.headline, same: m.same === true };
    }
  }
  return matches;
}

function emptyProgress(): Progress {
  return { settled: {}, cards: {}, edits: {}, moves: {} };
}

const OLD_PICTURE_CHECK = "Plytos read this from a picture in your resume. Check the wording.";

// Picks what the screens need from the API's import. Only the lines cards
// came from travel with them; the rest of the text, the contact details and
// the parse stay on the server.
export function toReview(raw: unknown): Review {
  const view = (raw ?? {}) as RawImport;
  const result = view.result ?? {};
  const blocks = new Map((result.blocks ?? []).map((b) => [b.index, b]));
  const format = view.file?.format;
  const contact = result.contact ?? {};
  return {
    id: String(view.id ?? ""),
    file: {
      format: format === "docx" || format === "pdf" ? format : "text",
      size: view.file?.size ?? 0,
      name: view.file?.name ?? "resume",
      pages: result.facts?.pages ?? null,
      words: result.facts?.word_count ?? 0,
    },
    cards: (result.cards ?? []).map((card) => {
      const sourceBlocks = card.source_blocks ?? [];
      return {
        ref: card.ref,
        kind: card.kind,
        content: card.content,
        parent_ref: card.parent_ref ?? null,
        role_ref: card.role_ref ?? null,
        source_blocks: sourceBlocks,
        source: sourceBlocks.flatMap((i) => {
          const block = blocks.get(i);
          if (!block) return [];
          const picture = block.where === "image";
          return [{ block: i, page: block.page ?? null, text: block.text, picture }];
        }),
        // Imports read before scans were checked a page at a time asked on every card.
        needs_check: (card.needs_check ?? []).filter((q) => q !== OLD_PICTURE_CHECK),
        placement: card.placement ?? null,
      };
    }),
    findings: (result.findings ?? []).map((finding) => ({
      rule: finding.rule,
      severity: finding.severity,
      category: finding.category,
      about: finding.about === "cards" ? "cards" : "document",
      title: finding.title,
      detail: finding.detail,
      locations: (finding.locations ?? []).map((loc) => ({
        block: loc.block ?? null,
        excerpt: loc.excerpt ?? "",
        figure: loc.figure ?? null,
      })),
    })),
    toSettle: view.to_settle ?? [],
    progress: { ...emptyProgress(), ...view.progress },
    contactKept:
      (contact.emails?.length ?? 0) > 0 || (contact.phones?.length ?? 0) > 0 || !!contact.location,
    readBy: typeof result.read_by === "string" ? result.read_by : null,
    matches: toMatches(view.matches),
  };
}

// What approving a matched card does, in the person's words.
export function matchNote(match: CardMatch, choice: MatchChoice): string {
  if (choice === "separate") return "Approving makes a separate card. Yours stays as it is.";
  if (match.same) return `It's your card “${match.headline}”. Approving changes nothing on it.`;
  const name = `“${match.headline}”`;
  if (choice === "keep") return `Approving keeps your card ${name} as it is, without this wording.`;
  return (
    `It's your card ${name}. Approving saves this as its next version; ` +
    "the one before stays in its history."
  );
}

// "claude-haiku-5-5" reads as "Claude Haiku 5.5".
export function readerName(readBy: string | null): string | null {
  const m = readBy?.match(/^claude-([a-z]+)-(\d+)(?:-(\d+))?$/);
  if (!m) return readBy;
  const [, family = "", major = "", minor] = m;
  const name = family.charAt(0).toUpperCase() + family.slice(1);
  return `Claude ${name} ${minor ? `${major}.${minor}` : major}`;
}

// --- Progress ---------------------------------------------------------------

export function contentFor(card: Proposal, progress: Progress): CardContent {
  return progress.edits[card.ref] ?? card.content;
}

export function stateOf(ref: string, progress: Progress): CardState | "pending" {
  return progress.cards[ref]?.state ?? "pending";
}

export type SettleState = "settled" | "later" | "open";

export function settleState(index: number, progress: Progress): SettleState {
  const settlement = progress.settled[String(index)];
  if (!settlement) return "open";
  return settlement.answer === "later" ? "later" : "settled";
}

export function settledCount(review: Review): number {
  return review.toSettle.filter((i) => settleState(i, review.progress) === "settled").length;
}

// The figures a "two numbers" question offers, in the order the resume uses them.
export function figureChoices(finding: Finding): string[] {
  return [...new Set(finding.locations.flatMap((loc) => (loc.figure ? [loc.figure] : [])))];
}

export function isFigureQuestion(finding: Finding): boolean {
  return finding.rule === "consistency.figures" && figureChoices(finding).length >= 2;
}

// --- Findings and cards ------------------------------------------------------

function normalize(text: string): string {
  return text.replace(/…$/, "").replace(/\s+/g, " ").trim().toLowerCase();
}

function cardsPerBlock(cards: Proposal[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const card of cards) {
    for (const block of card.source_blocks) counts.set(block, (counts.get(block) ?? 0) + 1);
  }
  return counts;
}

// Whether a finding's location is about this card. When several cards came
// from the same line, the excerpt has to match the card's own words.
function locationMatches(
  card: Proposal,
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

export function cardsForFinding(finding: Finding, cards: Proposal[]): string[] {
  const perBlock = cardsPerBlock(cards);
  return cards
    .filter((card) => finding.locations.some((loc) => locationMatches(card, loc, perBlock)))
    .map((card) => card.ref);
}

// Findings about a card's words, by their position in the import's list.
export function findingsForCard(card: Proposal, review: Review): number[] {
  const perBlock = cardsPerBlock(review.cards);
  const out: number[] = [];
  review.findings.forEach((finding, i) => {
    if (finding.about !== "cards") return;
    if (finding.locations.some((loc) => locationMatches(card, loc, perBlock))) out.push(i);
  });
  return out;
}

// Open questions on a card: facts still to settle, and the import's own guesses.
export function openQuestions(card: Proposal, review: Review): number[] {
  return findingsForCard(card, review).filter(
    (i) => review.toSettle.includes(i) && settleState(i, review.progress) !== "settled",
  );
}

// Wording tips: findings about the card's words that aren't questions of fact.
export function wordingTips(card: Proposal, review: Review): number[] {
  return findingsForCard(card, review).filter((i) => !review.toSettle.includes(i));
}

// --- Ordering cards for review ---------------------------------------------

// How strong a proposed card is as proof: a result with a number beats one
// without, and both come before the frames around them.
export function strength(card: Proposal, content: CardContent): number {
  if (card.kind === "accomplishment") {
    if (content.facts.award !== undefined) return 2;
    return numbersOf(content).length > 0 ? 4 : 3;
  }
  if (card.kind === "project") return 2;
  if (FRAME_KINDS.has(card.kind)) return 1;
  return 0;
}

// The kinds that frame a career: where and as what the person worked.
const FRAME_KINDS = new Set<CardKind>(["employment", "position", "engagement", "role"]);

// --- The career tree ---------------------------------------------------------

// The card a proposal sits under: where the person put it, or where the import did.
export function parentRef(card: Proposal, progress: Progress): string | null {
  return card.ref in progress.moves ? (progress.moves[card.ref] ?? null) : card.parent_ref;
}

// Whether a card still waits on the person to say where it belongs.
export function placementOpen(card: Proposal, progress: Progress): boolean {
  return card.placement !== null && !(card.ref in progress.moves);
}

// The cards a proposal sits under, nearest first.
export function ancestors(card: Proposal, review: Review): Proposal[] {
  const byRef = new Map(review.cards.map((c) => [c.ref, c]));
  const out: Proposal[] = [];
  let ref = parentRef(card, review.progress);
  while (ref) {
    const parent = byRef.get(ref);
    if (!parent || out.includes(parent)) break;
    out.push(parent);
    ref = parentRef(parent, review.progress);
  }
  return out;
}

// Facts a card shows from the cards above it (the employer, the title, the
// dates), nearest first. Its own facts win.
export function factsAbove(card: Proposal, review: Review): Record<string, FactValue> {
  const out: Record<string, FactValue> = {};
  for (const parent of ancestors(card, review)) {
    for (const [key, value] of Object.entries(contentFor(parent, review.progress).facts)) {
      if (!(key in out)) out[key] = value;
    }
  }
  return out;
}

// "Northwind Logistics › Director": where a card sits.
export function pathLabel(card: Proposal, review: Review): string | null {
  const path = ancestors(card, review)
    .reverse()
    .map((c) => contentFor(c, review.progress).framing.headline);
  return path.length > 0 ? path.join(" › ") : null;
}

export type OutlineNode = { card: Proposal; children: OutlineNode[] };

// Every proposal under the ones above it, in resume order.
export function outline(review: Review): OutlineNode[] {
  const refs = new Set(review.cards.map((c) => c.ref));
  const nodes = new Map(review.cards.map((c) => [c.ref, { card: c, children: [] } as OutlineNode]));
  const roots: OutlineNode[] = [];
  for (const card of review.cards) {
    const node = nodes.get(card.ref)!;
    const above = parentRef(card, review.progress);
    const parent = above && refs.has(above) ? nodes.get(above) : null;
    (parent ? parent.children : roots).push(node);
  }
  return roots;
}

// Cards still to review. A card comes after the one it sits under, so each
// employer comes first, then its titles, then what was done in each, strongest
// first. Cards set aside for later come last.
export function reviewQueue(review: Review): string[] {
  const order: Proposal[] = [];
  const visit = (nodes: OutlineNode[]) => {
    const ranked = nodes
      .map((node, index) => ({ node, index }))
      .sort(
        (a, b) =>
          strength(b.node.card, contentFor(b.node.card, review.progress)) -
            strength(a.node.card, contentFor(a.node.card, review.progress)) ||
          a.index - b.index,
      );
    for (const { node } of ranked) {
      order.push(node.card);
      visit(node.children);
    }
  };
  // Frames go first among the roots so the career's outline is settled before
  // anything is placed in it; loose cards follow, strongest first.
  const roots = outline(review);
  visit(roots.filter((n) => FRAME_KINDS.has(n.card.kind)));
  visit(roots.filter((n) => !FRAME_KINDS.has(n.card.kind)));
  const waiting = order.filter((c) => {
    const state = stateOf(c.ref, review.progress);
    return state === "pending" || state === "later";
  });
  return [
    ...waiting.filter((c) => stateOf(c.ref, review.progress) === "pending"),
    ...waiting.filter((c) => stateOf(c.ref, review.progress) === "later"),
  ].map((c) => c.ref);
}

// --- Summaries for the screens ---------------------------------------------

// The numbers a card's words cite.
function numbersOf(content: CardContent): string[] {
  return numbersIn(`${content.framing.headline} ${content.framing.body}`);
}

function yearOf(value: FactValue | undefined): number | null {
  if (typeof value !== "string") return null;
  if (value === "present") return new Date().getFullYear();
  const match = /^(\d{4})/.exec(value);
  return match ? Number(match[1]) : null;
}

export type Overview = {
  things: number;
  accomplishments: number;
  withNumbers: number;
  roles: number;
  employers: number;
  years: [number, number] | null;
  dateQuestions: number;
  figureQuestions: number;
  repeatQuestions: number;
  skills: number;
  wordingTips: number;
  documentNotes: number;
  open: number;
  pending: number;
  approved: number;
};

export function overview(review: Review): Overview {
  const content = (card: Proposal) => contentFor(card, review.progress);
  const accomplishments = review.cards.filter(
    (c) => c.kind === "accomplishment" && content(c).facts.award === undefined,
  );
  const roles = review.cards.filter(
    (c) => c.kind === "position" || c.kind === "engagement" || c.kind === "role",
  );
  const years = review.cards
    .filter((c) => c.kind === "employment" || c.kind === "role")
    .flatMap((c) => [yearOf(c.content.facts.start), yearOf(c.content.facts.end)])
    .filter((y): y is number => y !== null);
  const open = (rule: (r: string) => boolean) =>
    review.toSettle.filter(
      (i) => rule(review.findings[i]!.rule) && settleState(i, review.progress) !== "settled",
    ).length;
  const states = review.cards.map((c) => stateOf(c.ref, review.progress));
  return {
    things: review.cards.length,
    accomplishments: accomplishments.length,
    withNumbers: accomplishments.filter((c) => numbersOf(content(c)).length > 0).length,
    roles: roles.length,
    employers: review.cards.filter((c) => c.kind === "employment").length,
    years: years.length > 0 ? [Math.min(...years), Math.max(...years)] : null,
    dateQuestions: open((r) => r.startsWith("dates.")),
    figureQuestions: open((r) => r === "consistency.figures"),
    repeatQuestions: open((r) => r === "content.duplicates"),
    skills: review.cards
      .filter((c) => c.kind === "skill")
      .reduce((n, c) => {
        const skills = c.content.facts.skills;
        return n + (Array.isArray(skills) ? skills.length : 1);
      }, 0),
    wordingTips: review.findings.filter(
      (f, i) => f.about === "cards" && !review.toSettle.includes(i),
    ).length,
    documentNotes: review.findings.filter((f) => f.about === "document").length,
    open: review.toSettle.filter((i) => settleState(i, review.progress) !== "settled").length,
    pending: states.filter((s) => s === "pending" || s === "later").length,
    approved: states.filter((s) => s === "approved").length,
  };
}

export type FoundRow = { label: string; detail?: string; count: number | null };

export const FOUND_LABELS = [
  "Jobs and roles",
  "Dates",
  "Accomplishments",
  "Skills",
  "Education and credentials",
  "Checking numbers and dates",
] as const;

// What the Reading screen lists as it reads, from what the import found.
export function foundRows(review: Review): FoundRow[] {
  const o = overview(review);
  const education = review.cards.filter(
    (c) => c.kind === "education" || c.kind === "credential",
  ).length;
  const [roles, dates, accomplishments, skills, schooling, checks] = FOUND_LABELS;
  return [
    { label: roles, count: o.roles },
    { label: dates, count: null },
    { label: accomplishments, count: o.accomplishments },
    {
      label: skills,
      detail: "Grouped the way your resume lists them",
      count: o.skills,
    },
    { label: schooling, count: education },
    { label: checks, count: null },
  ];
}

// A few cards to show while reading: a role, two results and a skill.
export function foundSoFar(review: Review): Proposal[] {
  const role = review.cards.find((c) => c.kind === "position" || c.kind === "role");
  const results = review.cards
    .filter((c) => c.kind === "accomplishment")
    .sort((a, b) => strength(b, b.content) - strength(a, a.content))
    .slice(0, 2);
  const skill = review.cards.find((c) => c.kind === "skill");
  return [role, ...results, skill].filter((c): c is Proposal => c !== undefined);
}

// --- Words on a card ---------------------------------------------------------

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
  const end = formatMonth(facts.end ?? facts.date);
  if (start && end) return `${start} – ${end}`;
  return start ?? end;
}

function text(value: FactValue | undefined): string | null {
  if (value === undefined) return null;
  const out = Array.isArray(value) ? value.join(", ") : String(value);
  return out || null;
}

// Where a card sits: "Meridian Group · 2021", or for a result, "Director,
// Meridian Group · 2021". `above` holds the facts of the cards above it.
export function cardPlace(
  content: CardContent,
  above: Record<string, FactValue> = {},
): string | null {
  const facts = { ...above, ...content.facts };
  const where = text(facts.client) ?? text(facts.employer) ?? text(facts.institution);
  const title = content.facts.title === undefined ? text(above.title) : null;
  const year = yearOf(facts.start ?? facts.date ?? facts.end);
  const parts = [
    [title, where].filter(Boolean).join(", ") || null,
    year ? String(year) : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export type FactRow = {
  key: string;
  label: string;
  value: string;
  note?: string;
  // Shown from a card above this one; it changes there, not here.
  above?: boolean;
};

// The facts the front of a card shows, in the order a reader wants them.
// `above` holds the facts of the cards it sits under.
export function factRows(
  card: Proposal,
  content: CardContent,
  above: Record<string, FactValue> = {},
): FactRow[] {
  const f = content.facts;
  const rows: FactRow[] = [];
  const add = (key: string, label: string, value: string | null, extra: Partial<FactRow> = {}) => {
    if (value) rows.push({ key, label, value, ...extra });
  };
  const inherited = { above: true, note: "From the card above" };
  if (card.kind === "skill") {
    add("category", "Group", text(f.category));
    add("skills", "Skills", text(f.skills));
    return rows;
  }
  if (card.kind === "education") {
    add("institution", "School", text(f.institution));
    add("degree", "Degree", text(f.degree));
    add("date", "Date", formatMonth(f.date));
    return rows;
  }
  if (card.kind === "credential") {
    add("name", "Credential", text(f.name));
    add("date", "Date", formatMonth(f.date));
    return rows;
  }
  if (card.kind === "employment") {
    add("employer", "Employer", text(f.employer));
    add("dates", "Tenure", dateSpan(f), {
      note: f.tenure === "from positions" ? "Worked out from your titles" : undefined,
    });
    add("location", "Location", text(f.location));
    add("employment_type", "Type", text(f.employment_type));
    return rows;
  }
  if (card.kind === "position") {
    add("employer", "At", text(above.employer), inherited);
    add("title", "Official title", text(f.title), { note: text(f.plain_title) ?? undefined });
    add("dates", "Dates", dateSpan(f));
    add("location", "Location", text(f.location));
    add("employment_type", "Type", text(f.employment_type));
    return rows;
  }
  if (card.kind === "engagement") {
    add("client", "Client", text(f.client));
    add("employer", "Through", text(above.employer), inherited);
    add("title", "Title", text(f.title));
    add("dates", "Dates", dateSpan(f));
    return rows;
  }
  if (card.kind === "accomplishment" && Object.keys(above).length > 0) {
    const where = [text(above.title), text(above.client) ?? text(above.employer)]
      .filter(Boolean)
      .join(", ");
    add("under", "Under", where || null, inherited);
    add("dates", "When", dateSpan(above), inherited);
  }
  if (f.client) {
    add("client", "Client", text(f.client));
    add("employer", "Through", text(f.employer));
  } else {
    add("employer", "Employer", text(f.employer));
  }
  add("title", "Official title", text(f.title), {
    note: text(f.plain_title) ?? undefined,
  });
  add("dates", "Dates", dateSpan(f));
  if (card.kind === "role") {
    add("location", "Location", text(f.location));
    add("employment_type", "Type", text(f.employment_type));
  }
  add("workstream", "Workstream", text(f.workstream));
  add("award", "Award", text(f.award));
  if (card.kind === "accomplishment") {
    add("outcome", "Result", text(f.outcome));
    add("scope", "Scope", text(f.scope));
    add("skills", "Skills", text(f.skills));
  }
  return rows;
}

// Splits a line around the first place it quotes `needle`, for highlighting.
export function highlight(line: string, needle: string): [string, string, string] {
  const clean = needle.replace(/…$/, "").trim();
  if (!clean) return [line, "", ""];
  const at = line.toLowerCase().indexOf(clean.toLowerCase());
  if (at < 0) return [line, "", ""];
  return [line.slice(0, at), line.slice(at, at + clean.length), line.slice(at + clean.length)];
}

// Where a quoted line sits: "Line 14 · Meridian Group" or "Page 2 · ...".
export function lineLabel(review: Review, block: number | null): string {
  const card = review.cards.find((c) => block !== null && c.source_blocks.includes(block));
  const page = card?.source.find((s) => s.block === block)?.page ?? null;
  const where = card ? cardPlace(card.content)?.split(" · ")[0] : null;
  const position = page ? `Page ${page}` : block !== null ? `Line ${block + 1}` : "Your resume";
  return where ? `${position} · ${where}` : position;
}

// --- Editing --------------------------------------------------------------------

const FACT_LABELS: Record<string, string> = {
  title: "Official title",
  plain_title: "Plain-language title",
  employer: "Employer",
  client: "Client",
  agency: "Agency",
  start: "Start",
  end: "End",
  location: "Location",
  employment_type: "Employment type",
  role_type: "Role type",
  workstream: "Workstream",
  outcome: "Result",
  scope: "Scope",
  award: "Award",
  date: "Date",
  name: "Name",
  institution: "School",
  degree: "Degree",
  category: "Group",
  skills: "Skills",
  use: "Used as",
};

export const FACT_HINTS: Record<string, string> = {
  start: "Year and month, like 2021-03",
  end: "Year and month, or present",
  date: "Year and month, like 2021-03",
  skills: "Separate with commas",
  scope: "Separate with commas",
};

export function factLabel(key: string): string {
  return FACT_LABELS[key] ?? key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}

export function factToText(value: FactValue): string {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

// Reads an edited fact back, keeping the kind of value it had. An empty
// field removes the fact.
export function textToFact(input: string, original: FactValue): FactValue | undefined {
  const trimmed = input.trim();
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

// Facts the person can edit on a card. "use" is bookkeeping, not a fact.
export function editableFacts(content: CardContent): [string, FactValue][] {
  return Object.entries(content.facts).filter(([key]) => key !== "use");
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

export function cleanContent(content: CardContent): CardContent {
  return {
    facts: content.facts,
    framing: { ...content.framing, headline: content.framing.headline.trim() },
  };
}

// --- Audit list -------------------------------------------------------------------

const SEVERITY_ORDER: Record<Severity, number> = {
  fix: 0,
  improve: 1,
  note: 2,
};

export function bySeverity(findings: Finding[]): { finding: Finding; index: number }[] {
  return findings
    .map((finding, index) => ({ finding, index }))
    .sort(
      (a, b) =>
        SEVERITY_ORDER[a.finding.severity] - SEVERITY_ORDER[b.finding.severity] ||
        a.index - b.index,
    );
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  fix: "Fix",
  improve: "Improve",
  note: "Note",
};

export function minutesFor(cards: number): number {
  return Math.max(1, Math.round(cards * 0.8));
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
