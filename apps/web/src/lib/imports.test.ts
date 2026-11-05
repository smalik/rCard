import { describe, expect, it } from "vitest";

import {
  bySeverity,
  cardsForFinding,
  contentFor,
  contentProblems,
  dateSpan,
  factRows,
  factsAbove,
  failureText,
  type Finding,
  figureChoices,
  findingsForCard,
  foundRows,
  highlight,
  isFigureQuestion,
  matchNote,
  openQuestions,
  outline,
  overview,
  parentRef,
  pathLabel,
  placementOpen,
  type Proposal,
  type Review,
  readerName,
  reviewQueue,
  settledCount,
  settleState,
  stageSpan,
  stageStates,
  textToFact,
  toMatches,
  toReview,
  toStatus,
  wordingTips,
} from "./imports";

// A made-up person, as in the API's import tests.
function card(partial: Partial<Proposal> & Pick<Proposal, "ref" | "kind">): Proposal {
  return {
    content: { facts: {}, framing: { headline: partial.ref, body: "" } },
    parent_ref: null,
    role_ref: null,
    source_blocks: [],
    source: [],
    needs_check: [],
    placement: null,
    ...partial,
  };
}

const ROLE = {
  employer: "Fabrikam Inc.",
  title: "Senior Analyst",
  start: "2019-07",
  end: "present",
};

const CARDS: Proposal[] = [
  card({
    ref: "card-1",
    kind: "role",
    role_ref: "role-1",
    content: { facts: ROLE, framing: { headline: "Senior Analyst, Fabrikam Inc.", body: "" } },
    source_blocks: [10],
  }),
  card({
    ref: "card-2",
    kind: "accomplishment",
    role_ref: "role-1",
    content: {
      facts: ROLE,
      framing: { headline: "Cut claim review time 30% by rebuilding triage.", body: "" },
    },
    source_blocks: [12],
  }),
  card({
    ref: "card-3",
    kind: "accomplishment",
    role_ref: "role-1",
    content: {
      facts: ROLE,
      framing: { headline: "Led the pricing review with finance.", body: "" },
    },
    source_blocks: [13],
  }),
  card({
    ref: "card-4",
    kind: "accomplishment",
    content: {
      facts: { award: "Analyst of the Year", date: "2022-12" },
      framing: { headline: "Analyst of the Year", body: "" },
    },
    source_blocks: [20],
  }),
  card({
    ref: "card-5",
    kind: "skill",
    content: {
      facts: { category: "Tools", skills: ["SQL", "Python", "Tableau"] },
      framing: { headline: "Tools", body: "SQL, Python, Tableau" },
    },
    source_blocks: [22],
  }),
  card({
    ref: "card-6",
    kind: "role",
    role_ref: "role-2",
    content: {
      facts: {
        employer: "Contoso Staffing",
        client: "Northwind Health",
        title: "Consultant II",
        plain_title: "Consultant",
        start: "2016-01",
        end: "2019-06",
      },
      framing: { headline: "Consultant, Northwind Health", body: "" },
    },
    source_blocks: [16],
  }),
];

function finding(partial: Partial<Finding> & Pick<Finding, "rule">): Finding {
  return {
    severity: "note",
    category: partial.rule.split(".")[0]!,
    about: "cards",
    title: partial.rule,
    detail: "",
    locations: [],
    ...partial,
  };
}

const FIGURES = finding({
  rule: "consistency.figures",
  severity: "fix",
  locations: [
    { block: 12, excerpt: "Cut claim review time 30% by rebuilding triage.", figure: "30%" },
    { block: 30, excerpt: "Cut review time 25% across claims.", figure: "25%" },
  ],
});
const TENSE = finding({
  rule: "consistency.tense",
  locations: [{ block: 13, excerpt: "Led the pricing review", figure: null }],
});
const GAP = finding({
  rule: "dates.gap",
  locations: [{ block: 16, excerpt: "Consultant, Northwind Health", figure: null }],
});
const LAYOUT = finding({ rule: "ats.tables", severity: "improve", about: "document" });

function review(progress: Partial<Review["progress"]> = {}): Review {
  return {
    id: "0190a7a2-0000-7000-8000-000000000000",
    file: { format: "docx", size: 20_000, name: "Riley Park resume.docx", pages: 1, words: 300 },
    cards: CARDS,
    findings: [FIGURES, TENSE, GAP, LAYOUT],
    toSettle: [0, 2],
    progress: { settled: {}, cards: {}, edits: {}, moves: {}, ...progress },
    contactKept: true,
    readBy: null,
    matches: {},
  };
}

