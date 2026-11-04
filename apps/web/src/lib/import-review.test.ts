import { describe, expect, it } from "vitest";

import {
  type Finding,
  type ProposedCard,
  acceptBody,
  bySeverity,
  cardsForFinding,
  contentProblems,
  dateSpan,
  findingsForCard,
  groupCards,
  initialDecisions,
  roleSubtitle,
  textToFact,
  toPreview,
  visibleFacts,
} from "./import-review";
import { isSameOrigin } from "./same-origin";

// A made-up person, as in the API's import tests.
function card(partial: Partial<ProposedCard> & Pick<ProposedCard, "ref" | "kind">): ProposedCard {
  return {
    content: { facts: {}, framing: { headline: partial.ref, body: "" } },
    role_ref: null,
    source_blocks: [],
    needs_check: [],
    ...partial,
  };
}

const ROLE_FACTS = { employer: "Fabrikam Inc.", title: "Senior Analyst", start: "2023-07", end: "present" };

const CARDS: ProposedCard[] = [
  card({ ref: "card-1", kind: "story", content: { facts: { use: "summary" }, framing: { headline: "Analytics consultant.", body: "" } }, source_blocks: [6] }),
  card({ ref: "card-2", kind: "role", role_ref: "role-1", content: { facts: ROLE_FACTS, framing: { headline: "Senior Analyst, Fabrikam Inc.", body: "" } }, source_blocks: [10] }),
  card({ ref: "card-3", kind: "accomplishment", role_ref: "role-1", content: { facts: { ...ROLE_FACTS, workstream: "Pricing", figures: ["4"] }, framing: { headline: "Rebuilt the discount model, lifting margin 4 points.", body: "" } }, source_blocks: [12] }),
  card({ ref: "card-4", kind: "role", role_ref: "role-2", content: { facts: { employer: "Contoso Staffing", client: "Northwind Health", title: "Consultant", start: "2019-01", end: "2023-06" }, framing: { headline: "Consultant, Northwind Health", body: "" } }, source_blocks: [16] }),
  card({ ref: "card-5", kind: "accomplishment", content: { facts: { figures: ["30%"] }, framing: { headline: "Cut claim review time 30%.", body: "" } }, source_blocks: [8] }),
  card({ ref: "card-6", kind: "skill", content: { facts: { category: "Tools", skills: ["SQL", "Python"] }, framing: { headline: "Tools", body: "SQL, Python" } }, source_blocks: [20] }),
  card({ ref: "card-7", kind: "accomplishment", content: { facts: { award: "Analyst of the Year", date: "2022-12" }, framing: { headline: "Analyst of the Year", body: "" } }, source_blocks: [22] }),
];

function finding(partial: Partial<Finding> & Pick<Finding, "rule" | "severity" | "about">): Finding {
  return { category: partial.rule.split(".")[0]!, title: partial.rule, detail: "", locations: [], ...partial };
}

describe("toPreview", () => {
  it("keeps the cards and findings but leaves the resume text and contact details behind", () => {
    const preview = toPreview({
      facts: { format: "docx", filename: "Riley Park resume.docx", pages: 1, word_count: 137 },
      contact: { name: "Riley Park", emails: ["riley.park@example.com"] },
      blocks: [{ index: 0, text: "Riley Park" }],
      sections: [],
      roles: [],
      cards: [{ ...CARDS[0], findings: ["ats.misfiled_summary"] }],
      findings: [finding({ rule: "content.cliches", severity: "note", about: "cards" })],
    });
    expect(preview.file).toEqual({ format: "docx", pages: 1, words: 137 });
    expect(preview.cards).toHaveLength(1);
    expect(preview.findings).toHaveLength(1);
    const text = JSON.stringify(preview);
    expect(text).not.toContain("riley.park@example.com");
    expect(text).not.toContain("Riley Park resume.docx");
    expect(text).not.toContain("blocks\":[{");
  });
});

describe("groupCards", () => {
  it("reads like a resume: summary, highlights, roles, skills, awards", () => {
    const groups = groupCards(CARDS);
    expect(groups.map((g) => g.key)).toEqual(["summary", "highlights", "role-1", "role-2", "skills", "awards"]);
    const role = groups.find((g) => g.key === "role-1")!;
    expect(role.roleCard).toBe("card-2");
    expect(role.refs).toEqual(["card-2", "card-3"]);
  });

  it("names a client engagement's agency under its heading", () => {
    expect(roleSubtitle(CARDS[3]!.content)).toBe("Jan 2019 – Jun 2023 · through Contoso Staffing");
    expect(dateSpan(ROLE_FACTS)).toBe("Jul 2023 – Present");
  });
});

