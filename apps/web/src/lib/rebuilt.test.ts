import { describe, expect, it } from "vitest";

import type { CardKind } from "./cards";
import { toReview } from "./imports";
import {
  canMoveUnder,
  coverage,
  coverageDetail,
  coverageText,
  cardsByLine,
  fateOf,
  fateText,
  groupQuestions,
  isSure,
  linesOf,
  moveTargets,
  placeName,
  questions,
  rebuild,
  showsPages,
  toResumeFile,
} from "./rebuilt";

// A made-up resume, as the API sends an import of it.
const LINES = [
  "Riley Park",
  "riley@example.com | 555-0100",
  "SUMMARY",
  "Operations leader who turns around late shipments.",
  "PROFESSIONAL EXPERIENCE",
  "Northwind Logistics, Seattle, WA 2018 – Present",
  "Director of Operations 2021 – Present",
  "Cut late shipments by 22%",
  "Operations Manager 2018 – 2021",
  "Late shipments down 25% across 3 sites",
  "Fabrikam, Portland, OR 2015 – 2018",
  "Analyst",
  "Built the weekly forecast",
  "EDUCATION",
  "University of Washington, B.A. Economics, 2015",
  "Page 1 of 1",
];

function card(
  ref: string,
  kind: CardKind,
  headline: string,
  blocks: number[],
  parent: string | null,
  facts: Record<string, string> = {},
  extra: Record<string, unknown> = {},
) {
  return {
    ref,
    kind,
    content: { facts, framing: { headline, body: "" } },
    parent_ref: parent,
    role_ref: null,
    source_blocks: blocks,
    needs_check: [],
    placement: null,
    ...extra,
  };
}

function raw(options: { format?: string; boxes?: boolean; progress?: object; twice?: boolean } = {}) {
  const boxes = options.boxes ?? true;
  return {
    id: "0190a7a2-0000-7000-8000-000000000000",
    file: { format: options.format ?? "pdf", size: 30_000, name: "Riley Park.pdf" },
    to_settle: [0],
    progress: options.progress ?? {},
    result: {
      facts: { format: options.format ?? "pdf", pages: 1, word_count: 80, page_sizes: [[8.5, 11]] },
      contact: { blocks: [0, 1] },
      blocks: LINES.map((text, index) => ({
        index,
        text,
        page: 1,
        is_bullet: [7, 9, 12].includes(index),
        bold: [2, 4, 13].includes(index),
        all_caps: [2, 4, 13].includes(index),
        box: boxes ? [0.1, index * 0.05, 0.9, index * 0.05 + 0.02] : null,
      })),
      sections: [
        { kind: "contact", heading: null, heading_block: null, blocks: [0, 1] },
        { kind: "summary", heading: "SUMMARY", heading_block: 2, blocks: [3] },
        {
          kind: "experience",
          heading: "PROFESSIONAL EXPERIENCE",
          heading_block: 4,
          blocks: [5, 6, 7, 8, 9, 10, 11, 12],
        },
        { kind: "education", heading: "EDUCATION", heading_block: 13, blocks: [14] },
      ],
      lines: {
        lines: 16,
        on_cards: 11,
        contact: [0, 1],
        headings: [2, 4, 13],
        skipped: [{ block: 15, reason: "page_number" }],
        guessed: [],
      },
      cards: [
        card("card-1", "story", "Operations leader who turns around late shipments.", [3], null),
        card("card-2", "employment", "Northwind Logistics", [5], null, {
          employer: "Northwind Logistics",
          location: "Seattle, WA",
          start: "2018",
          end: "present",
        }),
        card("card-3", "position", "Director of Operations", [6], "card-2", {
          title: "Director of Operations",
          start: "2021",
          end: "present",
        }),
        card("card-4", "accomplishment", "Cut late shipments by 22%", [7], "card-3"),
        card("card-5", "position", "Operations Manager", [8], "card-2", {
          title: "Operations Manager",
          start: "2018",
          end: "2021",
        }),
        card("card-6", "accomplishment", "Late shipments down 25% across 3 sites", [9], "card-5"),
        card("card-7", "employment", "Fabrikam", [10], null, { employer: "Fabrikam", start: "2015", end: "2018" }),
        card("card-8", "position", "Analyst", [11], "card-7", { title: "Analyst" }),
        card("card-9", "accomplishment", "Built the weekly forecast", [12], "card-8", {}, {
          placement: {
            question: "Which job is this from?",
            reason: "It reads like the forecasting work at Northwind.",
            choices: [
              { parent_ref: "card-8", label: "Fabrikam › Analyst" },
              { parent_ref: "card-5", label: "Northwind Logistics › Operations Manager" },
            ],
            moved_from: null,
          },
        }),
        card("card-10", "education", "University of Washington, B.A. Economics", [14], null, {
          institution: "University of Washington",
          date: "2015",
        }),
      ],
      findings: [
        {
          rule: "consistency.figures",
          severity: "fix",
          category: "consistency",
          about: "cards",
          title: "Two numbers for late shipments",
          detail: "",
          locations: [
            { block: 7, excerpt: "Cut late shipments by 22%", figure: "22%" },
            { block: 9, excerpt: "Late shipments down 25%", figure: "25%" },
            ...(options.twice ? [{ block: 9, excerpt: "down 25%", figure: "25%" }] : []),
          ],
        },
      ],
    },
  };
}

