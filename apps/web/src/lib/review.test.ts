import { describe, expect, it } from "vitest";

import type { Finding, ImportSummary, Proposal, Review } from "./imports";
import {
  activeImport,
  answerText,
  currentStep,
  datesProblem,
  deferred,
  groupIntro,
  groupMatches,
  groupStatus,
  keepRequest,
  keptAlready,
  laterRequest,
  leaveOutRequest,
  lineNotes,
  lineText,
  NO_CHOICES,
  pictureCheck,
  picturePages,
  quoteLabel,
  reviewGroups,
  reviewSteps,
  setAside,
  settleReplies,
  stepKey,
  stepRecap,
  tally,
  withLineText,
} from "./review";

// A made-up person's resume, as the import reads it.
function card(
  ref: string,
  kind: Proposal["kind"],
  headline: string,
  parent_ref: string | null = null,
  facts: Proposal["content"]["facts"] = {},
): Proposal {
  return {
    ref,
    kind,
    content: { facts, framing: { headline, body: "" } },
    parent_ref,
    role_ref: null,
    source_blocks: [],
    source: [],
    needs_check: [],
    placement: null,
  };
}

const CARDS: Proposal[] = [
  card("card-1", "story", "Operations leader who ships on time."),
  card("card-2", "employment", "Northwind Logistics", null, { start: "2014-03", end: "present" }),
  card("card-3", "position", "Director", "card-2"),
  card("card-4", "accomplishment", "Cut late shipments by 22%.", "card-3"),
  card("card-5", "accomplishment", "Built a demand forecast.", "card-3"),
  card("card-6", "employment", "Brightline Consulting", null, { start: "2010", end: "2014" }),
  card("card-7", "position", "Consultant", "card-6"),
  card("card-8", "accomplishment", "Moved freight to rail.", "card-7"),
  card("card-9", "skill", "Tools: SQL, Python"),
  card("card-10", "education", "University of Wisconsin"),
];

const FIGURES: Finding = {
  rule: "consistency.figures",
  severity: "fix",
  category: "consistency",
  about: "cards",
  title: "The same result has two different numbers",
  detail: "One place says 22% and another says 25%.",
  locations: [
    { block: 1, excerpt: "Cut late shipments by 22%", figure: "22%" },
    { block: 9, excerpt: "late shipments down 25%", figure: "25%" },
  ],
};

function review(overrides: Partial<Review> = {}, progress: Partial<Review["progress"]> = {}): Review {
  return {
    id: "import-1",
    file: { format: "docx", size: 1000, name: "Avery Quinn.docx", pages: 1, words: 300 },
    cards: CARDS,
    findings: [FIGURES],
    toSettle: [0],
    progress: { settled: {}, cards: {}, edits: {}, moves: {}, ...progress },
    contactKept: true,
    readBy: null,
    matches: {},
    ...overrides,
  };
}

describe("groups", () => {
  it("takes each job with what's under it, then the rest with the summary first", () => {
    const groups = reviewGroups(review());
    expect(groups.map((g) => [g.key, g.cards.map((c) => c.ref)])).toEqual([
      ["card-2", ["card-2", "card-3", "card-4", "card-5"]],
      ["card-6", ["card-6", "card-7", "card-8"]],
      ["rest", ["card-1", "card-10", "card-9"]],
    ]);
  });

  it("follows where the person moved a line", () => {
    const moved = review({}, { moves: { "card-8": "card-3" } });
    const [northwind, brightline] = reviewGroups(moved);
    expect(northwind!.cards.map((c) => c.ref)).toContain("card-8");
    expect(brightline!.cards.map((c) => c.ref)).toEqual(["card-6", "card-7"]);
  });

  it("says what a job holds", () => {
    const [first, second, rest] = reviewGroups(review());
    expect(groupIntro(first!, review(), true)).toBe(
      "Let's go job by job, starting with Northwind Logistics, Mar 2014 – Present: 1 title and 2 lines.",
    );
    expect(groupIntro(second!, review(), false)).toBe(
      "Next, Brightline Consulting, 2010 – 2014: 1 title and 1 line.",
    );
    expect(groupIntro(rest!, review(), false)).toBe(
      "And the rest: your summary, education and skills.",
    );
  });
});

