import { describe, expect, it } from "vitest";

import {
  attachmentKindFor,
  buildLibrary,
  cardDates,
  changedSince,
  cleanContent,
  evidence,
  formatDate,
  isWebAddress,
  type LibraryCard,
  listFact,
  move,
  relativeTime,
  tenure,
  withOrder,
} from "./library";

let made = 0;

// A made-up card; every one is created a minute after the one before.
function card(
  kind: LibraryCard["kind"],
  headline: string,
  facts: Record<string, string | string[]> = {},
  more: Partial<LibraryCard> = {},
): LibraryCard {
  made += 1;
  const at = new Date(Date.UTC(2026, 0, 1, 0, made)).toISOString();
  return {
    id: `card-${made}`,
    kind,
    status: "approved",
    parent_id: null,
    sort_key: null,
    created_at: at,
    content: {
      parent: more.parent_id ?? null,
      facts,
      framing: { headline, body: "", shown_facts: null },
      attachments: [],
    },
    version_id: `version-${made}`,
    version: 1,
    version_author: "person",
    updated_at: at,
    variants: 0,
    variants_behind: 0,
    ...more,
  };
}

describe("buildLibrary", () => {
  it("puts titles, clients and accomplishments under their employer", () => {
    const employer = card("employment", "Northwind Logistics", { employer: "Northwind Logistics" });
    const director = card("position", "Director", {}, { parent_id: employer.id });
    const analyst = card("position", "Analyst", {}, { parent_id: employer.id });
    const won = card("accomplishment", "Cut late shipments by 22%", {}, { parent_id: director.id });
    const client = card("engagement", "Fabrikam Foods", {}, { parent_id: director.id });
    const forClient = card("accomplishment", "Redesigned routing", {}, { parent_id: client.id });
    const across = card("accomplishment", "Ran peak season", {}, { parent_id: employer.id });

    const view = buildLibrary([forClient, analyst, won, employer, across, client, director]);

    expect(view.experience).toHaveLength(1);
    const job = view.experience[0]!;
    expect(job.card.id).toBe(employer.id);
    expect(job.positions.map((p) => p.card.id)).toEqual([director.id, analyst.id]);
    expect(job.positions[0]!.items.map((c) => c.id)).toEqual([won.id]);
    expect(job.positions[0]!.engagements[0]!.items.map((c) => c.id)).toEqual([forClient.id]);
    expect(job.items.map((c) => c.id)).toEqual([across.id]);
  });

  it("follows the person's order, with unplaced cards after, oldest first", () => {
    const employer = card("employment", "Northwind Logistics");
    const a = card("position", "A", {}, { parent_id: employer.id });
    const b = card("position", "B", {}, { parent_id: employer.id, sort_key: 1 });
    const c = card("position", "C", {}, { parent_id: employer.id, sort_key: 0 });
    const d = card("position", "D", {}, { parent_id: employer.id });

    const view = buildLibrary([employer, a, b, c, d]);

    expect(view.experience[0]!.positions.map((p) => p.card.content?.framing.headline)).toEqual([
      "C",
      "B",
      "A",
      "D",
    ]);
  });

  it("sorts top-level cards into their sections, with awards apart from highlights", () => {
    const school = card("education", "University of Wisconsin–Madison");
    const award = card("accomplishment", "Leader of the Year", { award: "Leader of the Year" });
    const loose = card("accomplishment", "Spoke at a summit");
    const cert = card("credential", "CSCP");
    const skills = card("skill", "Tools", { skills: ["SQL"] });
    const project = card("project", "Routing benchmark");
    const talk = card("activity", "Midwest Logistics Summit");

    const view = buildLibrary([school, award, loose, cert, skills, project, talk]);

    expect(view.education).toEqual([school]);
    expect(view.awards).toEqual([award]);
    expect(view.highlights).toEqual([loose]);
    expect(view.credentials).toEqual([cert]);
    expect(view.skills).toEqual([skills]);
    expect(view.projects).toEqual([project]);
    expect(view.activities).toEqual([talk]);
  });
});

describe("dates", () => {
  it("reads months, years and open ends", () => {
    expect(formatDate("2005-06")).toBe("Jun 2005");
    expect(formatDate("2005")).toBe("2005");
    expect(formatDate("present")).toBe("Present");
    expect(formatDate("Spring term")).toBe("Spring term");
  });

  it("prefers a single date over a range", () => {
    expect(cardDates(card("credential", "CSCP", { date: "2018" }))).toBe("2018");
    expect(cardDates(card("position", "Director", { start: "2020-01", end: "present" }))).toBe(
      "Jan 2020 – Present",
    );
    expect(cardDates(card("position", "Director"))).toBe("");
  });

  it("counts tenure in years and months, both months included", () => {
    const now = new Date(Date.UTC(2026, 10, 4));
    expect(tenure("2014-03", "present", now)).toBe("12 yrs 9 mos");
    expect(tenure("2010-07", "2014-02", now)).toBe("3 yrs 8 mos");
    expect(tenure("2020-01", "2020-01", now)).toBe("1 mo");
    expect(tenure("2019", "2019", now)).toBe("1 yr");
    expect(tenure("2020-05", "2019-01", now)).toBe("");
    expect(tenure("", "present", now)).toBe("");
  });

  it("says how long ago in a few words", () => {
    const now = new Date("2026-11-04T12:00:00Z");
    expect(relativeTime("2026-11-04T11:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-11-04T11:55:00Z", now)).toBe("5 min ago");
    expect(relativeTime("2026-11-04T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-10-30T12:00:00Z", now)).toBe("5 d ago");
    expect(relativeTime("2026-01-15T12:00:00Z", now)).toBe("Jan 2026");
  });
});

