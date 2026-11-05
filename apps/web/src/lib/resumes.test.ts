import { describe, expect, it } from "vitest";

import {
  askText,
  bringBack,
  changesLabel,
  cleanContent,
  cleanLine,
  leaveOut,
  lineParts,
  move,
  moveContextLine,
  moveLine,
  type NewResume,
  proposalSize,
  type ResumeContent,
  resumeFor,
  type ResumeSummary,
  type ResumeVersion,
  sameContent,
  setFold,
  setHeader,
  switchOff,
  switchOn,
  switchOnContext,
  versionAuthor,
  versionLabel,
} from "./resumes";

const HEADER = {
  name: "Avery Quinn",
  headline: "",
  email: "avery.quinn@example.com",
  phone: "",
  location: "Chicago, IL",
  links: [],
  summary: "",
};

function content(): ResumeContent {
  return {
    header: HEADER,
    entries: [
      { card: "northwind", fold_earlier: false, items: [{ card: "late" }, { card: "forecast" }] },
      { card: "brightline", items: [{ card: "freight" }] },
    ],
    context: [{ card: "degree" }],
  };
}

function version(over: Partial<ResumeVersion> = {}): ResumeVersion {
  return {
    id: "v",
    number: 2,
    author_kind: "person",
    author_ref: null,
    created_at: "2026-11-04T10:00:00Z",
    synced_parent_version_id: null,
    redacted: false,
    names: [],
    note: null,
    ...over,
  };
}

describe("changing which lines show", () => {
  it("switches a line off wherever it is, and leaves the original alone", () => {
    const before = content();
    const after = switchOff(before, "forecast");
    expect(after.entries[0]!.items.map((i) => i.card)).toEqual(["late"]);
    expect(before.entries[0]!.items).toHaveLength(2);
    expect(switchOff(before, "degree").context).toEqual([]);
  });

  it("switches a line on once, under its employment", () => {
    const once = switchOn(switchOff(content(), "forecast"), "northwind", "forecast");
    expect(once.entries[0]!.items.map((i) => i.card)).toEqual(["late", "forecast"]);
    expect(switchOn(once, "northwind", "forecast").entries[0]!.items).toHaveLength(2);
    expect(switchOn(once, "nowhere", "x")).toEqual(once);
  });

  it("leaves an employment out and brings it back empty", () => {
    const out = leaveOut(content(), "brightline");
    expect(out.entries.map((e) => e.card)).toEqual(["northwind"]);
    const back = bringBack(out, "brightline");
    expect(back.entries.at(-1)).toEqual({ card: "brightline", fold_earlier: false, items: [] });
    expect(bringBack(back, "brightline").entries).toHaveLength(2);
  });

  it("folds titles and moves employments within bounds", () => {
    expect(setFold(content(), "northwind", true).entries[0]!.fold_earlier).toBe(true);
    expect(move(content(), "brightline", -1).entries.map((e) => e.card)).toEqual([
      "brightline",
      "northwind",
    ]);
    expect(move(content(), "northwind", -1)).toEqual(content());
    expect(move(content(), "brightline", 1)).toEqual(content());
  });

  it("compares content without the version note", () => {
    expect(sameContent(content(), { ...content(), note: "Back to version 1" })).toBe(true);
    expect(sameContent(content(), switchOff(content(), "late"))).toBe(false);
  });
});