describe("steps", () => {
  it("asks what doesn't line up first, then each job, then the rest", () => {
    const steps = reviewSteps(review());
    expect(steps.map((s) => s.kind)).toEqual(["settle", "group", "group", "group"]);
    expect(currentStep(review())?.kind).toBe("settle");
  });

  it("moves on once a question has an answer, even 'not sure yet'", () => {
    const later = review({}, { settled: { "0": { answer: "later", value: null, changed: [] } } });
    const step = currentStep(later);
    expect(step?.kind === "group" && step.group.key).toBe("card-2");
    expect(answerText(reviewSteps(later)[0]!, later)).toBe("Not sure yet");

    const chosen = review({}, { settled: { "0": { answer: "chosen", value: "25%", changed: [] } } });
    expect(answerText(reviewSteps(chosen)[0]!, chosen)).toBe("It was 25%");
    expect(settleReplies(FIGURES).map((r) => r.label)).toEqual([
      "It was 22%",
      "It was 25%",
      "Not sure yet",
    ]);
  });

  it("goes back to a question left for later when the person asks to", () => {
    const later = review({}, { settled: { "0": { answer: "later", value: null, changed: [] } } });
    expect(deferred(later).map(stepKey)).toEqual(["settle-0"]);
    expect(setAside(later).has("settle-0")).toBe(true);
    expect(currentStep(later, setAside(later))?.kind).toBe("settle");
    const sure = review({}, { settled: { "0": { answer: "as_is", value: null, changed: [] } } });
    expect(deferred(sure)).toEqual([]);
    // Once the cards it's about are kept, Plytos says the answer won't change them.
    const cards = CARDS.map((c, i) => ({ ...c, source_blocks: [i] }));
    const step = { kind: "settle" as const, index: 0, finding: FIGURES };
    expect(keptAlready(step, review({ cards }))).toBe(false);
    const kept = review({ cards }, { cards: { "card-2": { state: "approved", card_id: "c2" } } });
    expect(keptAlready(step, kept)).toBe(true);
  });

  it("points the person to the dates when they'll fix them, and reminds them there", () => {
    const gap: Finding = {
      ...FIGURES,
      rule: "dates.gap",
      title: "An 8-month gap",
      locations: [{ block: 5, excerpt: "Brightline Consulting", figure: null }],
    };
    expect(settleReplies(gap).map((r) => r.label)).toContain("I'll fix the dates below");
    const cards = CARDS.map((c, i) => ({ ...c, source_blocks: [i] }));
    const fixing = review(
      { cards, findings: [gap], toSettle: [0] },
      { settled: { "0": { answer: "on_card", value: null, changed: [] } } },
    );
    expect(lineNotes(cards[5]!, fixing)).toEqual(["An 8-month gap"]);
  });

  it("asks where a line belongs before anything else", () => {
    const unsure: Proposal = {
      ...CARDS[7]!,
      placement: {
        question: "Which job is this from?",
        reason: "It reads like Northwind's work.",
        choices: [
          { parent_ref: "card-7", label: "Consultant, Brightline Consulting" },
          { parent_ref: "card-3", label: "Director, Northwind Logistics" },
        ],
        moved_from: null,
      },
    };
    const cards = CARDS.map((c) => (c.ref === "card-8" ? unsure : c));
    const asked = review({ cards });
    expect(currentStep(asked)?.kind).toBe("place");
    const placed = review({ cards }, { moves: { "card-8": "card-3" } });
    expect(answerText(reviewSteps(placed)[0]!, placed)).toBe("Director, Northwind Logistics");
    const dropped = review({ cards }, { cards: { "card-8": { state: "dropped", card_id: null } } });
    expect(answerText(reviewSteps(dropped)[0]!, dropped)).toBe("Leave it out");
  });

  it("passes over a job set aside until the person goes back to it", () => {
    const settled = { "0": { answer: "as_is" as const, value: null, changed: [] } };
    const later = review(
      {},
      {
        settled,
        cards: Object.fromEntries(
          ["card-2", "card-3", "card-4", "card-5"].map((ref) => [ref, { state: "later" as const, card_id: null }]),
        ),
      },
    );
    const step = currentStep(later);
    expect(step?.kind === "group" && step.group.key).toBe("card-6");
    expect(setAside(later)).toEqual(new Set(["card-2"]));
    const revisit = currentStep(later, setAside(later));
    expect(revisit?.kind === "group" && revisit.group.key).toBe("card-2");
    expect(groupStatus(reviewGroups(later)[0]!, later)).toBe("later");
    expect(answerText(reviewSteps(later)[1]!, later)).toBe("Not now");
  });

  it("is done when every job and question has an answer", () => {
    const decided = review(
      {},
      {
        settled: { "0": { answer: "as_is", value: null, changed: [] } },
        cards: Object.fromEntries(
          CARDS.map((c) => [c.ref, { state: c.ref === "card-5" ? "dropped" : "approved", card_id: "x" }]),
        ) as Review["progress"]["cards"],
      },
    );
    expect(currentStep(decided)).toBeNull();
    const steps = reviewSteps(decided);
    expect(answerText(steps[1]!, decided)).toBe("Kept it, with 1 line, 1 left out");
    expect(answerText(steps[3]!, decided)).toBe("Kept 3");
    expect(stepRecap(steps[0]!, decided)).toBe(
      "The same result has two different numbers. These can't both be right. Which one is true?",
    );
    expect(stepRecap(steps[1]!, decided)).toBe("Northwind Logistics, Mar 2014 – Present.");
    expect(tally(decided)).toEqual({ kept: 9, later: 0, out: 1 });
  });
});

