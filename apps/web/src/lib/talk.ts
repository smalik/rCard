// The conversation with Plytos: types shared by the server and the browser,
// and the small pure helpers the thread uses. See docs/agents.md.

import type { CardContent, CardKind } from "./cards";
import type { ImportSummary } from "./imports";
import type { NewResume } from "./resumes";

export const MAX_MESSAGE = 4000;

export type AgentName =
  | "check_in"
  | "listener"
  | "stitcher"
  | "fact_checker"
  | "connector"
  | "strategist"
  | "scout"
  | "assembler"
  | "critic";

export const AGENT_LABELS: Record<AgentName, string> = {
  check_in: "Check-in",
  listener: "Listener",
  stitcher: "Stitcher",
  fact_checker: "Fact-checker",
  connector: "Connector",
  strategist: "Strategist",
  scout: "Scout",
  assembler: "Assembler",
  critic: "Critic",
};

export type ProposalState = "open" | "kept" | "edited" | "dismissed" | "superseded";

export type ProposedCard = {
  kind: CardKind;
  content: CardContent;
  // One question that would complete it, such as "Did late shipments drop?"
  missing: string | null;
};

export type Proposal = {
  id: string;
  agent: AgentName;
  kind: "new_card" | "card_version" | "variant" | "resume" | "question" | "insight";
  state: ProposalState;
  card_id: string | null;
  cites: string[];
  body: { message: string; card: ProposedCard | null; resume?: NewResume | null };
  created_at: string;
  decided_at: string | null;
  result_version_id: string | null;
  // The resume version made when the person kept a proposed resume.
  result_resume_version_id?: string | null;
};

export type Message = {
  id: string;
  author: "person" | "plytos";
  channel: "app" | "text_message" | "email";
  text: string;
  created_at: string;
  proposal: Proposal | null;
  // A resume shared in the conversation, while its import is kept.
  import_id?: string | null;
  // A resume the message is about, such as one the person asked a version of.
  resume_id?: string | null;
};

// What the thread needs to show: the messages, the resumes they share, and
// when Plytos checks in.
export type Thread = { messages: Message[]; resumes: ImportSummary[]; check_ins: CheckIns };

// -- check-ins ----------------------------------------------------------------

// The first to the fourth week of the month, or -1 for the last.
export type CheckInWeek = 1 | 2 | 3 | 4 | -1;

// Once a month, on a weekday of a given week, at a local time.
export type CheckInPlan = {
  state: "on" | "off";
  week: CheckInWeek;
  // ISO weekday: 1 is Monday, 7 is Sunday.
  weekday: number;
  // 24-hour local time, "16:00".
  time: string;
  time_zone: string;
};

// No plan means the person hasn't been asked yet.
export type CheckIns = { plan: CheckInPlan | null; label: string | null; next_at: string | null };

export const NO_CHECK_INS: CheckIns = { plan: null, label: null, next_at: null };

export type CheckInSlot = Pick<CheckInPlan, "week" | "weekday" | "time">;

// What Plytos suggests first: the end of the month, at the end of the week.
export const USUAL_CHECK_IN: CheckInSlot = { week: -1, weekday: 5, time: "16:00" };

// The two answers most people give, offered as one tap each.
export const CHECK_IN_CHOICES: { label: string; slot: CheckInSlot }[] = [
  { label: "Last Friday, 4 PM", slot: USUAL_CHECK_IN },
  { label: "First Monday, 9 AM", slot: { week: 1, weekday: 1, time: "09:00" } },
];

export const WEEKS: { week: CheckInWeek; label: string }[] = [
  { week: 1, label: "First" },
  { week: 2, label: "Second" },
  { week: 3, label: "Third" },
  { week: 4, label: "Fourth" },
  { week: -1, label: "Last" },
];

export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

const TIME = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;

// "16:00" as "4 PM", "09:30" as "9:30 AM".
export function timeLabel(value: string): string {
  const [hour = 0, minute = 0] = value.split(":").map(Number);
  const shown = hour % 12 || 12;
  const half = hour < 12 ? "AM" : "PM";
  return minute === 0 ? `${shown} ${half}` : `${shown}:${String(minute).padStart(2, "0")} ${half}`;
}

// On the hour, from 7 AM to 9 PM, plus the plan's own time if it's another.
export function checkInTimes(current?: string): string[] {
  const times = Array.from({ length: 15 }, (_, i) => `${String(i + 7).padStart(2, "0")}:00`);
  if (current && TIME.test(current) && !times.includes(current)) {
    times.push(current);
    times.sort();
  }
  return times;
}

