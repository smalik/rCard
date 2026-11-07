// "Your resume, rebuilt": the person's resume rebuilt from the cards Plytos
// read, beside their own file, so one glance says "yes, that's me". Each line
// on one side has a partner on the other: a card's lines in the file, or, for
// a line of the file, the cards it went into. A line on no card says where it
// went instead (a heading, the contact details, a page number left off), so
// every line is accounted for.
//
// Everything here is worked out from the import and the person's progress;
// nothing is asked of a model.

import type { CardContent, CardKind } from "./cards";
import {
  type Answer,
  cardsForFinding,
  contentFor,
  dateSpan,
  type Finding,
  isFigureQuestion,
  outline,
  type OutlineNode,
  parentRef,
  placementOpen,
  plural,
  type Proposal,
  type Review,
  stateOf,
  toReview,
} from "./imports";
import {
  isFrame,
  lineText,
  type ReviewGroup,
  SECTION_NAMES,
  settleQuestion,
  settleReplies,
  undecided,
  withLineText,
} from "./review";

// -- the person's file, line by line -------------------------------------------

export type SkipReason = "page_number" | "page_header" | "decoration" | "references" | "marking";

// Where a line sits on its page, as fractions of the page: left, top, right, bottom.
export type Box = [number, number, number, number];

export type FileLine = {
  block: number;
  page: number | null;
  text: string;
  bullet: boolean;
  bold: boolean;
  caps: boolean;
  // Read from a picture in the file (a scan, a screenshot of bullets).
  picture: boolean;
  box: Box | null;
};

export type FileSection = {
  kind: string;
  heading: string | null;
  headingBlock: number | null;
  blocks: number[];
};

export type ResumeFile = {
  format: "docx" | "pdf" | "text";
  lines: FileLine[];
  // A PDF's pages, each as width and height in inches.
  pages: { number: number; width: number; height: number }[];
  sections: FileSection[];
  // Where the lines on no card went.
  contact: number[];
  headings: number[];
  skipped: Record<number, SkipReason>;
};

type RawBlock = {
  index?: number;
  text?: string;
  is_bullet?: boolean;
  bold?: boolean;
  all_caps?: boolean;
  where?: string;
  page?: number | null;
  box?: unknown;
};

type RawResult = {
  facts?: { format?: string; page_sizes?: unknown };
  blocks?: RawBlock[];
  sections?: { kind?: string; heading?: string | null; heading_block?: number | null; blocks?: number[] }[];
  contact?: { blocks?: number[] };
  roles?: { subheading_blocks?: number[] }[];
  lines?: {
    contact?: number[];
    headings?: number[];
    skipped?: { block?: number; reason?: string }[];
  } | null;
};

const SKIP_REASONS = new Set<string>(["page_number", "page_header", "decoration", "references", "marking"]);

function toBox(value: unknown): Box | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const [left, top, right, bottom] = value as unknown[];
  const nums = [left, top, right, bottom];
  if (!nums.every((n) => typeof n === "number" && n >= 0 && n <= 1)) return null;
  const box = nums as Box;
  return box[0] < box[2] && box[1] < box[3] ? box : null;
}

function numbers(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((n): n is number => Number.isInteger(n)) : [];
}