describe("keeping a job", () => {
  const job = () => reviewGroups(review())[0]!;

  it("keeps what's left, in the person's words, and leaves out what they took out", () => {
    const request = keepRequest(job(), review(), {
      out: new Set(["card-5"]),
      wording: { "card-4": "  Cut late shipments by 25%.  ", "card-3": "Director" },
      choice: {},
      dates: {},
    });
    expect(request.leave_out).toEqual(["card-5"]);
    expect(request.later).toEqual([]);
    expect(request.keep.map((k) => k.ref)).toEqual(["card-2", "card-3", "card-4"]);
    // Unchanged wording sends nothing; changed wording keeps the facts.
    expect(request.keep[1]!.content).toBeNull();
    expect(request.keep[2]!.content?.framing.headline).toBe("Cut late shipments by 25%.");
  });

  it("leaves the whole job out with its own card", () => {
    const request = keepRequest(job(), review(), { ...NO_CHOICES, out: new Set(["card-2"]) });
    expect(request.keep).toEqual([]);
    expect(request.leave_out).toEqual(["card-2", "card-3", "card-4", "card-5"]);
    expect(leaveOutRequest(job(), review()).leave_out).toEqual(request.leave_out);
  });

  it("skips what's decided and sets the rest aside", () => {
    const partly = review({}, { cards: { "card-2": { state: "approved", card_id: "c2" } } });
    const group = reviewGroups(partly)[0]!;
    expect(laterRequest(group, partly).later).toEqual(["card-3", "card-4", "card-5"]);
  });

  it("carries a choice only for cards that are already the person's", () => {
    const mine = review({
      matches: { "card-2": { card_id: "c2", headline: "Northwind Logistics", same: false } },
    });
    const group = reviewGroups(mine)[0]!;
    const request = keepRequest(group, mine, {
      ...NO_CHOICES,
      choice: { "card-2": "keep", "card-3": "separate" },
    });
    expect(request.keep.map((k) => k.choice)).toEqual(["keep", null, null, null]);
    expect(groupMatches(group, mine)).toEqual({ mine: 1, changes: 1 });
  });
});

describe("rewording and dates", () => {
  const LONG = `${"Operations leader who ships on time across many sites ".repeat(5).trim()}.`;
  const summary = withLineText(CARDS[0]!.content, LONG);

  it("edits a long summary in full, not its shortened headline", () => {
    expect(summary.framing.headline.endsWith("…")).toBe(true);
    expect(summary.framing.headline.length).toBeLessThanOrEqual(200);
    expect(summary.framing.body).toBe(LONG);
    expect(lineText(summary)).toBe(LONG);
    // Shortened again, it goes back to a plain headline.
    expect(withLineText(summary, "Ships on time.").framing).toEqual({ headline: "Ships on time.", body: "" });
  });

  it("keeps a reworded summary's full text", () => {
    const long = review({ cards: CARDS.map((c) => (c.ref === "card-1" ? { ...c, content: summary } : c)) });
    const rest = reviewGroups(long).at(-1)!;
    const words = `${LONG} Known for calm launches.`;
    const request = keepRequest(rest, long, { ...NO_CHOICES, wording: { "card-1": words } });
    const kept = request.keep.find((k) => k.ref === "card-1")!.content!;
    expect(kept.framing.body).toBe(words);
    expect(lineText(kept)).toBe(words);
  });

  it("keeps a job or title with the dates the person corrected", () => {
    const group = reviewGroups(review())[1]!;
    const request = keepRequest(group, review(), {
      ...NO_CHOICES,
      dates: { "card-6": { start: "2010-06", end: "2013-06" }, "card-7": { start: "2010", end: "" } },
    });
    const facts = (ref: string) => request.keep.find((k) => k.ref === ref)!.content!.facts;
    expect(facts("card-6")).toMatchObject({ start: "2010-06", end: "2013-06" });
    expect(facts("card-7")).toEqual({ start: "2010" });
  });

  it("says plainly what's wrong with dates", () => {
    expect(datesProblem({ start: "2014-03", end: "present" })).toBeNull();
    expect(datesProblem({ start: "2014", end: "2014" })).toBeNull();
    expect(datesProblem({ start: "March 2014", end: "" })).toMatch(/start/);
    expect(datesProblem({ start: "2014-03", end: "soon" })).toMatch(/end/);
    expect(datesProblem({ start: "2015-01", end: "2014-12" })).toBe("The end comes before the start.");
  });
});

