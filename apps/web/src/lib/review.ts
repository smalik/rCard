// Going through an imported resume in the conversation: the questions first,
// one at a time, then each job as a whole, then the rest. Everything here is
// worked out from the import itself (what was read and the person's progress),
// so the conversation reads the same after a reload, and no model is asked.

import type { CardContent, CardKind } from "./cards";
import {
  type Answer,
  contentFor,
  dateSpan,
  type Finding,
  findingsForCard,
  type ImportSummary,
  isFigureQuestion,
  lineLabel,
  type MatchChoice,
  outline,
  type OutlineNode,
  pathLabel,
  plural,
  type Proposal,
  type Review,
  stateOf,
} from "./imports";

const FRAMES = new Set<CardKind>(["employment", "position", "engagement", "role"]);

export function isFrame(kind: CardKind): boolean {
  return FRAMES.has(kind);
}

// -- groups -------------------------------------------------------------------

// A job and everything under it, or everything outside the jobs ("rest").
export type ReviewGroup = {
  key: string;
  kind: "job" | "rest";
  // The employment (or other frame) the job starts from; null for the rest.
  root: Proposal | null;
  // Every card in the group, each after the one it sits under.
  cards: Proposal[];
};

// The order the rest comes in: the summary, then what reads as proof, then
// schooling, then the lists.
const REST_ORDER: CardKind[] = [
  "story",
  "accomplishment",
  "project",
  "education",
  "credential",
  "skill",
  "activity",
];

function rank(kind: CardKind): number {
  const i = REST_ORDER.indexOf(kind);
  return i === -1 ? REST_ORDER.length : i;
}

function flatten(nodes: OutlineNode[]): Proposal[] {
  return nodes.flatMap((node) => [node.card, ...flatten(node.children)]);
}

export function reviewGroups(review: Review): ReviewGroup[] {
  const roots = outline(review);
  const jobs: ReviewGroup[] = roots
    .filter((node) => isFrame(node.card.kind))
    .map((node) => ({ key: node.card.ref, kind: "job", root: node.card, cards: flatten([node]) }));
  const rest = roots
    .filter((node) => !isFrame(node.card.kind))
    .map((node, index) => ({ node, index }))
    .sort((a, b) => rank(a.node.card.kind) - rank(b.node.card.kind) || a.index - b.index)
    .flatMap(({ node }) => flatten([node]));
  return rest.length > 0
    ? [...jobs, { key: "rest", kind: "rest", root: null, cards: rest }]
    : jobs;
}

export type GroupStatus = "open" | "later" | "done";

// Open while any card in it is undecided; "later" when what's left was set aside.
export function groupStatus(group: ReviewGroup, review: Review): GroupStatus {
  const states = group.cards.map((c) => stateOf(c.ref, review.progress));
  if (states.includes("pending")) return "open";
  if (states.includes("later")) return "later";
  return "done";
}

// The cards in a group the person still decides: not yet approved or left out.
export function undecided(group: ReviewGroup, review: Review): Proposal[] {
  return group.cards.filter((c) => {
    const state = stateOf(c.ref, review.progress);
    return state === "pending" || state === "later";
  });
}

// -- steps --------------------------------------------------------------------

export type Step =
  | { kind: "place"; card: Proposal }
  | { kind: "settle"; index: number; finding: Finding }
  | { kind: "group"; group: ReviewGroup };

// Every step of going through the import, in the order Plytos asks: where a
// line belongs first (it decides which job it's kept with), then what doesn't
// line up, then each job, then the rest.
export function reviewSteps(review: Review): Step[] {
  const place: Step[] = review.cards
    .filter((card) => card.placement !== null)
    .map((card) => ({ kind: "place", card }));
  const settle: Step[] = review.toSettle.flatMap((index) => {
    const finding = review.findings[index];
    return finding ? [{ kind: "settle" as const, index, finding }] : [];
  });
  const groups: Step[] = reviewGroups(review).map((group) => ({ kind: "group", group }));
  return [...place, ...settle, ...groups];
}