// The file as the import read it: every line, in reading order, and where the
// ones on no card went.
export function toResumeFile(raw: unknown): ResumeFile {
  const view = (raw ?? {}) as { file?: { format?: string }; result?: RawResult | null };
  const result = view.result ?? {};
  const format = view.file?.format ?? result.facts?.format;
  const lines: FileLine[] = (result.blocks ?? []).flatMap((b) =>
    typeof b.index === "number" && typeof b.text === "string"
      ? [
          {
            block: b.index,
            page: typeof b.page === "number" ? b.page : null,
            text: b.text,
            bullet: b.is_bullet === true,
            bold: b.bold === true,
            caps: b.all_caps === true,
            picture: b.where === "image",
            box: toBox(b.box),
          },
        ]
      : [],
  );
  const sizes = Array.isArray(result.facts?.page_sizes) ? (result.facts.page_sizes as unknown[]) : [];
  const pages = sizes.flatMap((size, i) => {
    if (!Array.isArray(size) || size.length !== 2) return [];
    const [width, height] = size as unknown[];
    if (typeof width !== "number" || typeof height !== "number" || width <= 0 || height <= 0) {
      return [];
    }
    return [{ number: i + 1, width, height }];
  });
  const sections: FileSection[] = (result.sections ?? []).map((s) => ({
    kind: s.kind ?? "other",
    heading: typeof s.heading === "string" && s.heading.trim() ? s.heading.trim() : null,
    headingBlock: typeof s.heading_block === "number" ? s.heading_block : null,
    blocks: numbers(s.blocks),
  }));
  // Imports read before every line was accounted for say less; the headings
  // and contact details still show where they went.
  const account = result.lines ?? null;
  const headings = account?.headings
    ? numbers(account.headings)
    : [
        ...sections.flatMap((s) => (s.headingBlock !== null ? [s.headingBlock] : [])),
        ...(result.roles ?? []).flatMap((r) => numbers(r.subheading_blocks)),
      ];
  const contact = account?.contact ? numbers(account.contact) : numbers(result.contact?.blocks);
  const skipped: Record<number, SkipReason> = {};
  for (const s of account?.skipped ?? []) {
    if (typeof s.block === "number" && typeof s.reason === "string" && SKIP_REASONS.has(s.reason)) {
      skipped[s.block] = s.reason as SkipReason;
    }
  }
  return {
    format: format === "docx" || format === "pdf" ? format : "text",
    lines,
    pages,
    sections,
    contact,
    headings,
    skipped,
  };
}

// Whether the file can be shown as pictures of its pages, each typed line lit
// up where it sits. A scanned page shows too, with what was read from it
// listed under it. A PDF read before lines kept their places is shown line by
// line.
export function showsPages(file: ResumeFile): boolean {
  if (file.format !== "pdf" || file.pages.length === 0) return false;
  return file.lines.filter((l) => !l.picture).every((l) => l.box !== null);
}

// -- where each line went ---------------------------------------------------------

export type Fate =
  | { kind: "cards"; refs: string[] }
  | { kind: "heading" }
  | { kind: "contact" }
  | { kind: "skipped"; reason: SkipReason }
  // Nothing claimed it. Imports read since every line was accounted for have none.
  | { kind: "loose" };

// The cards each line of the file went into, in the order they're shown.
export function cardsByLine(review: Review): Map<number, string[]> {
  const out = new Map<number, string[]>();
  for (const card of review.cards) {
    for (const block of card.source_blocks) {
      const refs = out.get(block) ?? [];
      if (!refs.includes(card.ref)) refs.push(card.ref);
      out.set(block, refs);
    }
  }
  return out;
}

export function fateOf(block: number, file: ResumeFile, byLine: Map<number, string[]>): Fate {
  const refs = byLine.get(block);
  if (refs && refs.length > 0) return { kind: "cards", refs };
  if (file.headings.includes(block)) return { kind: "heading" };
  if (file.contact.includes(block)) return { kind: "contact" };
  const reason = file.skipped[block];
  if (reason) return { kind: "skipped", reason };
  return { kind: "loose" };
}

const SKIPPED_WORDS: Record<SkipReason, string> = {
  page_number: "A page number. Left off, since a card doesn't need one.",
  page_header: "Printed again at the top or foot of a page. Left off as a repeat.",
  decoration: "A divider or decoration, with no words to keep.",
  references: "“References available on request”. Left off, since it goes without saying.",
  marking: "A label your organization's tools added to the file. Left off.",
};

// What happened to a line on no card, in plain words.
export function fateText(fate: Fate): string | null {
  if (fate.kind === "heading") return "A heading. It names the part of your resume below it.";
  if (fate.kind === "contact") {
    return "Your contact details. Kept with this import for your resumes, never on a card.";
  }
  if (fate.kind === "skipped") return SKIPPED_WORDS[fate.reason];
  if (fate.kind === "loose") return "Plytos couldn't place this line. It's on no card yet.";
  return null;
}

export type Coverage = {
  lines: number;
  onCards: number;
  headings: number;
  contact: number;
  skipped: number;
  loose: number[];
};

export function coverage(file: ResumeFile, review: Review): Coverage {
  const byLine = cardsByLine(review);
  const out: Coverage = { lines: file.lines.length, onCards: 0, headings: 0, contact: 0, skipped: 0, loose: [] };
  for (const line of file.lines) {
    const fate = fateOf(line.block, file, byLine);
    if (fate.kind === "cards") out.onCards += 1;
    else if (fate.kind === "heading") out.headings += 1;
    else if (fate.kind === "contact") out.contact += 1;
    else if (fate.kind === "skipped") out.skipped += 1;
    else out.loose.push(line.block);
  }
  return out;
}