// A plan the browser sent, checked before it goes to the API; null if it's
// not one.
export function cleanPlan(body: unknown): CheckInPlan | null {
  if (typeof body !== "object" || body === null) return null;
  const { state, week, weekday, time, time_zone } = body as Record<string, unknown>;
  if (state !== "on" && state !== "off") return null;
  if (!WEEKS.some((w) => w.week === week)) return null;
  if (typeof weekday !== "number" || !Number.isInteger(weekday) || weekday < 1 || weekday > 7) {
    return null;
  }
  if (typeof time !== "string" || !TIME.test(time)) return null;
  if (typeof time_zone !== "string" || !time_zone || time_zone.length > 64) return null;
  return { state, week: week as CheckInWeek, weekday, time, time_zone };
}

// Offers check-ins at the end of the thread once the person has said
// something and Plytos has answered, until they choose.
export function offerCheckIns(thread: Message[], checkIns: CheckIns, waiting: boolean): boolean {
  if (checkIns.plan !== null || waiting) return false;
  return thread.some((m) => m.author === "person") && thread.at(-1)?.author === "plytos";
}

// "Fri, Nov 27", for when the next check-in is due.
export function nextCheckInLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

// The text to send, or null when there's nothing to send.
export function cleanMessage(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed || trimmed.length > MAX_MESSAGE) return null;
  return trimmed;
}

// Adds newer messages to the thread. A message already there is replaced,
// because the proposal it carries may have been decided since.
export function merge(thread: Message[], incoming: Message[]): Message[] {
  const byId = new Map(thread.map((m) => [m.id, m]));
  for (const m of incoming) byId.set(m.id, m);
  return [...byId.values()].sort(
    (a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
  );
}

// Plytos usually answers within a few seconds. Until it does, the thread
// shows it's thinking and checks back often.
export function awaitingReply(thread: Message[], now: Date, withinSeconds = 45): boolean {
  const last = thread.at(-1);
  if (!last || last.author !== "person") return false;
  return now.getTime() - new Date(last.created_at).getTime() < withinSeconds * 1000;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

// "Today", "Yesterday", a weekday within the week, then a date.
export function dayLabel(iso: string, now: Date): string {
  const date = new Date(iso);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString("en-US", { weekday: "long" });
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
}

export function groupByDay(
  thread: Message[],
  now: Date,
): { label: string; messages: Message[] }[] {
  const groups: { label: string; messages: Message[] }[] = [];
  for (const message of thread) {
    const label = dayLabel(message.created_at, now);
    const last = groups.at(-1);
    if (last && last.label === label) last.messages.push(message);
    else groups.push({ label, messages: [message] });
  }
  return groups;
}

// The card as the person edited it before keeping it. Facts stay as the notes
// gave them; only the wording changes.
export function withWording(card: ProposedCard, headline: string, body: string): CardContent {
  return {
    ...card.content,
    framing: { ...card.content.framing, headline: headline.trim(), body: body.trim() },
  };
}

// "from 3 of your notes", for the line that says how Plytos got here.
export function fromNotes(proposal: Proposal): string {
  const n = proposal.cites.length;
  if (n === 0) return "";
  return n === 1 ? "from one of your notes" : `from ${n} of your notes`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-09" as "Sep 2026". Anything else is shown as written.
export function monthLabel(value: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  if (!match) return value;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${month} ${match[1]}` : value;
}

// Where "Go through them" leads: open questions first, then the cards.
export function resumeNext(resume: ImportSummary): { href: string; label: string } {
  const id = encodeURIComponent(resume.id);
  if (resume.to_settle > 0) return { href: `/import/${id}/settle`, label: "Answer the questions" };
  const left = resume.cards - resume.approved - resume.dropped;
  if (left > 0) return { href: `/import/${id}/approve`, label: "Go through them" };
  return { href: `/import/${id}`, label: "See what I read" };
}

// "26 cards · 4 kept", for the resume card in the thread.
export function resumeProgress(resume: ImportSummary): string {
  const parts = [`${resume.cards} ${resume.cards === 1 ? "card" : "cards"}`];
  if (resume.approved > 0) parts.push(`${resume.approved} kept`);
  if (resume.to_settle > 0) {
    parts.push(`${resume.to_settle} ${resume.to_settle === 1 ? "question" : "questions"}`);
  }
  return parts.join(" · ");
}
