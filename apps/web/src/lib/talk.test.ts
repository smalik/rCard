import { describe, expect, it } from "vitest";

import {
  awaitingReply,
  cleanMessage,
  dayLabel,
  fromNotes,
  groupByDay,
  MAX_MESSAGE,
  type Message,
  merge,
  monthLabel,
  type Proposal,
  type ProposedCard,
  withWording,
} from "./talk";

function message(id: string, at: string, author: Message["author"] = "person"): Message {
  return { id, author, channel: "app", text: id, created_at: at, proposal: null };
}

const card: ProposedCard = {
  kind: "accomplishment",
  missing: "Did late shipments drop?",
  content: {
    parent: "job",
    facts: { date: "2026-09", figures: ["9"] },
    framing: { headline: "Rolled a carrier scorecard out to all 9 carriers", body: "" },
  },
};

function proposal(cites: number, state: Proposal["state"] = "open"): Proposal {
  return {
    id: "p",
    agent: "stitcher",
    kind: "new_card",
    state,
    card_id: null,
    cites: Array.from({ length: cites }, (_, i) => `n${i}`),
    body: { message: "I think these notes are one win.", card },
    created_at: "2026-11-04T10:00:00Z",
    decided_at: null,
    result_version_id: null,
  };
}

describe("cleanMessage", () => {
  it("trims, and refuses empty or overlong messages", () => {
    expect(cleanMessage("  shipped it \n")).toBe("shipped it");
    expect(cleanMessage("   ")).toBeNull();
    expect(cleanMessage("x".repeat(MAX_MESSAGE + 1))).toBeNull();
  });
});

describe("merge", () => {
  it("adds new messages in order and replaces ones already there", () => {
    const thread = [message("a", "2026-11-04T10:00:00Z"), message("c", "2026-11-04T10:02:00Z")];
    const decided = { ...message("a", "2026-11-04T10:00:00Z"), text: "updated" };
    const merged = merge(thread, [message("b", "2026-11-04T10:01:00Z"), decided]);
    expect(merged.map((m) => m.id)).toEqual(["a", "b", "c"]);
    expect(merged[0]?.text).toBe("updated");
  });
});

describe("awaitingReply", () => {
  const now = new Date("2026-11-04T10:00:30Z");
  it("waits after the person speaks, until Plytos answers or time runs out", () => {
    expect(awaitingReply([message("a", "2026-11-04T10:00:10Z")], now)).toBe(true);
    expect(
      awaitingReply(
        [message("a", "2026-11-04T10:00:10Z"), message("b", "2026-11-04T10:00:20Z", "plytos")],
        now,
      ),
    ).toBe(false);
    expect(awaitingReply([message("a", "2026-11-04T09:58:00Z")], now)).toBe(false);
    expect(awaitingReply([], now)).toBe(false);
  });
});

describe("days", () => {
  const now = new Date(2026, 10, 4, 15, 0);
  it("names recent days and dates older ones", () => {
    expect(dayLabel(new Date(2026, 10, 4, 9, 0).toISOString(), now)).toBe("Today");
    expect(dayLabel(new Date(2026, 10, 3, 23, 0).toISOString(), now)).toBe("Yesterday");
    expect(dayLabel(new Date(2026, 10, 1, 12, 0).toISOString(), now)).toBe("Sunday");
    expect(dayLabel(new Date(2026, 8, 14, 12, 0).toISOString(), now)).toBe("Sep 14");
    expect(dayLabel(new Date(2025, 8, 14, 12, 0).toISOString(), now)).toBe("Sep 14, 2025");
  });

  it("groups the thread by day", () => {
    const thread = [
      message("a", new Date(2026, 10, 3, 9, 0).toISOString()),
      message("b", new Date(2026, 10, 4, 9, 0).toISOString()),
      message("c", new Date(2026, 10, 4, 9, 5).toISOString()),
    ];
    expect(groupByDay(thread, now).map((g) => [g.label, g.messages.length])).toEqual([
      ["Yesterday", 1],
      ["Today", 2],
    ]);
  });
});

describe("offers", () => {
  it("keeps the facts and changes only the wording", () => {
    const content = withWording(card, "  Built a scorecard for 9 carriers ", " Cut delays. ");
    expect(content.facts).toEqual(card.content.facts);
    expect(content.parent).toBe("job");
    expect(content.framing).toEqual({ headline: "Built a scorecard for 9 carriers", body: "Cut delays." });
  });

  it("says how many notes a win came from", () => {
    expect(fromNotes(proposal(0))).toBe("");
    expect(fromNotes(proposal(1))).toBe("from one of your notes");
    expect(fromNotes(proposal(3))).toBe("from 3 of your notes");
  });

  it("shows month dates in words", () => {
    expect(monthLabel("2026-09")).toBe("Sep 2026");
    expect(monthLabel("2026-13")).toBe("2026-13");
    expect(monthLabel("Fall 2026")).toBe("Fall 2026");
  });
});
