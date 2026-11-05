import { describe, expect, it } from "vitest";

import {
  awaitingReply,
  CHECK_IN_CHOICES,
  checkInTimes,
  cleanMessage,
  cleanPlan,
  dayLabel,
  fromNotes,
  groupByDay,
  MAX_MESSAGE,
  type Message,
  merge,
  monthLabel,
  NO_CHECK_INS,
  offerCheckIns,
  type Proposal,
  type ProposedCard,
  readingShared,
  resumeProgress,
  timeLabel,
  withWording,
} from "./talk";
import type { ImportSummary } from "./imports";

function message(id: string, at: string, author: Message["author"] = "person"): Message {
  return { id, author, channel: "app", text: id, created_at: at, proposal: null };
}

const card: ProposedCard = {
  kind: "accomplishment",
  missing: "Did late shipments drop?",
  content: {
    parent: "job",
    facts: { date: "2026-09" },
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

describe("a shared resume", () => {
  const resume: ImportSummary = {
    id: "r1",
    created_at: "2026-11-04T10:00:00Z",
    updated_at: "2026-11-04T10:00:00Z",
    state: "read",
    stage: null,
    file: { format: "docx", size: 1000, name: "Resume.docx" },
    cards: 26,
    approved: 0,
    later: 0,
    dropped: 0,
    to_settle: 2,
  };

  it("says how far along it is", () => {
    expect(resumeProgress(resume)).toBe("26 cards · 2 questions");
    expect(resumeProgress({ ...resume, approved: 4, to_settle: 1 })).toBe(
      "26 cards · 4 kept · 1 question",
    );
    expect(resumeProgress({ ...resume, approved: 20, later: 3, to_settle: 0 })).toBe(
      "26 cards · 20 kept · 3 set aside",
    );
  });

  it("follows a reading that's under way or failed", () => {
    const reading = { ...resume, state: "reading" as const, stage: "structure" as const, cards: 0 };
    expect(resumeProgress(reading)).toBe("Reading it now");
    const failed = { ...resume, state: "failed" as const, cards: 0 };
    expect(resumeProgress(failed)).toBe("Couldn't read it");
  });

  it("keeps the conversation waiting while a shared resume is read", () => {
    const shared = { ...message("a", "2026-11-04T09:00:00Z"), import_id: "r1" };
    const reading = { r1: { ...resume, state: "reading" as const } };
    expect(readingShared([shared], reading)).toBe(true);
    expect(readingShared([shared], { r1: resume })).toBe(false);
    // An upload that wasn't shared here doesn't hold the conversation.
    expect(readingShared([message("a", "2026-11-04T09:00:00Z")], reading)).toBe(false);
  });
});

describe("check-ins", () => {
  const plan = {
    state: "on",
    week: -1,
    weekday: 5,
    time: "16:00",
    time_zone: "America/Chicago",
  } as const;

  it("says times the way people do", () => {
    expect(timeLabel("16:00")).toBe("4 PM");
    expect(timeLabel("09:30")).toBe("9:30 AM");
    expect(timeLabel("12:00")).toBe("12 PM");
    expect(timeLabel("00:00")).toBe("12 AM");
  });

  it("offers the day's hours, and keeps a plan's own time", () => {
    const times = checkInTimes();
    expect(times[0]).toBe("07:00");
    expect(times.at(-1)).toBe("21:00");
    expect(times).toHaveLength(15);
    expect(checkInTimes("06:30")[0]).toBe("06:30");
    expect(checkInTimes("16:00")).toHaveLength(15);
  });

  it("passes on only a whole plan", () => {
    expect(cleanPlan(plan)).toEqual(plan);
    expect(cleanPlan({ ...plan, state: "off", week: 1, weekday: 1 })).not.toBeNull();
    for (const bad of [
      null,
      "monthly",
      { ...plan, state: "sometimes" },
      { ...plan, week: 5 },
      { ...plan, week: "-1" },
      { ...plan, weekday: 0 },
      { ...plan, weekday: 2.5 },
      { ...plan, time: "25:00" },
      { ...plan, time: "4 PM" },
      { ...plan, time_zone: "" },
      { ...plan, time_zone: "x".repeat(65) },
    ]) {
      expect(cleanPlan(bad)).toBeNull();
    }
    // Anything extra stays behind.
    expect(cleanPlan({ ...plan, channel: "text_message" })).toEqual(plan);
  });

  it("asks once the person has said something and Plytos has answered", () => {
    const said = message("a", "2026-11-04T10:00:00Z");
    const answered = [said, message("b", "2026-11-04T10:00:05Z", "plytos")];
    expect(offerCheckIns([], NO_CHECK_INS, false)).toBe(false);
    expect(offerCheckIns([said], NO_CHECK_INS, false)).toBe(false);
    expect(offerCheckIns(answered, NO_CHECK_INS, false)).toBe(true);
    expect(offerCheckIns(answered, NO_CHECK_INS, true)).toBe(false);
    const decided = { plan: { ...plan, state: "off" as const }, label: null, next_at: null };
    expect(offerCheckIns(answered, decided, false)).toBe(false);
  });

  it("starts with the end of the month", () => {
    expect(CHECK_IN_CHOICES.map((c) => c.label)).toEqual(["Last Friday, 4 PM", "First Monday, 9 AM"]);
  });
});
