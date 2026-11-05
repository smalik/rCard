import { describe, expect, it } from "vitest";

import {
  changeCount,
  compareResumes,
  diffSummary,
  mergeOrdered,
  steady,
} from "./resume-diff";
import type { RenderedEntry, RenderedItem, RenderedResume } from "./resumes";

// A made-up person's resume, read as pages.
function item(card: string, text = card, kind = "accomplishment"): RenderedItem {
  return { card, kind: kind as RenderedItem["kind"], text, detail: "", wording: "main", date: "" };
}

function job(card: string, roles: Record<string, RenderedItem[]>, fold = false): RenderedEntry {
  return {
    card,
    employer: card,
    location: "",
    dates: "",
    fold_earlier: fold,
    earlier_titles: [],
    roles: Object.entries(roles).map(([title, items]) => ({
      card: title === "-" ? null : title,
      title: title === "-" ? "" : title,
      dates: "",
      items,
    })),
    hidden: [],
  };
}

function page(entries: RenderedEntry[], sections: RenderedResume["sections"] = []): RenderedResume {
  return {
    header: {
      name: "Avery Quinn",
      headline: "",
      email: "avery.quinn@example.com",
      phone: "",
      location: "Chicago, IL",
      links: [],
      summary: "",
    },
    entries,
    sections,
    left_out: [],
    missing: 0,
  };
}

describe("ordering", () => {
  it("places what was taken out after the line it followed", () => {
    const merged = mergeOrdered(["a", "b", "c", "d"], ["a", "x", "d"], (k) => k);
    expect(merged.map((m) => `${m.presence}:${m.item}`)).toEqual([
      "same:a",
      "removed:b",
      "removed:c",
      "added:x",
      "same:d",
    ]);
    expect(mergeOrdered(["a", "b"], ["b"], (k) => k).map((m) => m.item)).toEqual(["a", "b"]);
  });

  it("finds the fewest moves", () => {
    // Moving c to the top moves one thing, not three.
    expect([...steady(["a", "b", "c"], ["c", "a", "b"])].sort()).toEqual(["a", "b"]);
    expect([...steady(["a", "b"], ["a", "b"])].sort()).toEqual(["a", "b"]);
  });
});

describe("compareResumes", () => {
  const before = page(
    [
      job("Northwind", { Director: [item("late", "Cut late shipments by 22%"), item("forecast")] }),
      job("Brightline", { Consultant: [item("freight")] }),
    ],
    [{ kind: "education", label: "Education", items: [item("degree", "B.S.", "education")] }],
  );

  it("sees nothing when nothing changed", () => {
    const diff = compareResumes(before, before);
    expect(changeCount(diff)).toBe(0);
    expect(diffSummary(diff)).toBeNull();
  });

  it("marks lines brought in, left out and reworded, in place", () => {
    const after = page(
      [
        job("Northwind", {
          Director: [item("late", "Cut late payments by 22%"), item("mentoring")],
        }),
        job("Brightline", { Consultant: [item("freight")] }),
      ],
      before.sections,
    );
    const diff = compareResumes(before, after);
    const lines = diff.entries[0]!.roles[0]!.lines;
    expect(lines.map((l) => [l.card, l.presence])).toEqual([
      ["late", "same"],
      ["forecast", "removed"],
      ["mentoring", "added"],
    ]);
    expect(lines[0]!.was).toBe("Cut late shipments by 22%");
    expect(diff.counts).toMatchObject({ added: 1, removed: 1, reworded: 1, moved: 0 });
    expect(diffSummary(diff)).toBe("1 line added, 1 line left out, 1 reworded");
  });

  it("shows a job left out with its lines, and one moved", () => {
    const after = page([job("Brightline", { Consultant: [item("freight")] })], before.sections);
    const diff = compareResumes(before, after);
    expect(diff.entries.map((e) => [e.card, e.presence])).toEqual([
      ["Northwind", "removed"],
      ["Brightline", "same"],
    ]);
    expect(diff.entries[0]!.roles[0]!.lines.every((l) => l.presence === "removed")).toBe(true);
    expect(diff.counts.jobsRemoved).toBe(1);

    const swapped = page([before.entries[1]!, before.entries[0]!], before.sections);
    const moved = compareResumes(before, swapped);
    expect(moved.entries.filter((e) => e.moved).length).toBe(1);
    expect(diffSummary(moved)).toBe("1 moved");
  });

  it("notices lines that changed places under a title", () => {
    const after = page(
      [
        job("Northwind", { Director: [item("forecast"), item("late", "Cut late shipments by 22%")] }),
        before.entries[1]!,
      ],
      before.sections,
    );
    const diff = compareResumes(before, after);
    expect(diff.counts.moved).toBe(1);
    expect(diff.counts.added + diff.counts.removed).toBe(0);
  });

  it("treats folded titles as a fold, not as lines coming and going", () => {
    const unfolded = page([
      job("Northwind", { Director: [item("late")], "Senior Manager": [item("rollout")] }),
    ]);
    const folded = page([job("Northwind", { Director: [item("late"), item("rollout")] }, true)]);
    folded.entries[0]!.earlier_titles = ["Senior Manager (2017 – 2020)"];
    const diff = compareResumes(unfolded, folded);
    expect(diff.entries[0]!.fold).toBe("folded");
    expect(diff.counts).toMatchObject({ added: 0, removed: 0, moved: 0, folds: 1 });
  });

  it("keeps a line left out of a folded-away title in view", () => {
    const unfolded = page([
      job("Northwind", { Director: [item("late")], "Senior Manager": [item("rollout")] }),
    ]);
    const folded = page([job("Northwind", { Director: [item("late")] }, true)]);
    const lines = compareResumes(unfolded, folded).entries[0]!.roles[0]!.lines;
    expect(lines.map((l) => [l.card, l.presence])).toEqual([
      ["late", "same"],
      ["rollout", "removed"],
    ]);
  });

  it("lists what changed at the top", () => {
    const after = page(before.entries, before.sections);
    after.header = { ...after.header, phone: "312-555-0142", links: ["https://example.com"] };
    const diff = compareResumes(before, after);
    expect(diff.header.map((h) => [h.label, h.was, h.now])).toEqual([
      ["Phone", "", "312-555-0142"],
      ["Links", "", "https://example.com"],
    ]);
    expect(diffSummary(diff)).toBe("The top changed");
  });

  it("compares sections line by line", () => {
    const after = page(before.entries, [
      { kind: "education", label: "Education", items: [] },
      { kind: "skill", label: "Skills", items: [item("tools", "SQL", "skill")] },
    ]);
    const diff = compareResumes(before, after);
    expect(diff.sections.map((s) => [s.kind, s.presence, s.lines.map((l) => l.presence)])).toEqual([
      ["education", "same", ["removed"]],
      ["skill", "added", ["added"]],
    ]);
  });
});