// "Every one of your 47 lines is here." The promise the screen leads with.
export function coverageText(c: Coverage): string {
  if (c.lines === 0) return "Your file had no lines to read.";
  if (c.loose.length === 0) {
    return c.lines === 1 ? "Your one line is here." : `Every one of your ${c.lines} lines is here.`;
  }
  const here = c.lines - c.loose.length;
  return `${here} of your ${c.lines} lines are here. ${plural(c.loose.length, "line")} Plytos couldn't place ${c.loose.length === 1 ? "is" : "are"} marked in your file.`;
}

// "40 on cards, 4 headings, your contact details, 1 left off on purpose."
export function coverageDetail(c: Coverage): string {
  const parts = [
    `${c.onCards} on cards`,
    c.headings > 0 ? plural(c.headings, "heading") : "",
    c.contact > 0 ? "your contact details" : "",
    c.skipped > 0 ? `${c.skipped} left off on purpose` : "",
  ].filter(Boolean);
  return parts.join(", ");
}

// -- the resume, rebuilt from cards -----------------------------------------------

export type RebuiltRow = {
  ref: string;
  kind: CardKind;
  // 0 for an employer or a section's own line, 1 for a title, 2 for what was done in it.
  depth: number;
  text: string;
  // A job's or title's dates, a degree's year.
  dates: string | null;
  // An employer's place.
  place: string | null;
  blocks: number[];
  state: ReturnType<typeof stateOf>;
  // The workstream a run of lines sits under inside a job ("Pricing"), on the
  // first line of the run, with its heading's line in the file when there is one.
  label: { name: string; block: number | null } | null;
};

export type RebuiltGroup = {
  key: string;
  kind: "job" | "section";
  // How the person knows it: the employer, or the section's name.
  name: string;
  rows: RebuiltRow[];
  // The cards behind it, each after the one it sits under, to keep it in one go.
  group: ReviewGroup;
};

export type RebuiltSection = {
  key: string;
  heading: string;
  headingBlock: number | null;
  groups: RebuiltGroup[];
};

const SECTION_KINDS: Partial<Record<string, string>> = {
  summary: "Summary",
  objective: "Objective",
  highlights: "Highlights",
  experience: "Experience",
  education: "Education",
  skills: "Skills",
  certifications: "Certifications",
  projects: "Projects",
  awards: "Awards",
  publications: "Publications",
  volunteer: "Volunteering",
  affiliations: "Memberships",
  languages: "Languages",
  interests: "Interests",
};

// A heading as it reads in a sentence: "PROFESSIONAL EXPERIENCE" says
// "Professional experience".
export function speakable(heading: string): string {
  const letters = heading.replace(/[^A-Za-z]/g, "");
  if (letters && letters === letters.toUpperCase()) {
    const lower = heading.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }
  return heading;
}

function flatten(nodes: OutlineNode[], depth: number): { card: Proposal; depth: number }[] {
  return nodes.flatMap((node) => [{ card: node.card, depth }, ...flatten(node.children, depth + 1)]);
}

// Where a card starts in the file: its own first line, or, for one with no
// line of its own, the first line under it. A job sits where its employer's
// line is, even when a line from elsewhere (a highlight up top) was moved
// under it.
function firstLine(node: OutlineNode): number {
  if (node.card.source_blocks.length > 0) return Math.min(...node.card.source_blocks);
  return Math.min(Infinity, ...node.children.map(firstLine));
}

// Which section of the file a line sits in: the one listing it, else the last
// heading above it.
function sectionOf(block: number, file: ResumeFile): number {
  const listed = file.sections.findIndex((s) => s.blocks.includes(block) || s.headingBlock === block);
  if (listed >= 0) return listed;
  let found = -1;
  file.sections.forEach((s, i) => {
    if (s.headingBlock !== null && s.headingBlock <= block) found = i;
  });
  return found;
}

// A line as the rebuilt resume shows it. A group of skills reads as its list,
// named when it's more than "Skills".
export function rowText(card: Proposal, content: CardContent): string {
  if (card.kind === "skill" && content.framing.body.trim()) {
    const name = content.framing.headline.trim();
    const list = content.framing.body.trim();
    return /^(skills?|technical skills|core skills)$/i.test(name) ? list : `${name}: ${list}`;
  }
  return lineText(content);
}