describe("findings and cards", () => {
  const tense = finding({
    rule: "consistency.tense",
    severity: "improve",
    about: "cards",
    locations: [{ block: 12, excerpt: "Rebuilt the discount model" }],
  });
  const image = finding({
    rule: "ats.large_image",
    severity: "fix",
    about: "document",
    locations: [{ block: 12, excerpt: "a picture after this line" }],
  });

  it("links a finding to the cards built from its lines", () => {
    expect(cardsForFinding(tense, CARDS)).toEqual(["card-3"]);
  });

  it("shows only findings about the words on a card", () => {
    const notes = findingsForCard(CARDS[2]!, [image, tense], CARDS);
    expect(notes.map((n) => n.finding.rule)).toEqual(["consistency.tense"]);
    expect(notes[0]!.excerpts).toEqual(["Rebuilt the discount model"]);
  });

  it("tells apart cards built from sentences of the same paragraph", () => {
    const paragraph = [
      card({ ref: "p-1", kind: "accomplishment", role_ref: "role-9", content: { facts: {}, framing: { headline: "Built the claims model for the payer team.", body: "" } }, source_blocks: [30] }),
      card({ ref: "p-2", kind: "accomplishment", role_ref: "role-9", content: { facts: {}, framing: { headline: "Provide weekly reports to the board.", body: "" } }, source_blocks: [30] }),
    ];
    const slip = finding({
      rule: "consistency.tense",
      severity: "fix",
      about: "cards",
      locations: [{ block: 30, excerpt: "Provide weekly reports to the board." }],
    });
    expect(cardsForFinding(slip, paragraph)).toEqual(["p-2"]);
    expect(findingsForCard(paragraph[0]!, [slip], paragraph)).toEqual([]);
  });

  it("puts fixes before improvements before notes", () => {
    const note = finding({ rule: "content.cliches", severity: "note", about: "cards" });
    expect(bySeverity([note, tense, image]).map((f) => f.severity)).toEqual(["fix", "improve", "note"]);
  });

  it("doesn't repeat the role's employer, title and dates on its cards", () => {
    const decisions = initialDecisions(CARDS);
    expect(visibleFacts(CARDS[2]!, decisions["card-3"]!.content)).toEqual([
      ["Workstream", "Pricing"],
      ["Numbers", "4"],
    ]);
    expect(visibleFacts(CARDS[6]!, decisions["card-7"]!.content)).toEqual([
      ["Award", "Analyst of the Year"],
      ["Date", "Dec 2022"],
    ]);
  });
});

describe("saving", () => {
  it("sends only the cards the person kept, with their edits", () => {
    const decisions = initialDecisions(CARDS);
    decisions["card-1"]!.keep = false;
    decisions["card-3"] = {
      keep: true,
      edited: true,
      content: { ...CARDS[2]!.content, framing: { headline: "  Rebuilt the discount model.  ", body: "" } },
    };
    const body = acceptBody(CARDS, decisions);
    expect(body.cards).toHaveLength(CARDS.length - 1);
    expect(body.cards.map((c) => c.kind)).not.toContain("story");
    expect(body.cards[1]!.content.framing.headline).toBe("Rebuilt the discount model.");
  });

  it("explains what stops a card from saving", () => {
    const content = { facts: { start: "July 2023", end: "now" }, framing: { headline: " ", body: "" } };
    expect(contentProblems(content)).toEqual([
      "Add a headline.",
      "Write the start date as a year and month, like 2021-03.",
      "Write the end date as a year and month, like 2021-03, or as present.",
    ]);
    expect(contentProblems(CARDS[1]!.content)).toEqual([]);
  });

  it("reads edited facts back as the kind of value they were", () => {
    expect(textToFact("SQL, Python, , dbt", ["SQL"])).toEqual(["SQL", "Python", "dbt"]);
    expect(textToFact("42", 40)).toBe(42);
    expect(textToFact("about 40", 40)).toBe("about 40");
    expect(textToFact("  ", "Fabrikam")).toBeUndefined();
  });
});

describe("isSameOrigin", () => {
  const request = (headers: Record<string, string>) =>
    new Request("http://localhost:3000/import/preview", { method: "POST", headers });

  it("accepts Plytos's own pages", () => {
    expect(isSameOrigin(request({ "sec-fetch-site": "same-origin" }))).toBe(true);
    expect(isSameOrigin(request({ origin: "http://localhost:3000", host: "localhost:3000" }))).toBe(true);
  });

  it("refuses other sites and requests that don't say where they came from", () => {
    expect(isSameOrigin(request({ "sec-fetch-site": "cross-site" }))).toBe(false);
    expect(isSameOrigin(request({ origin: "https://evil.example", host: "localhost:3000" }))).toBe(false);
    expect(isSameOrigin(request({}))).toBe(false);
  });
});