const NONE: ReadonlySet<string> = new Set();

// Whether the person has answered a step. A job set aside counts as answered
// unless they asked to go back to it (`revisit` holds its key).
export function answered(step: Step, review: Review, revisit = NONE): boolean {
  const { progress } = review;
  if (step.kind === "place") {
    const state = stateOf(step.card.ref, progress);
    return step.card.ref in progress.moves || state === "dropped" || state === "approved";
  }
  if (step.kind === "settle") return String(step.index) in progress.settled;
  const status = groupStatus(step.group, review);
  return status === "done" || (status === "later" && !revisit.has(step.group.key));
}

// The step Plytos is on, or null when everything has an answer.
export function currentStep(review: Review, revisit = NONE): Step | null {
  return reviewSteps(review).find((step) => !answered(step, review, revisit)) ?? null;
}

// -- what Plytos asks ---------------------------------------------------------

export function settleQuestion(finding: Finding): string {
  if (isFigureQuestion(finding)) return "These can't both be right. Which one is true?";
  if (finding.rule === "dates.gap") return "Is this gap right?";
  if (finding.rule === "dates.overlap") return "Is this overlap right?";
  if (finding.rule === "content.duplicates") return "Are these the same thing?";
  if (finding.rule.startsWith("dates.")) return "Are these dates right?";
  return "Is this right?";
}

export type Reply = { answer: Answer; value: string | null; label: string };

// The answers offered for a question, as one tap each.
export function settleReplies(finding: Finding): Reply[] {
  const later: Reply = { answer: "later", value: null, label: "Not sure yet" };
  if (isFigureQuestion(finding)) {
    const figures = [
      ...new Set(finding.locations.flatMap((loc) => (loc.figure ? [loc.figure] : []))),
    ];
    return [
      ...figures.map((figure) => ({ answer: "chosen" as const, value: figure, label: `It was ${figure}` })),
      later,
    ];
  }
  if (finding.rule === "content.duplicates") {
    return [
      { answer: "as_is", value: null, label: "They're different" },
      { answer: "on_card", value: null, label: "I'll sort it out below" },
      later,
    ];
  }
  return [
    { answer: "as_is", value: null, label: "That's right" },
    { answer: "on_card", value: null, label: "I'll fix it on the card" },
    later,
  ];
}

function headline(card: Proposal, review: Review): string {
  return contentFor(card, review.progress).framing.headline;
}

function counts(cards: Proposal[]): { titles: number; lines: number } {
  const titles = cards.filter((c) => c.kind !== "employment" && isFrame(c.kind)).length;
  return { titles, lines: cards.filter((c) => !isFrame(c.kind)).length };
}

const REST_NAMES: Partial<Record<CardKind, string>> = {
  story: "your summary",
  accomplishment: "highlights and awards",
  project: "projects",
  education: "education",
  credential: "certifications",
  skill: "skills",
  activity: "talks, memberships and interests",
};

// The headings the rest of a resume goes under.
export const SECTION_NAMES: Partial<Record<CardKind, string>> = {
  story: "Summary",
  accomplishment: "Highlights and awards",
  project: "Projects",
  education: "Education",
  credential: "Certifications",
  skill: "Skills",
  activity: "Talks, memberships and interests",
};

// What a quoted line is part of, as the person knows it: "Northwind Logistics ›
// Operations Manager" for a result, "Summary" for the summary. Where it sits in
// the file is the last resort.
export function quoteLabel(review: Review, block: number | null): string {
  const card = block === null ? undefined : review.cards.find((c) => c.source_blocks.includes(block));
  if (!card) return lineLabel(review, block);
  const path = pathLabel(card, review);
  if (path) return path;
  if (isFrame(card.kind)) return "Experience";
  return SECTION_NAMES[card.kind] ?? lineLabel(review, block);
}

function join(parts: string[]): string {
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
}