// A card in the person's words, as they reworded its line.
export function reworded(card: Proposal, content: CardContent, text: string): CardContent {
  if (card.kind === "skill" && content.framing.body.trim()) {
    const named = text.match(/^([^:]{1,60}):\s*(.+)$/);
    const list = (named ? named[2]! : text).trim();
    const skills = list.split(",").map((s) => s.trim()).filter(Boolean);
    return {
      ...content,
      facts: { ...content.facts, skills },
      framing: { ...content.framing, headline: named ? named[1]!.trim() : content.framing.headline, body: list },
    };
  }
  return withLineText(content, text);
}

function row(card: Proposal, depth: number, review: Review): RebuiltRow {
  const content = contentFor(card, review.progress);
  const facts = content.facts;
  const frame = isFrame(card.kind);
  const place = typeof facts.location === "string" && facts.location ? facts.location : null;
  const text = rowText(card, content);
  const dates = frame || card.kind === "education" || card.kind === "credential" ? dateSpan(facts) : null;
  return {
    ref: card.ref,
    kind: card.kind,
    depth,
    text,
    // A degree's year written into its line isn't said twice.
    dates: dates && !text.includes(dates) ? dates : null,
    place: card.kind === "employment" ? place : null,
    blocks: card.source_blocks,
    state: stateOf(card.ref, review.progress),
    label: null,
  };
}

// Labels each run of lines that share a workstream, as the file grouped them.
function labelled(rows: RebuiltRow[], cards: Proposal[], review: Review, file: ResumeFile): RebuiltRow[] {
  const byRef = new Map(cards.map((c) => [c.ref, c]));
  let last: string | null = null;
  return rows.map((r) => {
    const card = byRef.get(r.ref);
    if (!card || isFrame(card.kind)) {
      last = null;
      return r;
    }
    const value = contentFor(card, review.progress).facts.workstream;
    const name = typeof value === "string" && value.trim() ? value.trim() : null;
    if (name === null || name === last) {
      last = name;
      return r;
    }
    last = name;
    const heading = file.lines.find(
      (l) => file.headings.includes(l.block) && l.text.trim().toLowerCase() === name.toLowerCase(),
    );
    return { ...r, label: { name, block: heading?.block ?? null } };
  });
}

// The resume rebuilt from its cards, in the file's own order and under its own
// headings: each job with its titles and what was done in them, then each
// other section as one group.
export function rebuild(review: Review, file: ResumeFile): RebuiltSection[] {
  const roots = outline(review);
  type Placed = { node: OutlineNode; section: number; first: number };
  const placed: Placed[] = roots.map((node) => {
    const first = firstLine(node);
    return { node, first, section: Number.isFinite(first) ? sectionOf(first, file) : -1 };
  });
  // Sections in the file's order; cards before any heading (a summary at the
  // top, say) come first, under a name for what they are.
  const order = [...new Set(placed.map((p) => p.section))].sort((a, b) => {
    const at = (s: number) => (s < 0 ? -1 : Math.min(...placed.filter((p) => p.section === s).map((p) => p.first)));
    return at(a) - at(b);
  });
  const sections: RebuiltSection[] = [];
  for (const index of order) {
    const here = placed.filter((p) => p.section === index).sort((a, b) => a.first - b.first);
    const fileSection = index >= 0 ? file.sections[index] : undefined;
    const groups: RebuiltGroup[] = [];
    const loose = here.filter((p) => !isFrame(p.node.card.kind));
    const key = `section-${index}`;
    const heading =
      fileSection?.heading ??
      SECTION_KINDS[fileSection?.kind ?? ""] ??
      SECTION_NAMES[loose[0]?.node.card.kind ?? "story"] ??
      "More";
    for (const p of here) {
      if (!isFrame(p.node.card.kind)) continue;
      const cards = flatten([p.node], 0);
      const root = p.node.card;
      groups.push({
        key: root.ref,
        kind: "job",
        name: contentFor(root, review.progress).framing.headline,
        rows: labelled(
          cards.map(({ card, depth }) => row(card, depth, review)),
          cards.map((c) => c.card),
          review,
          file,
        ),
        group: { key: root.ref, kind: "job", root, cards: cards.map((c) => c.card) },
      });
    }
    if (loose.length > 0) {
      const cards = loose.flatMap((p) => flatten([p.node], 0));
      const group: RebuiltGroup = {
        key,
        kind: "section",
        name: speakable(heading),
        rows: cards.map(({ card, depth }) => row(card, depth, review)),
        group: { key, kind: "rest", root: null, cards: cards.map((c) => c.card) },
      };
      // A section's own lines sit where they were written: before the jobs
      // when they came first (a line about the whole section), else after.
      const before = loose[0]!.first < (here.find((p) => isFrame(p.node.card.kind))?.first ?? Infinity);
      if (before) groups.unshift(group);
      else groups.push(group);
    }
    sections.push({
      key,
      heading,
      headingBlock: fileSection?.headingBlock ?? null,
      groups,
    });
  }
  return sections;
}