describe("the file", () => {
  it("keeps every line, where it sits, and where the rest went", () => {
    const file = toResumeFile(raw());
    expect(file.lines).toHaveLength(16);
    expect(file.lines[7]).toMatchObject({ block: 7, bullet: true, page: 1 });
    const [left, top, right] = file.lines[7]!.box!;
    expect([left, right]).toEqual([0.1, 0.9]);
    expect(top).toBeCloseTo(0.35);
    expect(file.pages).toEqual([{ number: 1, width: 8.5, height: 11 }]);
    expect(file.headings).toEqual([2, 4, 13]);
    expect(file.contact).toEqual([0, 1]);
    expect(file.skipped).toEqual({ 15: "page_number" });
    expect(showsPages(file)).toBe(true);
  });

  it("shows a scanned PDF as its pages, with what was read listed under them", () => {
    const scanned = raw({ boxes: false });
    for (const block of scanned.result.blocks) Object.assign(block, { where: "image" });
    expect(showsPages(toResumeFile(scanned))).toBe(true);
  });

  it("shows a file line by line when it can't light lines up on its pages", () => {
    expect(showsPages(toResumeFile(raw({ boxes: false })))).toBe(false);
    expect(showsPages(toResumeFile(raw({ format: "docx", boxes: false })))).toBe(false);
  });

  it("refuses a box that isn't one", () => {
    const bad = raw();
    bad.result.blocks[3]!.box = [0.5, 0.2, 0.4, 0.3];
    expect(toResumeFile(bad).lines[3]!.box).toBeNull();
  });

  it("finds where an older import's headings and contact went without an account", () => {
    const old = raw();
    (old.result as { lines: unknown }).lines = null;
    const file = toResumeFile(old);
    expect(file.headings).toEqual([2, 4, 13]);
    expect(file.contact).toEqual([0, 1]);
    expect(file.skipped).toEqual({});
  });
});

describe("every line is accounted for", () => {
  it("says so when every line went somewhere", () => {
    const review = toReview(raw());
    const c = coverage(toResumeFile(raw()), review);
    expect(c).toEqual({ lines: 16, onCards: 10, headings: 3, contact: 2, skipped: 1, loose: [] });
    expect(coverageText(c)).toBe("Every one of your 16 lines is here.");
    expect(coverageDetail(c)).toBe(
      "10 on cards, 3 headings, your contact details, 1 left off on purpose",
    );
  });

  it("owns up to a line it couldn't place", () => {
    const missing = raw();
    missing.result.cards = missing.result.cards.filter((c) => c.ref !== "card-10");
    const c = coverage(toResumeFile(missing), toReview(missing));
    expect(c.loose).toEqual([14]);
    expect(coverageText(c)).toBe(
      "15 of your 16 lines are here. 1 line Plytos couldn't place is marked in your file.",
    );
  });

  it("says in plain words what happened to a line on no card", () => {
    const file = toResumeFile(raw());
    const byLine = cardsByLine(toReview(raw()));
    expect(fateOf(7, file, byLine)).toEqual({ kind: "cards", refs: ["card-4"] });
    expect(fateText(fateOf(2, file, byLine))).toMatch(/^A heading/);
    expect(fateText(fateOf(0, file, byLine))).toMatch(/never on a card/);
    expect(fateText(fateOf(15, file, byLine))).toMatch(/page number/);
  });
});