describe("which resume to go through", () => {
  const summary = (id: string, created_at: string, more: Partial<ImportSummary> = {}): ImportSummary => ({
    id,
    created_at,
    updated_at: created_at,
    state: "read",
    stage: null,
    file: { format: "docx", size: 1, name: `${id}.docx` },
    cards: 10,
    approved: 0,
    later: 0,
    dropped: 0,
    to_settle: 0,
    ...more,
  });

  it("picks the one asked for, or the newest with cards still to decide", () => {
    const older = summary("a", "2026-11-01T00:00:00Z");
    const newer = summary("b", "2026-11-03T00:00:00Z");
    const done = summary("c", "2026-11-04T00:00:00Z", { approved: 8, dropped: 2 });
    const reading = summary("d", "2026-11-05T00:00:00Z", { state: "reading", cards: 0 });
    expect(activeImport([older, newer, done, reading], null)?.id).toBe("b");
    expect(activeImport([older, newer, done], "a")?.id).toBe("a");
    expect(activeImport([older, newer, done], "c")?.id).toBe("c");
    expect(activeImport([done, reading], "d")).toBeNull();
  });
});

describe("quoting a line", () => {
  // Which card each line of the made-up file was read into.
  const placed = CARDS.map((c, i) => ({ ...c, source_blocks: [i] }));

  it("says what the line is part of, not where it sits in the file", () => {
    const r = review({ cards: placed });
    expect(quoteLabel(r, 0)).toBe("Summary");
    expect(quoteLabel(r, 3)).toBe("Northwind Logistics › Director");
    expect(quoteLabel(r, 2)).toBe("Northwind Logistics");
    expect(quoteLabel(r, 1)).toBe("Experience");
    expect(quoteLabel(r, 8)).toBe("Skills");
  });

  it("follows where the person moved a line", () => {
    const r = review({ cards: placed }, { moves: { "card-4": "card-7" } });
    expect(quoteLabel(r, 3)).toBe("Brightline Consulting › Consultant");
  });

  it("falls back to the line when nothing was read from it", () => {
    expect(quoteLabel(review({ cards: placed }), 40)).toBe("Line 41");
    expect(quoteLabel(review({ cards: placed }), null)).toBe("Your resume");
  });
});

describe("scans", () => {
  const line = (block: number, page: number | null, picture: boolean) => ({
    block,
    page,
    text: "Cut late shipments by 22%.",
    picture,
  });
  const read = (...source: ReturnType<typeof line>[]): Proposal => ({
    ...card("card-9", "accomplishment", "Cut late shipments by 22%."),
    source,
  });

  it("are checked a page at a time, against the pages the cards were read from", () => {
    expect(picturePages([read(line(1, 1, false))])).toBeNull();
    expect(picturePages([read(line(4, 2, true)), read(line(1, 1, true), line(2, 2, true))])).toEqual([
      1, 2,
    ]);
    expect(pictureCheck([2])).toBe(
      "I read this from a picture of page 2, so check that the wording matches.",
    );
    expect(pictureCheck([1, 2])).toContain("pages 1 and 2");
  });

  it("say so when a picture in a Word file has no page to show", () => {
    expect(picturePages([read(line(3, null, true))])).toEqual([]);
    expect(pictureCheck([])).toContain("a picture in your file");
  });
});