describe("toReview", () => {
  it("keeps the lines cards came from and leaves the rest of the resume behind", () => {
    const shaped = toReview({
      id: "0190a7a2-0000-7000-8000-000000000000",
      file: { format: "docx", size: 20_000, name: "Riley Park resume.docx" },
      result: {
        facts: { pages: 1, word_count: 300 },
        contact: { emails: ["riley.park@example.com"], phones: ["555-0100"] },
        blocks: [
          { index: 0, text: "Riley Park · riley.park@example.com · 555-0100" },
          { index: 12, text: "Cut claim review time 30% by rebuilding triage.", page: 1 },
        ],
        cards: [{ ...CARDS[1], source: undefined }],
        findings: [FIGURES],
      },
      progress: { settled: {}, cards: {}, edits: {} },
      to_settle: [0],
    });
    expect(shaped.file).toEqual({
      format: "docx",
      size: 20_000,
      name: "Riley Park resume.docx",
      pages: 1,
      words: 300,
    });
    expect(shaped.cards[0]?.source).toEqual([
      {
        block: 12,
        page: 1,
        text: "Cut claim review time 30% by rebuilding triage.",
        picture: false,
      },
    ]);
    expect(shaped.contactKept).toBe(true);
    expect(shaped.toSettle).toEqual([0]);
    const text = JSON.stringify(shaped);
    expect(text).not.toContain("riley.park@example.com");
    expect(text).not.toContain("555-0100");
  });

  it("marks lines read from a picture, and drops the old question on every scanned card", () => {
    const shaped = toReview({
      result: {
        blocks: [{ index: 3, text: "Cut late shipments by 22%.", page: 2, where: "image" }],
        cards: [
          {
            ...CARDS[1],
            source_blocks: [3],
            needs_check: ["Plytos read this from a picture in your resume. Check the wording."],
          },
        ],
      },
    });
    expect(shaped.cards[0]?.source[0]?.picture).toBe(true);
    expect(shaped.cards[0]?.needs_check).toEqual([]);
  });

  it("copes with an empty answer", () => {
    const shaped = toReview(null);
    expect(shaped.cards).toEqual([]);
    expect(shaped.progress).toEqual({ settled: {}, cards: {}, edits: {}, moves: {} });
    expect(shaped.readBy).toBeNull();
  });

  it("says which model sorted the lines", () => {
    expect(toReview({ result: { read_by: "claude-haiku-5-5" } }).readBy).toBe("claude-haiku-5-5");
    expect(readerName("claude-haiku-5-5")).toBe("Claude Haiku 5.5");
    expect(readerName("claude-opus-5")).toBe("Claude Opus 5");
    expect(readerName(null)).toBeNull();
  });
});

describe("questions to settle", () => {
  it("offers the two numbers a result was given", () => {
    expect(figureChoices(FIGURES)).toEqual(["30%", "25%"]);
    expect(isFigureQuestion(FIGURES)).toBe(true);
    expect(isFigureQuestion(GAP)).toBe(false);
  });

  it("counts a question settled only when it has an answer other than later", () => {
    const r = review({
      settled: {
        "0": { answer: "chosen", value: "25%", changed: ["card-2"] },
        "2": { answer: "later", value: null, changed: [] },
      },
    });
    expect(settleState(0, r.progress)).toBe("settled");
    expect(settleState(2, r.progress)).toBe("later");
    expect(settleState(1, r.progress)).toBe("open");
    expect(settledCount(r)).toBe(1);
  });

  it("ties findings to the cards they're about", () => {
    const r = review();
    expect(cardsForFinding(FIGURES, CARDS)).toEqual(["card-2"]);
    expect(findingsForCard(CARDS[1]!, r)).toEqual([0]);
    expect(openQuestions(CARDS[1]!, r)).toEqual([0]);
    expect(wordingTips(CARDS[2]!, r)).toEqual([1]);
    expect(findingsForCard(CARDS[5]!, r)).toEqual([2]);
  });
});

describe("reviewQueue", () => {
  it("puts each job first, then results with numbers, and cards for later last", () => {
    expect(reviewQueue(review())).toEqual([
      "card-1",
      "card-6",
      "card-2",
      "card-3",
      "card-4",
      "card-5",
    ]);
    const r = review({
      cards: {
        "card-2": { state: "approved", card_id: "c1" },
        "card-3": { state: "later", card_id: null },
        "card-5": { state: "dropped", card_id: null },
      },
    });
    expect(reviewQueue(r)).toEqual(["card-1", "card-6", "card-4", "card-3"]);
  });

  it("reviews a card in the words the person's answers gave it", () => {
    const edited = {
      facts: ROLE,
      framing: { headline: "Cut claim review time 25% by rebuilding triage.", body: "" },
    };
    const r = review({ edits: { "card-2": edited } });
    expect(contentFor(CARDS[1]!, r.progress)).toBe(edited);
    expect(contentFor(CARDS[2]!, r.progress)).toBe(CARDS[2]!.content);
  });
});