// -- partners -------------------------------------------------------------------

// The file's lines a rebuilt line came from.
export function linesOf(ref: string, review: Review): number[] {
  return review.cards.find((c) => c.ref === ref)?.source_blocks ?? [];
}

// -- how sure Plytos is, and what it asks -------------------------------------------

export type Choice = {
  label: string;
  // What answering with it sends.
  answer: { kind: "settle"; index: number; answer: Answer; value: string | null } | {
    kind: "place";
    ref: string;
    parentRef: string | null;
  };
};

export type Question = {
  key: string;
  // The card it's asked at, in the rebuilt resume.
  ref: string;
  // Every card it's about. A job holding any of them isn't sure until it's
  // answered, and marking that job goes with Plytos's pick.
  refs: string[];
  prompt: string;
  // Why it's asked, in a line.
  why: string | null;
  // The file's lines it's about.
  blocks: number[];
  choices: Choice[];
  // Plytos's pick, as a position in `choices`. One tap on it accepts it.
  picked: number;
  // The person's answer, as a position in `choices`, when they've given one.
  answered: number | null;
};

function figureCounts(finding: Finding): Map<string, number> {
  const counts = new Map<string, number>();
  for (const loc of finding.locations) {
    if (loc.figure) counts.set(loc.figure, (counts.get(loc.figure) ?? 0) + 1);
  }
  return counts;
}

function settleChoices(index: number, finding: Finding): { choices: Choice[]; picked: number } {
  const replies = settleReplies(finding).filter((r) => r.answer !== "later");
  const choices: Choice[] = replies.map((r) => ({
    label: r.label,
    answer: { kind: "settle", index, answer: r.answer, value: r.value },
  }));
  let picked = 0;
  if (isFigureQuestion(finding)) {
    // The number the resume uses most; the first it uses when that's a tie.
    const counts = figureCounts(finding);
    let best = -1;
    replies.forEach((r, i) => {
      const n = r.value ? (counts.get(r.value) ?? 0) : 0;
      if (n > best) {
        best = n;
        picked = i;
      }
    });
  }
  return { choices, picked };
}

function answeredSettle(index: number, choices: Choice[], review: Review): number | null {
  const settled = review.progress.settled[String(index)];
  if (!settled || settled.answer === "later") return null;
  const at = choices.findIndex(
    (c) =>
      c.answer.kind === "settle" &&
      c.answer.answer === settled.answer &&
      (c.answer.value === null || c.answer.value === settled.value),
  );
  return at >= 0 ? at : null;
}

// Every question Plytos asks about this import, each at the first card it's
// about, with an answer already picked.
export function questions(review: Review): Question[] {
  const out: Question[] = [];
  for (const card of review.cards) {
    const placement = card.placement;
    if (placement === null) continue;
    const choices: Choice[] = placement.choices.map((c) => ({
      label: c.label,
      answer: { kind: "place", ref: card.ref, parentRef: c.parent_ref },
    }));
    let answered: number | null = null;
    if (card.ref in review.progress.moves) {
      const to = review.progress.moves[card.ref] ?? null;
      answered = choices.findIndex((c) => c.answer.kind === "place" && c.answer.parentRef === to);
      if (answered < 0) {
        // Moved somewhere Plytos didn't suggest: that's the person's answer.
        choices.push({ label: placeName(to, review), answer: { kind: "place", ref: card.ref, parentRef: to } });
        answered = choices.length - 1;
      }
    }
    out.push({
      key: `place-${card.ref}`,
      ref: card.ref,
      refs: [card.ref],
      prompt: placement.question,
      why: placement.reason || null,
      blocks: card.source_blocks,
      choices,
      picked: 0,
      answered,
    });
  }
  for (const index of review.toSettle) {
    const finding = review.findings[index];
    if (!finding) continue;
    const refs = cardsForFinding(finding, review.cards);
    const ref = refs[0];
    if (!ref) continue;
    const { choices, picked } = settleChoices(index, finding);
    out.push({
      key: `settle-${index}`,
      ref,
      refs,
      prompt: settleQuestion(finding),
      why: finding.title,
      blocks: finding.locations.flatMap((l) => (l.block !== null ? [l.block] : [])),
      choices,
      picked,
      answered: answeredSettle(index, choices, review),
    });
  }
  return out;
}