// "Northwind Logistics, Mar 2014 – Present: 2 titles and 8 lines." Plytos says
// this as it shows a job; the first one gets a word of how this goes.
export function groupIntro(group: ReviewGroup, review: Review, first: boolean): string {
  const left = undecided(group, review);
  if (group.kind === "rest") {
    const kinds = [...new Set(left.map((c) => c.kind))];
    const names = kinds.flatMap((k) => (REST_NAMES[k] ? [REST_NAMES[k]!] : []));
    const what = names.length > 0 ? join(names) : plural(left.length, "card");
    return first ? `Here's what I found: ${what}.` : `And the rest: ${what}.`;
  }
  const root = group.root!;
  const content = contentFor(root, review.progress);
  const when = dateSpan(content.facts);
  const { titles, lines } = counts(left.filter((c) => c !== root));
  const parts = [titles > 0 ? plural(titles, "title") : "", lines > 0 ? plural(lines, "line") : ""];
  const size = join(parts.filter(Boolean));
  const name = `${content.framing.headline}${when ? `, ${when}` : ""}`;
  const lead = first ? "Let's go job by job, starting with " : "Next, ";
  return size ? `${lead}${name}: ${size}.` : `${lead}${name}.`;
}

// How many of a group's cards are already the person's own (bringing a resume
// in again), and of those, how many this adds something to.
export function groupMatches(
  group: ReviewGroup,
  review: Review,
): { mine: number; changes: number } {
  const left = undecided(group, review);
  const matched = left.filter((c) => review.matches[c.ref]);
  return { mine: matched.length, changes: matched.filter((c) => !review.matches[c.ref]!.same).length };
}

// Notes under a line: where the reading had to guess, then wording tips.
export function lineNotes(card: Proposal, review: Review): string[] {
  const tips = findingsForCard(card, review)
    .filter((i) => !review.toSettle.includes(i))
    .map((i) => review.findings[i]!.title);
  return [...card.needs_check, ...tips].slice(0, 2);
}

// What Plytos asked, said again briefly above the person's answer once it's
// answered.
export function stepRecap(step: Step, review: Review): string {
  if (step.kind === "place") {
    const question = step.card.placement?.question ?? "Where does this go?";
    return `${question} “${headline(step.card, review)}”`;
  }
  if (step.kind === "settle") return `${step.finding.title}. ${settleQuestion(step.finding)}`;
  if (step.group.kind === "rest") return "And the rest: your summary, education, skills and so on.";
  const content = contentFor(step.group.root!, review.progress);
  const when = dateSpan(content.facts);
  return when ? `${content.framing.headline}, ${when}.` : `${content.framing.headline}.`;
}

// -- what the person said -----------------------------------------------------

// The person's answer to a step, as their reply in the conversation.
export function answerText(step: Step, review: Review): string | null {
  const { progress } = review;
  if (step.kind === "place") {
    const state = stateOf(step.card.ref, progress);
    if (state === "dropped") return "Leave it out";
    if (!(step.card.ref in progress.moves)) return null;
    const to = progress.moves[step.card.ref] ?? null;
    const choice = step.card.placement?.choices.find((c) => c.parent_ref === to);
    if (choice) return choice.label;
    const card = review.cards.find((c) => c.ref === to);
    return card ? headline(card, review) : "Neither";
  }
  if (step.kind === "settle") {
    const settled = progress.settled[String(step.index)];
    if (!settled) return null;
    const reply = settleReplies(step.finding).find(
      (r) => r.answer === settled.answer && (r.value === null || r.value === settled.value),
    );
    return reply?.label ?? null;
  }
  const states = step.group.cards.map((c) => ({ card: c, state: stateOf(c.ref, progress) }));
  if (states.some((s) => s.state === "pending")) return null;
  const lines = states.filter((s) => !isFrame(s.card.kind));
  const kept = lines.filter((s) => s.state === "approved").length;
  const out = lines.filter((s) => s.state === "dropped").length;
  const later = states.filter((s) => s.state === "later").length;
  if (states.every((s) => s.state === "later")) return "Not now";
  if (states.every((s) => s.state === "dropped")) return "Leave it out";
  const parts: string[] = [];
  if (step.group.kind === "job") {
    parts.push(kept > 0 ? `Kept it, with ${plural(kept, "line")}` : "Kept it");
  } else {
    parts.push(`Kept ${kept}`);
  }
  if (out > 0) parts.push(`${out} left out`);
  if (later > 0) parts.push(`${later} for later`);
  return parts.join(", ");
}