describe("evidence", () => {
  it("counts figures, attachments and a told story", () => {
    const bare = card("accomplishment", "Ran peak season");
    expect(evidence(bare)).toEqual({ figures: 0, attachments: 0, level: 0 });

    const backed = card("accomplishment", "Cut late shipments", { figures: ["40 people", "−22%"] });
    backed.content!.attachments = [
      { kind: "paper", url: "https://example.org/a.pdf", title: "Write-up", note: "" },
    ];
    backed.content!.framing.body = "Moved three sites onto one daily plan with shared cut-off times.";
    expect(evidence(backed)).toEqual({ figures: 2, attachments: 1, level: 3 });
  });

  it("reads a list fact written as one string", () => {
    expect(listFact(card("skill", "Tools", { skills: "SQL" }), "skills")).toEqual(["SQL"]);
    expect(listFact(card("skill", "Tools", { skills: ["SQL", " "] }), "skills")).toEqual(["SQL"]);
  });
});

describe("attachments", () => {
  it("guesses what an address points at", () => {
    expect(attachmentKindFor("https://github.com/example/route-planner")).toBe("repo");
    expect(attachmentKindFor("https://www.gitlab.com/example/x")).toBe("repo");
    expect(attachmentKindFor("https://arxiv.org/abs/2401.00001")).toBe("paper");
    expect(attachmentKindFor("https://doi.org/10.1000/182")).toBe("paper");
    expect(attachmentKindFor("https://example.com/talks/notes.PDF")).toBe("paper");
    expect(attachmentKindFor("https://example.com/case-study")).toBe("link");
    expect(attachmentKindFor("not an address")).toBe("link");
  });

  it("accepts only web addresses", () => {
    expect(isWebAddress("https://example.com/x")).toBe(true);
    expect(isWebAddress(" http://example.com ")).toBe(true);
    expect(isWebAddress("javascript:alert(1)")).toBe(false);
    expect(isWebAddress("ftp://example.com/file")).toBe(false);
    expect(isWebAddress("example.com")).toBe(false);
  });
});

describe("cleanContent", () => {
  const valid = {
    parent: null,
    facts: { figures: ["40 people"], start: "2020-01" },
    framing: { headline: " Cut late shipments ", body: "", shown_facts: null },
    attachments: [{ kind: "repo", url: "https://github.com/example/x", title: "x", note: "" }],
  };

  it("keeps a well-formed card, trimmed", () => {
    const clean = cleanContent(valid);
    expect(clean?.framing.headline).toBe("Cut late shipments");
    expect(clean?.attachments).toHaveLength(1);
    expect(clean?.facts.figures).toEqual(["40 people"]);
  });

  it("treats missing attachments as none", () => {
    const old: Record<string, unknown> = { ...valid };
    delete old.attachments;
    expect(cleanContent(old)?.attachments).toEqual([]);
  });

  it("refuses what the API would refuse", () => {
    expect(cleanContent(null)).toBeNull();
    expect(cleanContent({ ...valid, framing: { headline: "  " } })).toBeNull();
    expect(cleanContent({ ...valid, facts: { "Bad Key": "x" } })).toBeNull();
    expect(cleanContent({ ...valid, facts: { count: { nested: true } } })).toBeNull();
    expect(
      cleanContent({
        ...valid,
        attachments: [{ kind: "link", url: "javascript:alert(1)", title: "x", note: "" }],
      }),
    ).toBeNull();
    expect(
      cleanContent({
        ...valid,
        attachments: [{ kind: "video", url: "https://example.com", title: "x", note: "" }],
      }),
    ).toBeNull();
    expect(
      cleanContent({ ...valid, attachments: Array(21).fill(valid.attachments[0]) }),
    ).toBeNull();
  });
});

describe("order", () => {
  it("moves one item and leaves the list alone when out of range", () => {
    expect(move(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(move(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b"], 0, 5)).toEqual(["a", "b"]);
  });

  it("places one parent's children and leaves others as they were", () => {
    const employer = card("employment", "Northwind");
    const a = card("position", "A", {}, { parent_id: employer.id });
    const b = card("position", "B", {}, { parent_id: employer.id });
    const elsewhere = card("position", "C", {}, { parent_id: "someone-else", sort_key: 7 });

    const next = withOrder([employer, a, b, elsewhere], employer.id, [b.id, a.id]);

    expect(next.find((c) => c.id === b.id)?.sort_key).toBe(0);
    expect(next.find((c) => c.id === a.id)?.sort_key).toBe(1);
    expect(next.find((c) => c.id === elsewhere.id)?.sort_key).toBe(7);
    expect(next.find((c) => c.id === employer.id)?.sort_key).toBeNull();
  });

  it("notices new cards and new versions, not unchanged ones", () => {
    const a = card("position", "A");
    const b = card("position", "B");
    const c = card("position", "C");
    const changed = changedSince([a, b], [a, { ...b, version_id: "version-next" }, c]);
    expect([...changed].sort()).toEqual([b.id, c.id].sort());
  });
});