describe("saying it plainly", () => {
  const item = { card: "c", wording: "main" as const, date: "" };

  it("shows each line's full text and the details that belong on the page", () => {
    const long = "Led the migration of ".repeat(12).trim();
    expect(
      lineParts({ ...item, kind: "accomplishment", text: `${long.slice(0, 50)}…`, detail: long }),
    ).toEqual({ text: long, detail: "" });
    expect(
      lineParts({ ...item, kind: "accomplishment", text: "Cut costs", detail: "Context." }),
    ).toEqual({ text: "Cut costs", detail: "" });
    expect(lineParts({ ...item, kind: "skill", text: "Skills", detail: "SQL, Python" })).toEqual({
      text: "SQL, Python",
      detail: "",
    });
    expect(lineParts({ ...item, kind: "skill", text: "Tools", detail: "Excel" }).text).toBe(
      "Tools: Excel",
    );
    expect(
      lineParts({ ...item, kind: "education", text: "B.S. Engineering", detail: "Honors" }),
    ).toEqual({ text: "B.S. Engineering", detail: "Honors" });
    expect(lineParts({ ...item, kind: "skill", text: "Skills", detail: "" }).text).toBe("Skills");
  });

  it("names who made a version", () => {
    expect(versionAuthor(version())).toBe("You");
    expect(versionAuthor(version({ author_kind: "ai", author_ref: "assembler" }))).toBe(
      "Assembler",
    );
    expect(versionAuthor(version({ author_kind: "ai", author_ref: "stitcher" }))).toBe("Plytos");
  });

  it("labels a version by its number and latest name", () => {
    expect(versionLabel(version())).toBe("Version 2");
    expect(versionLabel(version({ names: ["Sent to Contoso", "Draft"] }))).toBe(
      "Version 2 · Sent to Contoso",
    );
  });

  it("says who a resume is for", () => {
    const own = { target_name: null } as ResumeSummary;
    expect(resumeFor(own)).toBe("Your own, as you wrote it");
    expect(resumeFor({ ...own, target_name: "Fintech" })).toBe("For Fintech");
  });

  it("sizes a proposed resume", () => {
    const proposed = { content: content(), rewordings: [] } as unknown as NewResume;
    expect(proposalSize(proposed)).toBe("2 jobs · 4 lines");
    const one = {
      content: { ...content(), entries: [content().entries[1]!], context: [] },
      rewordings: [{ card: "freight", framing: { headline: "x", body: "" } }],
    } as unknown as NewResume;
    expect(proposalSize(one)).toBe("1 job · 1 line · 1 reworded");
    expect(changesLabel(1)).toBe("1 change");
    expect(changesLabel(3)).toBe("3 changes");
  });

  it("words the ask for a version", () => {
    expect(askText("My resume", "  fintech ops roles ")).toBe(
      "Make a version of My resume for fintech ops roles",
    );
  });
});

describe("checking what the browser sends", () => {
  it("takes resume content and refuses anything else", () => {
    expect(cleanContent(content())).toEqual(content());
    expect(cleanContent(null)).toBeNull();
    expect(cleanContent([])).toBeNull();
    expect(cleanContent({ ...content(), entries: "no" })).toBeNull();
    expect(cleanContent({ ...content(), entries: [{ card: 1, items: [] }] })).toBeNull();
    expect(cleanContent({ ...content(), entries: [{ card: "a" }] })).toBeNull();
    expect(cleanContent({ ...content(), context: [{}] })).toBeNull();
  });

  it("trims a line and refuses empty or long ones", () => {
    expect(cleanLine("  Fintech  ", 20)).toBe("Fintech");
    expect(cleanLine("   ", 20)).toBeNull();
    expect(cleanLine("x".repeat(21), 20)).toBeNull();
    expect(cleanLine(5, 20)).toBeNull();
  });
});

describe("arranging lines", () => {
  it("moves a line among the lines shown with it, leaving the rest in place", () => {
    const start: ResumeContent = {
      header: HEADER,
      entries: [
        {
          card: "northwind",
          // late and forecast show under Director; rollout under Senior Manager.
          items: [{ card: "late" }, { card: "rollout" }, { card: "forecast", wording: "main" }],
        },
      ],
      context: [],
    };
    const next = moveLine(start, "northwind", ["late", "forecast"], "forecast", -1);
    expect(next.entries[0]!.items).toEqual([
      { card: "forecast", wording: "main" },
      { card: "rollout" },
      { card: "late" },
    ]);
    expect(start.entries[0]!.items[0]!.card).toBe("late");
    // Off either end, or a line it doesn't hold: nothing moves.
    expect(moveLine(start, "northwind", ["late", "forecast"], "late", -1)).toEqual(start);
    expect(moveLine(start, "northwind", ["late", "gone"], "late", 1)).toEqual(start);
  });

  it("moves a line within its section, and brings a card in at the end", () => {
    const start: ResumeContent = {
      header: HEADER,
      entries: [],
      context: [{ card: "degree" }, { card: "tools" }, { card: "cert" }],
    };
    const next = moveContextLine(start, ["degree", "cert"], "cert", -1);
    expect(next.context.map((i) => i.card)).toEqual(["cert", "tools", "degree"]);
    const added = switchOnContext(start, "award");
    expect(added.context.at(-1)).toEqual({ card: "award", wording: "auto" });
    expect(switchOnContext(added, "award").context).toHaveLength(4);
  });

  it("sets the top, dropping empty links", () => {
    const next = setHeader(content(), { ...HEADER, links: ["https://example.com", " "] });
    expect(next.header.links).toEqual(["https://example.com"]);
  });
});