describe("overview", () => {
  it("counts what the screens show", () => {
    const o = overview(review({ cards: { "card-2": { state: "approved", card_id: "c1" } } }));
    expect(o).toMatchObject({
      things: 6,
      accomplishments: 2,
      withNumbers: 1,
      roles: 2,
      dateQuestions: 1,
      figureQuestions: 1,
      repeatQuestions: 0,
      skills: 3,
      wordingTips: 1,
      documentNotes: 1,
      open: 2,
      pending: 5,
      approved: 1,
    });
    expect(o.years?.[0]).toBe(2016);
  });

  it("lists what was found while reading", () => {
    const rows = foundRows(review());
    expect(rows.map((r) => r.count)).toEqual([2, null, 2, 3, 0, null]);
  });
});

describe("card faces", () => {
  it("names a client engagement's agency and plain title", () => {
    const rows = factRows(CARDS[5]!, CARDS[5]!.content);
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ["Client", "Northwind Health"],
      ["Through", "Contoso Staffing"],
      ["Official title", "Consultant II"],
      ["Dates", "Jan 2016 – Jun 2019"],
    ]);
    expect(rows[2]?.note).toBe("Consultant");
    expect(dateSpan(ROLE)).toBe("Jul 2019 – Present");
  });

  it("highlights the figure inside a quoted line", () => {
    expect(highlight("Cut review time 25% across claims.", "25%")).toEqual([
      "Cut review time ",
      "25%",
      " across claims.",
    ]);
    expect(highlight("No figure here.", "25%")).toEqual(["No figure here.", "", ""]);
  });
});

describe("editing", () => {
  it("reads edited facts back as the kind of value they were", () => {
    expect(textToFact("SQL, Python ,", ["SQL"])).toEqual(["SQL", "Python"]);
    expect(textToFact("  ", "2021-03")).toBeUndefined();
    expect(textToFact("12", 4)).toBe(12);
  });

  it("explains what would stop a card saving", () => {
    expect(
      contentProblems({ facts: { start: "March 2021" }, framing: { headline: " ", body: "" } }),
    ).toEqual(["Add a headline.", "Write the start date as a year and month, like 2021-03."]);
    expect(
      contentProblems({ facts: { end: "present" }, framing: { headline: "Fine", body: "" } }),
    ).toEqual([]);
  });

  it("lists findings that need fixing first", () => {
    expect(bySeverity([GAP, LAYOUT, FIGURES]).map((f) => f.index)).toEqual([2, 1, 0]);
  });
});

// The same made-up person, read as a career tree.
const TREE: Proposal[] = [
  card({
    ref: "t-1",
    kind: "employment",
    content: {
      facts: { employer: "Fabrikam Inc.", start: "2015-02", end: "present" },
      framing: { headline: "Fabrikam Inc.", body: "" },
    },
  }),
  card({
    ref: "t-2",
    kind: "position",
    parent_ref: "t-1",
    content: {
      facts: { title: "Senior Analyst", start: "2019-07", end: "present" },
      framing: { headline: "Senior Analyst", body: "" },
    },
  }),
  card({
    ref: "t-3",
    kind: "accomplishment",
    parent_ref: "t-2",
    content: { facts: {}, framing: { headline: "Led the pricing review.", body: "" } },
  }),
  card({
    ref: "t-4",
    kind: "accomplishment",
    parent_ref: "t-2",
    content: {
      facts: {},
      framing: { headline: "Cut claim review time 30%.", body: "" },
    },
  }),
  card({
    ref: "t-5",
    kind: "position",
    parent_ref: "t-1",
    content: {
      facts: { title: "Analyst", start: "2015-02", end: "2019-06" },
      framing: { headline: "Analyst", body: "" },
    },
  }),
  card({ ref: "t-6", kind: "skill" }),
];

function treeReview(progress: Partial<Review["progress"]> = {}): Review {
  return { ...review(), cards: TREE, findings: [], toSettle: [], progress: { ...review().progress, ...progress } };
}