// -- keeping a group ----------------------------------------------------------

// What the person changed in a group before keeping it.
export type GroupChoices = {
  // Cards left out, by ref.
  out: ReadonlySet<string>;
  // Headlines the person reworded, by ref.
  wording: Readonly<Record<string, string>>;
  // For cards that are already theirs: what keeping does.
  choice: Readonly<Record<string, MatchChoice>>;
};

export const NO_CHOICES: GroupChoices = { out: new Set(), wording: {}, choice: {} };

export type KeepRequest = {
  keep: { ref: string; content: CardContent | null; choice: MatchChoice | null }[];
  leave_out: string[];
  later: string[];
};

function reworded(content: CardContent, words: string | undefined): CardContent | null {
  const trimmed = words?.trim();
  if (!trimmed || trimmed === content.framing.headline) return null;
  return { ...content, framing: { ...content.framing, headline: trimmed } };
}

// Keeps every undecided card in a group but the ones left out, in the
// person's wording where they changed it. Leaving out the job's own card
// leaves out the whole job.
export function keepRequest(group: ReviewGroup, review: Review, choices: GroupChoices): KeepRequest {
  const left = undecided(group, review);
  const all = group.root !== null && choices.out.has(group.root.ref);
  const request: KeepRequest = { keep: [], leave_out: [], later: [] };
  for (const card of left) {
    if (all || choices.out.has(card.ref)) {
      request.leave_out.push(card.ref);
      continue;
    }
    request.keep.push({
      ref: card.ref,
      content: reworded(contentFor(card, review.progress), choices.wording[card.ref]),
      choice: review.matches[card.ref] ? (choices.choice[card.ref] ?? null) : null,
    });
  }
  return request;
}

// Sets every undecided card in a group aside for later.
export function laterRequest(group: ReviewGroup, review: Review): KeepRequest {
  return { keep: [], leave_out: [], later: undecided(group, review).map((c) => c.ref) };
}

// Leaves a whole group out.
export function leaveOutRequest(group: ReviewGroup, review: Review): KeepRequest {
  return { keep: [], leave_out: undecided(group, review).map((c) => c.ref), later: [] };
}

// The jobs with cards set aside, to go back to them.
export function setAside(review: Review): Set<string> {
  return new Set(
    reviewGroups(review)
      .filter((group) => groupStatus(group, review) === "later")
      .map((group) => group.key),
  );
}

// -- where things stand ---------------------------------------------------------

export function tally(review: Review): { kept: number; later: number; out: number } {
  const states = review.cards.map((c) => stateOf(c.ref, review.progress));
  return {
    kept: states.filter((s) => s === "approved").length,
    later: states.filter((s) => s === "later").length,
    out: states.filter((s) => s === "dropped").length,
  };
}

// Whether a resume still has cards nobody has decided on, so going through it
// picks up in the conversation.
export function hasOpenWork(resume: ImportSummary): boolean {
  return (
    resume.state === "read" && resume.cards - resume.approved - resume.dropped - resume.later > 0
  );
}

// The resume to go through in the conversation: the one asked for, or else the
// newest one with cards still to decide.
export function activeImport(
  resumes: ImportSummary[],
  asked: string | null,
): ImportSummary | null {
  if (asked) {
    const found = resumes.find((r) => r.id === asked);
    if (found && found.state === "read") return found;
  }
  return (
    [...resumes]
      .filter(hasOpenWork)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null
  );
}