describe("the resume, rebuilt", () => {
  it("follows the file's order and headings, a job at a time", () => {
    const review = toReview(raw());
    const sections = rebuild(review, toResumeFile(raw()));
    expect(sections.map((s) => [s.heading, s.headingBlock])).toEqual([
      ["SUMMARY", 2],
      ["PROFESSIONAL EXPERIENCE", 4],
      ["EDUCATION", 13],
    ]);
    const experience = sections[1]!;
    expect(experience.groups.map((g) => [g.kind, g.name])).toEqual([
      ["job", "Northwind Logistics"],
      ["job", "Fabrikam"],
    ]);
    const northwind = experience.groups[0]!;
    expect(northwind.rows.map((r) => [r.ref, r.depth])).toEqual([
      ["card-2", 0],
      ["card-3", 1],
      ["card-4", 2],
      ["card-5", 1],
      ["card-6", 2],
    ]);
    expect(northwind.rows[0]).toMatchObject({ dates: "2018 – Present", place: "Seattle, WA" });
    expect(sections[2]!.groups[0]).toMatchObject({ kind: "section", name: "Education" });
    expect(sections[2]!.groups[0]!.rows[0]!.dates).toBe("2015");
  });

  it("keeps a job where its employer is written when a line from elsewhere sits under it", () => {
    const moved = raw();
    // The summary's line, read as a result at Fabrikam: Fabrikam stays in Experience.
    const story = moved.result.cards.find((c) => c.ref === "card-1")!;
    Object.assign(story, { kind: "accomplishment", parent_ref: "card-8" });
    const sections = rebuild(toReview(moved), toResumeFile(moved));
    expect(sections.map((s) => s.heading)).toEqual(["PROFESSIONAL EXPERIENCE", "EDUCATION"]);
    expect(sections[0]!.groups.map((g) => g.name)).toEqual(["Northwind Logistics", "Fabrikam"]);
  });

  it("labels a run of lines with the workstream the file grouped them under", () => {
    const grouped = raw();
    for (const ref of ["card-4", "card-6"]) {
      const c = grouped.result.cards.find((x) => x.ref === ref)!;
      c.content.facts = { workstream: "Shipping" };
    }
    const [, experience] = rebuild(toReview(grouped), toResumeFile(grouped));
    const labels = experience!.groups[0]!.rows.map((r) => r.label?.name ?? null);
    // Each title starts a new run.
    expect(labels).toEqual([null, null, "Shipping", null, "Shipping"]);
  });

  it("moves a line to the job the person put it under", () => {
    const moved = raw({ progress: { moves: { "card-4": "card-8" } } });
    const review = toReview(moved);
    const [, experience] = rebuild(review, toResumeFile(moved));
    const fabrikam = experience!.groups[1]!;
    expect(fabrikam.rows.map((r) => r.ref)).toContain("card-4");
    expect(experience!.groups[0]!.rows.map((r) => r.ref)).not.toContain("card-4");
  });

  it("shows the person's own corrections", () => {
    const fixed = raw({
      progress: {
        fixes: {
          "card-6": { facts: {}, framing: { headline: "Late shipments down 25% at 3 sites", body: "" } },
        },
      },
    });
    const [, experience] = rebuild(toReview(fixed), toResumeFile(fixed));
    const row = experience!.groups[0]!.rows.find((r) => r.ref === "card-6");
    expect(row!.text).toBe("Late shipments down 25% at 3 sites");
  });

  it("finds a rebuilt line's partners in the file", () => {
    expect(linesOf("card-9", toReview(raw()))).toEqual([12]);
  });
});