// The questions about anything in a group, answered or not, wherever they're
// asked.
export function groupQuestions(group: RebuiltGroup, all: Question[]): Question[] {
  const refs = new Set(group.rows.map((r) => r.ref));
  return all.filter((q) => q.refs.some((ref) => refs.has(ref)));
}

// Whether Plytos is sure of a group as it stands: nothing in it is asked about
// or was guessed, and none of it was read from a picture. Those come
// already marked "Looks right"; the person needs only glance at them.
export function isSure(group: RebuiltGroup, review: Review, all: Question[]): boolean {
  if (groupQuestions(group, all).some((q) => q.answered === null)) return false;
  return group.group.cards.every(
    (card) =>
      !placementOpen(card, review.progress) &&
      card.needs_check.length === 0 &&
      !card.source.some((s) => s.picture),
  );
}

// Whether every card in a group has been decided (kept or left out), so
// there's nothing left to confirm.
export function isSettled(group: RebuiltGroup, review: Review): boolean {
  return undecided(group.group, review).length === 0;
}

// -- moving a line ----------------------------------------------------------------

const PARENT_KINDS: Partial<Record<CardKind, CardKind[]>> = {
  position: ["employment"],
  engagement: ["employment", "position"],
  project: ["employment", "position", "engagement"],
  accomplishment: ["employment", "position", "engagement", "project"],
};

// Whether a card can be moved under another, as the API allows.
export function canMoveUnder(card: Proposal, parent: Proposal): boolean {
  return card.ref !== parent.ref && (PARENT_KINDS[card.kind] ?? []).includes(parent.kind);
}

// Where a line can be moved to: every job and title it could sit under, other
// than where it is, as the person knows them.
export function moveTargets(card: Proposal, review: Review): { ref: string; label: string }[] {
  if (stateOf(card.ref, review.progress) === "approved") return [];
  const here = parentRef(card, review.progress);
  return review.cards
    .filter(
      (c) =>
        c.ref !== here &&
        canMoveUnder(card, c) &&
        stateOf(c.ref, review.progress) !== "dropped" &&
        !isUnder(c, card, review),
    )
    .map((c) => ({ ref: c.ref, label: placeName(c.ref, review) }));
}

// Whether `card` sits somewhere under `top`.
function isUnder(card: Proposal, top: Proposal, review: Review): boolean {
  const byRef = new Map(review.cards.map((c) => [c.ref, c]));
  let ref = parentRef(card, review.progress);
  const seen = new Set<string>();
  while (ref && !seen.has(ref)) {
    if (ref === top.ref) return true;
    seen.add(ref);
    ref = parentRef(byRef.get(ref) ?? card, review.progress);
  }
  return false;
}

// Where a line sits, as the person knows it: "Brightline › Analyst".
export function placeName(ref: string | null, review: Review): string {
  if (ref === null) return "the top of your resume";
  const byRef = new Map(review.cards.map((c) => [c.ref, c]));
  const card = byRef.get(ref);
  if (!card) return "there";
  const own = contentFor(card, review.progress).framing.headline;
  const above = parentRef(card, review.progress);
  const parent = above ? byRef.get(above) : undefined;
  return parent ? `${contentFor(parent, review.progress).framing.headline} › ${own}` : own;
}

// -- the page ---------------------------------------------------------------------

export type ReviewPage = { review: Review; file: ResumeFile };

export function toReviewPage(raw: unknown): ReviewPage {
  return { review: toReview(raw), file: toResumeFile(raw) };
}