describe("career tree", () => {
  it("nests titles under their employer and results under their title", () => {
    const shape = (nodes: ReturnType<typeof outline>): unknown[] =>
      nodes.map((n) => (n.children.length ? [n.card.ref, shape(n.children)] : n.card.ref));
    expect(shape(outline(treeReview()))).toEqual([
      ["t-1", [["t-2", ["t-3", "t-4"]], "t-5"]],
      "t-6",
    ]);
  });

  it("reviews an employer before its titles and a title before its results", () => {
    expect(reviewQueue(treeReview())).toEqual(["t-1", "t-2", "t-4", "t-3", "t-5", "t-6"]);
  });

  it("shows a result where it sits, from the cards above it", () => {
    const r = treeReview();
    const result = TREE[3]!;
    expect(pathLabel(result, r)).toBe("Fabrikam Inc. › Senior Analyst");
    const rows = factRows(result, result.content, factsAbove(result, r));
    expect(rows.map((row) => [row.label, row.value, row.above ?? false])).toEqual([
      ["Under", "Senior Analyst, Fabrikam Inc.", true],
      ["When", "Jul 2019 – Present", true],
    ]);
    const title = TREE[1]!;
    expect(factRows(title, title.content, factsAbove(title, r)).map((row) => row.label)).toEqual([
      "At",
      "Official title",
      "Dates",
    ]);
  });

  it("shows the result, scope and skills an accomplishment names", () => {
    const result = card({
      ref: "r-1",
      kind: "accomplishment",
      content: {
        facts: {
          outcome: "collecting $2.4M a year",
          scope: ["3 clinics"],
          skills: ["billing"],
        },
        framing: { headline: "Ran billing for 3 clinics, collecting $2.4M a year.", body: "" },
      },
    });
    expect(factRows(result, result.content).map((row) => [row.label, row.value])).toEqual([
      ["Result", "collecting $2.4M a year"],
      ["Scope", "3 clinics"],
      ["Skills", "billing"],
    ]);
  });

  it("waits on the person to say where a result belongs, then files it there", () => {
    const asked: Proposal = {
      ...TREE[2]!,
      placement: {
        question: "Which job is this from?",
        reason: "It's written under Analyst at Fabrikam Inc. on your resume.",
        choices: [
          { parent_ref: "t-2", label: "Senior Analyst at Fabrikam Inc." },
          { parent_ref: "t-5", label: "Analyst at Fabrikam Inc." },
        ],
        moved_from: null,
      },
    };
    const cards = TREE.map((c) => (c.ref === asked.ref ? asked : c));
    const before = { ...treeReview(), cards };
    expect(placementOpen(asked, before.progress)).toBe(true);
    expect(parentRef(asked, before.progress)).toBe("t-2");

    const after = { ...treeReview({ moves: { "t-3": "t-5" } }), cards };
    expect(placementOpen(asked, after.progress)).toBe(false);
    expect(parentRef(asked, after.progress)).toBe("t-5");
    expect(pathLabel(asked, after)).toBe("Fabrikam Inc. › Analyst");
    expect(placementOpen(TREE[3]!, after.progress)).toBe(false);
  });
});

describe("a reading in the background", () => {
  it("shows which stages are done and which is under way", () => {
    expect(stageStates("file", false)).toEqual(["working", "pending", "pending", "pending"]);
    expect(stageStates(null, false)).toEqual(["working", "pending", "pending", "pending"]);
    // A file without pictures goes straight to sorting; the pictures stage counts as done.
    expect(stageStates("structure", false)).toEqual(["done", "done", "working", "pending"]);
    expect(stageStates("checks", true)).toEqual(["done", "done", "done", "done"]);
  });

  it("moves the bar forward stage by stage, up to where the found rows take over", () => {
    const spans = (["file", "pictures", "structure", "checks"] as const).map(stageSpan);
    for (let i = 1; i < spans.length; i++) expect(spans[i]![0]).toBe(spans[i - 1]![1]);
    expect(spans.at(-1)![1]).toBe(0.6);
  });

  it("says why a reading failed without anything from the file", () => {
    expect(failureText("unreadable")).toMatch(/couldn't open that file/);
    expect(failureText("gave_up")).toMatch(/on our side/);
    expect(failureText(null)).toMatch(/Try again/);
  });

  it("takes only known states and stages from the API", () => {
    const status = toStatus({
      id: "i1",
      state: "failed",
      stage: "sideways",
      error_code: "unreadable",
      file: { format: "pdf", size: 10, name: "Resume.pdf" },
    });
    expect(status).toEqual({
      id: "i1",
      state: "failed",
      stage: null,
      error_code: "unreadable",
      file: { format: "pdf", size: 10, name: "Resume.pdf" },
    });
    expect(toStatus({ id: "i2", state: "odd" }).state).toBe("reading");
  });
});

describe("a card already in the person's cards", () => {
  const match = { card_id: "c1", headline: "Contoso Bank", same: false };

  it("keeps only well-formed matches from the API", () => {
    expect(
      toMatches({
        "card-1": { card_id: "c1", headline: "Contoso Bank", same: true },
        "card-2": { card_id: 7, headline: "x" },
        "card-3": null,
      }),
    ).toEqual({ "card-1": { card_id: "c1", headline: "Contoso Bank", same: true } });
    expect(toMatches(undefined)).toEqual({});
  });

  it("says what approving does with each choice", () => {
    expect(matchNote(match, "update")).toMatch(/next version/);
    expect(matchNote(match, "keep")).toMatch(/keeps your card “Contoso Bank” as it is/);
    expect(matchNote(match, "separate")).toMatch(/separate card/);
    expect(matchNote({ ...match, same: true }, "update")).toMatch(/changes nothing/);
  });
});