describe("questions with the answer already picked", () => {
  it("asks each at the first line it's about", () => {
    const review = toReview(raw());
    const asked = questions(review);
    expect(asked.map((q) => [q.key, q.ref, q.picked, q.answered])).toEqual([
      ["place-card-9", "card-9", 0, null],
      ["settle-0", "card-4", 0, null],
    ]);
    expect(asked[0]!.choices.map((c) => c.label)).toEqual([
      "Fabrikam › Analyst",
      "Northwind Logistics › Operations Manager",
    ]);
    // "Not sure yet" isn't offered here: the person can leave the job unmarked.
    expect(asked[1]!.choices.map((c) => c.label)).toEqual(["It was 22%", "It was 25%"]);
  });

  it("picks the number the resume uses most", () => {
    const [, figures] = questions(toReview(raw({ twice: true })));
    expect(figures!.picked).toBe(1);
  });

  it("knows a question the person already answered", () => {
    const answered = raw({
      progress: {
        moves: { "card-9": "card-5" },
        settled: { "0": { answer: "chosen", value: "25%", changed: [] } },
      },
    });
    const asked = questions(toReview(answered));
    expect(asked.map((q) => q.answered)).toEqual([1, 1]);
  });

  it("counts a place the person chose that Plytos didn't suggest as their answer", () => {
    const moved = toReview(raw({ progress: { moves: { "card-9": "card-3" } } }));
    const [placed] = questions(moved);
    expect(placed!.answered).toBe(2);
    expect(placed!.choices[2]!.label).toBe("Northwind Logistics › Director of Operations");
  });

  it("holds back every job a question is about, not just the one it's asked in", () => {
    // One of the two numbers now sits under Fabrikam; the question is asked at Northwind.
    const split = raw({ progress: { moves: { "card-6": "card-8", "card-9": "card-8" } } });
    const review = toReview(split);
    const asked = questions(review);
    const [, experience] = rebuild(review, toResumeFile(split));
    const [northwind, fabrikam] = experience!.groups;
    expect(asked.find((q) => q.key === "settle-0")!.ref).toBe("card-4");
    expect(groupQuestions(fabrikam!, asked).map((q) => q.key)).toEqual(["place-card-9", "settle-0"]);
    expect(isSure(fabrikam!, review, asked)).toBe(false);
    expect(isSure(northwind!, review, asked)).toBe(false);
  });

  it("marks a job looks-right only when nothing in it is asked or guessed", () => {
    const review = toReview(raw());
    const asked = questions(review);
    const [, experience, education] = rebuild(review, toResumeFile(raw()));
    const [northwind, fabrikam] = experience!.groups;
    expect(groupQuestions(northwind!, asked).map((q) => q.key)).toEqual(["settle-0"]);
    expect(isSure(northwind!, review, asked)).toBe(false);
    expect(isSure(fabrikam!, review, asked)).toBe(false);
    expect(isSure(education!.groups[0]!, review, asked)).toBe(true);

    const settled = raw({
      progress: {
        moves: { "card-9": "card-8" },
        settled: { "0": { answer: "chosen", value: "22%", changed: [] } },
      },
    });
    const now = toReview(settled);
    const again = questions(now);
    const [, exp] = rebuild(now, toResumeFile(settled));
    expect(exp!.groups.map((g) => isSure(g, now, again))).toEqual([true, true]);
  });
});

describe("moving a line", () => {
  it("offers every job and title it could sit under but its own", () => {
    const review = toReview(raw());
    const line = review.cards.find((c) => c.ref === "card-4")!;
    const targets = moveTargets(line, review).map((t) => t.label);
    expect(targets).toContain("Northwind Logistics › Operations Manager");
    expect(targets).toContain("Fabrikam › Analyst");
    expect(targets).not.toContain("Northwind Logistics › Director of Operations");
    const title = review.cards.find((c) => c.ref === "card-5")!;
    expect(moveTargets(title, review).map((t) => t.ref)).toEqual(["card-7"]);
  });

  it("keeps to what the API allows", () => {
    const review = toReview(raw());
    const byRef = (ref: string) => review.cards.find((c) => c.ref === ref)!;
    expect(canMoveUnder(byRef("card-3"), byRef("card-7"))).toBe(true);
    expect(canMoveUnder(byRef("card-2"), byRef("card-7"))).toBe(false);
    expect(canMoveUnder(byRef("card-10"), byRef("card-3"))).toBe(false);
  });

  it("names a place the way the person knows it", () => {
    const review = toReview(raw());
    expect(placeName("card-8", review)).toBe("Fabrikam › Analyst");
    expect(placeName("card-2", review)).toBe("Northwind Logistics");
  });
});
