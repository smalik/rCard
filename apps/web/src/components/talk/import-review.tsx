"use client";

// Going through a resume in the conversation. Plytos asks what it isn't sure
// of, one question at a time, then shows each job as it read it. The person
// takes out what they don't want, rewords what they like, and keeps the rest
// in one tap. Nothing becomes a card until they keep it. Every answer is
// recorded on the import, so after a reload it picks up where they left off;
// once nothing is left to decide, the resume's card in the thread takes over.

import { Check, ChevronDown, Pencil } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { KindTile, type Purpose } from "@/components/cards/strength-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { BODY_MAX, type CardKind, HEADLINE_MAX } from "@/lib/cards";
import {
  type CardMatch,
  contentFor,
  dateSpan,
  highlight,
  type MatchChoice,
  parentRef,
  plural,
  type Progress,
  type Proposal,
  type ReadingStatus,
  type Review,
} from "@/lib/imports";
import {
  answered,
  answerText,
  currentStep,
  type Dates,
  datesOf,
  datesProblem,
  deferred,
  type GroupChoices,
  groupIntro,
  groupMatches,
  isFrame,
  isLong,
  keepRequest,
  keptAlready,
  type KeepRequest,
  laterRequest,
  lineNotes,
  lineText,
  type Reply as ReplyChoice,
  type ReviewGroup,
  quoteLabel,
  reviewSteps,
  SECTION_NAMES,
  setAside,
  settleQuestion,
  settleReplies,
  type Step,
  stepKey,
  stepRecap,
  tally,
  undecided,
} from "@/lib/review";
import { cn } from "@/lib/utils";

import { PersonSays, PlytosSays, Quote, Replies, Reply, Thinking } from "./bubbles";
import { useMakeResume } from "./make-resume";
import { send } from "./send";

type Decided = { progress: Progress; matches?: Record<string, CardMatch> };

// What the thread's resume card shows, worked out from the review as it stands.
export type ReviewCounts = { approved: number; later: number; dropped: number; to_settle: number };

function counts(review: Review): ReviewCounts {
  const { kept, later, out } = tally(review);
  const open = review.toSettle.filter((i) => {
    const settled = review.progress.settled[String(i)];
    return !settled || settled.answer === "later";
  }).length;
  return { approved: kept, later, dropped: out, to_settle: open };
}

// How many earlier answers stay in view; the rest fold away.
const RECENT = 2;

export function ImportReview({
  importId,
  goBack,
  resumeId,
  onCounts,
  onAdvance,
}: {
  importId: string;
  // Go back to what was set aside, not only what's undecided.
  goBack: boolean;
  // The resume already made from this file, if one was.
  resumeId: string | null;
  onCounts: (id: string, counts: ReviewCounts) => void;
  onAdvance: () => void;
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [revisit, setRevisit] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let stopped = false;
    void send<ReadingStatus>(`/import/${encodeURIComponent(importId)}/status`).then((result) => {
      if (stopped) return;
      if (result.ok && result.data.review) {
        setReview(result.data.review);
        setFailed(false);
        if (goBack) setRevisit(setAside(result.data.review));
      } else {
        setFailed(true);
      }
    });
    return () => {
      stopped = true;
    };
  }, [importId, goBack, attempt]);

  const steps = useMemo(() => (review ? reviewSteps(review) : []), [review]);

  // The thread scrolled before the review arrived, so it scrolls again now.
  const loaded = review !== null;
  useEffect(() => {
    if (loaded) onAdvance();
  }, [loaded, onAdvance]);

  if (failed) {
    return (
      <PlytosSays
        attached={
          <Replies>
            <Reply onClick={() => setAttempt((n) => n + 1)}>Try again</Reply>
          </Replies>
        }
      >
        I couldn&apos;t open that resume just now.
      </PlytosSays>
    );
  }
  if (!review) return <Thinking />;
  if (review.cards.length === 0) return null;

  const current = currentStep(review, revisit);
  const history = steps.filter((s) => s !== current && answered(s, review, revisit));
  const hidden = showAll ? 0 : Math.max(0, history.length - RECENT);

  function apply(next: Review) {
    setReview(next);
    onCounts(importId, counts(next));
    onAdvance();
  }

  async function act(said: string, url: string, body: unknown, after?: (r: Review) => void) {
    if (!review) return;
    setBusy(said);
    setError(null);
    const result = await send<Decided | Progress>(url, body);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const data = result.data;
    const next =
      "progress" in data
        ? { ...review, progress: data.progress, matches: data.matches ?? review.matches }
        : { ...review, progress: data };
    after?.(next);
    apply(next);
  }

  const base = `/import/${encodeURIComponent(importId)}`;
  const questionsLeft = steps.filter(
    (s) => s.kind !== "group" && !answered(s, review, revisit),
  ).length;
  const firstGroup = !history.some((s) => s.kind === "group");

  return (
    <section aria-label={`Going through ${review.file.name}`} className="flex flex-col gap-3">
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mx-auto flex items-center gap-1 rounded-full px-3 py-1 text-[13px] font-medium text-muted-foreground hover:bg-secondary"
        >
          <ChevronDown className="size-3.5" />
          {plural(hidden, "earlier answer")}
        </button>
      )}
      {history.slice(hidden).map((step) => (
        <Exchange key={stepKey(step)} step={step} review={review} />
      ))}

      {current?.kind === "place" && (
        <PlaceQuestion
          card={current.card}
          review={review}
          lead={history.length === 0 ? questionsLeft : 0}
          busy={busy !== null}
          onPlace={(parent, label) =>
            void act(label, `${base}/cards/${current.card.ref}`, { action: "place", parent_ref: parent })
          }
          onLeaveOut={() =>
            void act("Leave it out", `${base}/cards/${current.card.ref}`, { action: "dropped" })
          }
        />
      )}
      {current?.kind === "settle" && (
        <SettleQuestion
          step={current}
          review={review}
          lead={history.length === 0 ? questionsLeft : 0}
          busy={busy !== null}
          onAnswer={(reply) =>
            void act(
              reply.label,
              `${base}/answer`,
              { finding: current.index, answer: reply.answer, value: reply.value },
              // Answered again, even "not sure yet": it moves on.
              () => setRevisit((keys) => new Set([...keys].filter((k) => k !== stepKey(current)))),
            )
          }
        />
      )}
      {current?.kind === "group" && (
        <GroupStep
          key={current.group.key}
          group={current.group}
          review={review}
          first={firstGroup}
          busy={busy !== null}
          onDecide={(said, request) =>
            void act(said, `${base}/keep`, request, () => {
              if (request.later.length > 0) {
                setRevisit((keys) => new Set([...keys].filter((k) => k !== current.group.key)));
              }
            })
          }
        />
      )}
      {busy !== null && <PersonSays pending>{busy}</PersonSays>}
      {error && (
        <p role="alert" className="pl-9 text-[13px] text-destructive">
          {error}
        </p>
      )}
      {current === null && busy === null && (
        <Done
          review={review}
          resumeId={resumeId}
          onGoBack={() => {
            setRevisit(setAside(review));
            onAdvance();
          }}
        />
      )}
    </section>
  );
}

/** An answered step: what Plytos asked, briefly, and what the person said. */
function Exchange({ step, review }: { step: Step; review: Review }) {
  const said = answerText(step, review);
  return (
    <>
      <PlytosSays>
        <span className="text-[14px] text-muted-foreground">{stepRecap(step, review)}</span>
      </PlytosSays>
      {said && <PersonSays>{said}</PersonSays>}
    </>
  );
}

function Lead({ left }: { left: number }) {
  if (left === 0) return null;
  return (
    <>
      {left === 1 ? "Before the jobs, one thing to check. " : `Before the jobs, ${left} things to check. `}
    </>
  );
}

function PlaceQuestion({
  card,
  review,
  lead,
  busy,
  onPlace,
  onLeaveOut,
}: {
  card: Proposal;
  review: Review;
  lead: number;
  busy: boolean;
  onPlace: (parent: string | null, label: string) => void;
  onLeaveOut: () => void;
}) {
  const placement = card.placement!;
  return (
    <PlytosSays
      label="Where this line belongs"
      attached={
        <>
          <Quote where="From your resume">
            {contentFor(card, review.progress).framing.headline}
          </Quote>
          <Replies label={placement.question}>
            {placement.choices.map((choice) => (
              <Reply
                key={choice.parent_ref ?? "top"}
                disabled={busy}
                onClick={() => onPlace(choice.parent_ref, choice.label)}
              >
                {choice.label}
              </Reply>
            ))}
            <Reply quiet disabled={busy} onClick={onLeaveOut}>
              Leave it out
            </Reply>
          </Replies>
        </>
      }
    >
      <p>
        <Lead left={lead} />
        <span className="font-medium">{placement.question}</span>
      </p>
      <p className="mt-1 text-[14px] text-muted-foreground">{placement.reason}</p>
    </PlytosSays>
  );
}

function SettleQuestion({
  step,
  review,
  lead,
  busy,
  onAnswer,
}: {
  step: Extract<Step, { kind: "settle" }>;
  review: Review;
  lead: number;
  busy: boolean;
  onAnswer: (reply: ReplyChoice) => void;
}) {
  const { finding } = step;
  const quotes = finding.locations.filter((loc) => loc.excerpt).slice(0, 3);
  return (
    <PlytosSays
      label={finding.title}
      attached={
        <>
          {quotes.map((loc, i) => {
            const [before, hit, after] = loc.figure
              ? highlight(loc.excerpt, loc.figure)
              : [loc.excerpt, "", ""];
            return (
              <Quote key={i} where={quoteLabel(review, loc.block)}>
                {before}
                {hit && <mark className="rounded bg-live-soft px-0.5 font-semibold text-foreground">{hit}</mark>}
                {after}
              </Quote>
            );
          })}
          <Replies label={settleQuestion(finding)}>
            {settleReplies(finding).map((reply) => (
              <Reply
                key={`${reply.answer}-${reply.value ?? ""}`}
                quiet={reply.answer === "later"}
                disabled={busy}
                onClick={() => onAnswer(reply)}
              >
                {reply.label}
              </Reply>
            ))}
          </Replies>
        </>
      }
    >
      <p>
        <Lead left={lead} />
        <span className="font-medium">{settleQuestion(finding)}</span>
      </p>
      <p className="mt-1 text-[14px] text-muted-foreground">{finding.detail}</p>
      {keptAlready(step, review) && (
        <p className="mt-1 text-[14px] text-muted-foreground">
          You&apos;ve already kept the cards this is about, so your answer won&apos;t change them.
          You can fix a card from Cards.
        </p>
      )}
    </PlytosSays>
  );
}

// -- a job, as the person goes through it ------------------------------------

const PURPOSE: Partial<Record<CardKind, Purpose>> = {
  employment: "experience",
  position: "experience",
  engagement: "experience",
  role: "experience",
  education: "education",
  credential: "credential",
  skill: "skill",
  project: "project",
  activity: "activity",
};


function purposeOf(card: Proposal): Purpose {
  if (card.kind === "accomplishment" && card.content.facts.award !== undefined) return "award";
  return PURPOSE[card.kind] ?? "highlight";
}

function GroupStep({
  group,
  review,
  first,
  busy,
  onDecide,
}: {
  group: ReviewGroup;
  review: Review;
  first: boolean;
  busy: boolean;
  onDecide: (said: string, request: KeepRequest) => void;
}) {
  const [out, setOut] = useState<ReadonlySet<string>>(new Set());
  const [wording, setWording] = useState<Record<string, string>>({});
  const [choice, setChoice] = useState<Record<string, MatchChoice>>({});
  const [dates, setDates] = useState<Record<string, Dates>>({});
  const choices: GroupChoices = { out, wording, choice, dates };
  const left = undecided(group, review);
  const mine = groupMatches(group, review);
  const all = group.root !== null && out.has(group.root.ref);
  const lines = left.filter((c) => !isFrame(c.kind));
  const keptLines = all ? 0 : lines.filter((c) => !out.has(c.ref)).length;
  const everythingOut = all || left.every((c) => out.has(c.ref));

  function toggle(ref: string) {
    setOut((now) => {
      const next = new Set(now);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });
  }

  function keep() {
    const request = keepRequest(group, review, choices);
    const said = everythingOut
      ? "Leave it out"
      : group.kind === "job"
        ? keptLines === lines.length
          ? "Keep it"
          : `Keep it, with ${plural(keptLines, "line")}`
        : `Keep ${request.keep.length}`;
    onDecide(said, request);
  }

  const intro = groupIntro(group, review, first);
  const already =
    mine.mine === 0
      ? ""
      : mine.changes === 0
        ? ` ${mine.mine === 1 ? "One of these is" : `${mine.mine} of these are`} already in your cards, as they are.`
        : ` ${mine.mine === 1 ? "One of these is" : `${mine.mine} of these are`} already in your cards; keeping adds what's new as ${mine.mine === 1 ? "its next version" : "their next versions"}.`;

  return (
    <PlytosSays
      label={group.root ? contentFor(group.root, review.progress).framing.headline : "The rest"}
      attached={
        <article
          aria-label="Draft cards"
          className="w-full max-w-full overflow-hidden rounded-card border bg-card shadow-card sm:max-w-[92%]"
        >
          {group.kind === "job" ? (
            <JobDraft
              group={group}
              review={review}
              choices={choices}
              onToggle={toggle}
              onWord={(ref, words) => setWording((w) => ({ ...w, [ref]: words }))}
              onChoose={(ref, c) => setChoice((now) => ({ ...now, [ref]: c }))}
              onDates={(ref, d) => setDates((now) => ({ ...now, [ref]: d }))}
            />
          ) : (
            <RestDraft
              cards={left}
              review={review}
              choices={choices}
              onToggle={toggle}
              onWord={(ref, words) => setWording((w) => ({ ...w, [ref]: words }))}
              onChoose={(ref, c) => setChoice((now) => ({ ...now, [ref]: c }))}
              onDates={(ref, d) => setDates((now) => ({ ...now, [ref]: d }))}
            />
          )}
          <footer className="flex flex-wrap items-center gap-2 border-t bg-muted/40 px-4 py-3">
            <Button disabled={busy} onClick={keep} variant={everythingOut ? "outline" : "default"}>
              {everythingOut
                ? "Leave it out"
                : group.kind === "job"
                  ? "Keep this job"
                  : `Keep ${left.filter((c) => !out.has(c.ref)).length}`}
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => onDecide("Not now", laterRequest(group, review))}
            >
              Not now
            </Button>
            {!everythingOut && out.size > 0 && (
              <span className="text-[13px] text-muted-foreground">
                {plural(all ? left.length : out.size, "line")} left out
              </span>
            )}
          </footer>
        </article>
      }
    >
      {intro}
      {already}
      {first && (
        <span className="text-muted-foreground">
          {" "}
          Untick anything you don&apos;t want, reword what you like, and keep the rest. Nothing
          becomes a card until you do.
        </span>
      )}
    </PlytosSays>
  );
}

type DraftProps = {
  review: Review;
  choices: GroupChoices;
  onToggle: (ref: string) => void;
  onWord: (ref: string, words: string) => void;
  onChoose: (ref: string, choice: MatchChoice) => void;
  onDates: (ref: string, dates: Dates) => void;
};

function depthIn(group: ReviewGroup, review: Review): Map<string, number> {
  const depth = new Map<string, number>();
  for (const card of group.cards) {
    const above = parentRef(card, review.progress);
    depth.set(card.ref, above && depth.has(above) ? depth.get(above)! + 1 : 0);
  }
  return depth;
}

function JobDraft({ group, ...props }: DraftProps & { group: ReviewGroup }) {
  const { review, choices } = props;
  const root = group.root!;
  const content = contentFor(root, review.progress);
  const left = new Set(undecided(group, review).map((c) => c.ref));
  const depth = depthIn(group, review);
  const all = choices.out.has(root.ref);
  const location = typeof content.facts.location === "string" ? content.facts.location : "";
  return (
    <div className="flex flex-col px-4 pt-4 pb-2">
      <header className="flex items-start gap-3 pb-2">
        <KindTile purpose="experience" className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3 className={cn("text-[17px] leading-snug font-semibold tracking-[-0.01em]", all && "text-muted-foreground line-through")}>
            {content.framing.headline}
          </h3>
          <FrameDates card={root} place={location} editable={left.has(root.ref) && !all} {...props} />
          <MatchNote card={root} {...props} />
        </div>
        {left.has(root.ref) && (
          <Tick
            kept={!all}
            label={all ? `Keep ${content.framing.headline}` : `Leave out the whole job at ${content.framing.headline}`}
            onClick={() => props.onToggle(root.ref)}
          />
        )}
      </header>
      <ul className="flex flex-col">
        {group.cards
          .filter((c) => c !== root)
          .map((card) => {
            const indent = Math.max(0, (depth.get(card.ref) ?? 1) - 1);
            if (isFrame(card.kind)) {
              return (
                <TitleRow
                  key={card.ref}
                  card={card}
                  indent={indent}
                  decided={!left.has(card.ref)}
                  dimmed={all}
                  {...props}
                />
              );
            }
            return (
              <LineRow
                key={card.ref}
                card={card}
                indent={indent}
                decided={!left.has(card.ref)}
                dimmed={all}
                {...props}
              />
            );
          })}
      </ul>
    </div>
  );
}

function RestDraft({ cards, ...props }: DraftProps & { cards: Proposal[] }) {
  const sections: { label: string; purpose: Purpose; cards: Proposal[] }[] = [];
  for (const card of cards) {
    const label = SECTION_NAMES[card.kind] ?? "Other";
    const last = sections.at(-1);
    if (last && last.label === label) last.cards.push(card);
    else sections.push({ label, purpose: purposeOf(card), cards: [card] });
  }
  return (
    <div className="flex flex-col gap-3 px-4 pt-4 pb-2">
      {sections.map((section) => (
        <section key={section.label} aria-label={section.label}>
          <h3 className="flex items-center gap-2 pb-1 text-[13px] font-semibold tracking-[0.02em] text-muted-foreground">
            <KindTile purpose={section.purpose} className="size-6 rounded-[7px] [&_svg]:size-3.5" />
            {section.label}
          </h3>
          <ul className="flex flex-col">
            {section.cards.map((card) => (
              <LineRow key={card.ref} card={card} indent={0} decided={false} dimmed={false} {...props} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Tick({ kept, label, onClick }: { kept: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={kept}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "relative mt-0.5 grid size-[22px] shrink-0 place-items-center rounded-full border-2 transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40",
        "after:absolute after:-inset-2.5 after:content-['']",
        kept ? "border-primary bg-primary text-primary-foreground" : "border-input bg-transparent text-transparent",
      )}
    >
      <Check className="size-3.5" strokeWidth={3} />
    </button>
  );
}

function TitleRow({
  card,
  indent,
  decided,
  dimmed,
  ...props
}: DraftProps & { card: Proposal; indent: number; decided: boolean; dimmed: boolean }) {
  const content = contentFor(card, props.review.progress);
  const gone = dimmed || props.choices.out.has(card.ref);
  return (
    <li className="pt-3 pb-1" style={{ paddingLeft: `${indent * 16 + 34}px` }}>
      <p className={cn("text-[15px] font-semibold italic", gone && "text-muted-foreground line-through")}>
        {content.framing.headline}
      </p>
      <FrameDates card={card} editable={!decided && !gone} {...props} />
      <MatchNote card={card} {...props} />
    </li>
  );
}

// Shortens a line for a button's spoken name.
function short(text: string): string {
  return text.length > 60 ? `${text.slice(0, 59).trimEnd()}…` : text;
}

/** A job's or title's dates. The person can correct them before keeping it,
 * such as when they said they'd fix the dates. */
function FrameDates({
  card,
  place = "",
  editable,
  review,
  choices,
  onDates,
}: DraftProps & { card: Proposal; place?: string; editable: boolean }) {
  const content = contentFor(card, review.progress);
  const original = datesOf(content);
  const dates = choices.dates[card.ref] ?? original;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(dates);
  const [tried, setTried] = useState(false);
  const problem = datesProblem(draft);
  const facts = { ...content.facts, start: dates.start, end: dates.end };
  const when = dateSpan(facts);
  const where = [when, place].filter(Boolean).join(" · ");
  const changed = dates.start !== original.start || dates.end !== original.end;
  const notes = editable ? lineNotes(card, review) : [];
  const name = content.framing.headline;

  if (editing) {
    return (
      <div className="mt-1 flex max-w-sm flex-col gap-2">
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-[12px] font-medium text-muted-foreground">
            From
            <Input
              autoFocus
              value={draft.start}
              placeholder="2014-03"
              autoComplete="off"
              onChange={(e) => setDraft((d) => ({ ...d, start: e.target.value }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-[12px] font-medium text-muted-foreground">
            To
            <Input
              value={draft.end}
              placeholder="present"
              autoComplete="off"
              onChange={(e) => setDraft((d) => ({ ...d, end: e.target.value }))}
            />
          </label>
        </div>
        <p className="text-[12px] text-muted-foreground">
          A year and month, like 2021-03. For a job you&apos;re still in, the end is present.
        </p>
        {tried && problem && (
          <p role="alert" className="text-[12px] text-destructive">
            {problem}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => {
              setTried(true);
              if (problem) return;
              onDates(card.ref, { start: draft.start.trim(), end: draft.end.trim() });
              setEditing(false);
            }}
          >
            Done
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraft(dates);
              setTried(false);
              setEditing(false);
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    );
  }
  return (
    <>
      <p className="flex flex-wrap items-baseline gap-x-2 text-[13px] text-muted-foreground">
        {where && <span>{where}</span>}
        {editable && (
          <button
            type="button"
            aria-label={`Change the dates for ${short(name)}`}
            className="font-medium text-primary"
            onClick={() => {
              setDraft(dates);
              setEditing(true);
            }}
          >
            {when ? "Change dates" : "Add dates"}
          </button>
        )}
      </p>
      {changed && <p className="text-[12px] font-medium text-primary">Your dates</p>}
      {notes.map((note) => (
        <p key={note} className="text-[12px] leading-snug text-muted-foreground">
          <span className="font-semibold text-live">Check:</span> {note}
        </p>
      ))}
    </>
  );
}

function LineRow({
  card,
  indent,
  decided,
  dimmed,
  ...props
}: DraftProps & { card: Proposal; indent: number; decided: boolean; dimmed: boolean }) {
  const { review, choices, onToggle, onWord } = props;
  const content = contentFor(card, review.progress);
  // A long line, such as a summary, is edited in full, not its shortened headline.
  const original = lineText(content);
  const words = choices.wording[card.ref];
  const shown = words?.trim() || original;
  const kept = !dimmed && !choices.out.has(card.ref);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(shown);
  const notes = lineNotes(card, review);
  const detail = detailOf(card, review);

  if (decided) return null;
  return (
    <li className="flex items-start gap-3 py-2" style={{ paddingLeft: `${indent * 16}px` }}>
      <Tick
        kept={kept}
        label={kept ? `Leave out “${short(shown)}”` : `Keep “${short(shown)}”`}
        onClick={() => onToggle(card.ref)}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {editing ? (
          <div className="flex flex-col gap-2">
            <Textarea
              autoFocus
              aria-label="Reword this line"
              value={draft}
              maxLength={isLong(content) ? BODY_MAX : HEADLINE_MAX}
              rows={isLong(content) ? 6 : 3}
              onChange={(e) => setDraft(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!draft.trim()}
                onClick={() => {
                  onWord(card.ref, draft.trim() === original ? "" : draft);
                  setEditing(false);
                }}
              >
                Done
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft(shown);
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p
            className={cn(
              "text-[15px] leading-[1.45] break-words",
              !kept && "text-muted-foreground line-through decoration-muted-foreground/50",
            )}
          >
            {shown}
          </p>
        )}
        {detail && !editing && <p className="text-[13px] text-muted-foreground">{detail}</p>}
        {words?.trim() && !editing && (
          <p className="text-[12px] font-medium text-primary">Your wording</p>
        )}
        <MatchNote card={card} {...props} />
        {kept &&
          notes.map((note) => (
            <p key={note} className="text-[12px] leading-snug text-muted-foreground">
              <span className="font-semibold text-live">Check:</span> {note}
            </p>
          ))}
      </div>
      {!editing && kept && (
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Reword “${short(shown)}”`}
          className="-mt-1 -mr-2 text-muted-foreground"
          onClick={() => {
            setDraft(shown);
            setEditing(true);
          }}
        >
          <Pencil className="size-3.5" />
        </Button>
      )}
    </li>
  );
}

// What a line holds besides its headline, when the headline alone doesn't say:
// a skills line's skills, a certificate's issuer.
function detailOf(card: Proposal, review: Review): string | null {
  const { facts, framing } = contentFor(card, review.progress);
  if (card.kind === "skill" && Array.isArray(facts.skills)) return facts.skills.join(", ");
  if (card.kind === "credential" && typeof facts.issuer === "string") return facts.issuer;
  if (card.kind === "story") return null;
  return framing.body || null;
}

const CHOICE_LABELS: Record<MatchChoice, string> = {
  update: "Save as its next version",
  keep: "Keep mine as it is",
  separate: "Make a separate card",
};

/** For a card that's already the person's: what keeping does, and a way to
 * change it. */
function MatchNote({ card, review, choices, onChoose }: DraftProps & { card: Proposal }) {
  const match = review.matches[card.ref];
  if (!match) return null;
  const chosen = choices.choice[card.ref] ?? "update";
  const options: MatchChoice[] = match.same ? ["update", "separate"] : ["update", "keep", "separate"];
  const label =
    chosen === "separate"
      ? "New card"
      : match.same
        ? "Already in your cards"
        : chosen === "keep"
          ? "Yours stays as it is"
          : "Updates your card";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex w-fit items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[12px] font-medium text-accent-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
        >
          {label}
          <ChevronDown className="size-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel className="max-w-64 font-normal text-muted-foreground">
          It&apos;s your card “{match.headline}”.
        </DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem key={option} onSelect={() => onChoose(card.ref, option)}>
            <Check className={cn("size-4", option !== chosen && "opacity-0")} />
            {match.same && option === "update" ? "Use my card" : CHOICE_LABELS[option]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// -- when everything has an answer -------------------------------------------

function Done({
  review,
  resumeId,
  onGoBack,
}: {
  review: Review;
  resumeId: string | null;
  onGoBack: () => void;
}) {
  const { kept, later } = tally(review);
  const asked = deferred(review).length;
  const { make, busy, error } = useMakeResume(review.id);

  const what = kept > 0 ? `You kept ${plural(kept, "card")}` : "You didn't keep anything from it this time";
  const aside = later > 0 ? `, and set ${later} aside for later` : "";
  const open =
    asked === 0 ? "" : asked === 1 ? " One question is left for later." : ` ${asked} questions are left for later.`;
  const said = `That's everything from ${review.file.name}. ${what}${aside}.${open}`;
  const goBack =
    later > 0 && asked > 0
      ? "Go back to what's set aside"
      : later > 0
        ? `Go through the ${later} set aside`
        : asked === 1
          ? "Answer the question left"
          : `Answer the ${asked} questions left`;

  return (
    <PlytosSays
      attached={
        <>
          <div className="flex flex-wrap gap-2">
            {resumeId ? (
              <Button asChild>
                <Link href={`/resumes/${encodeURIComponent(resumeId)}`}>Open my resume</Link>
              </Button>
            ) : (
              kept > 0 && (
                <Button disabled={busy} onClick={make}>
                  {busy ? "Setting it up…" : "Make my resume"}
                </Button>
              )
            )}
            {(later > 0 || asked > 0) && (
              <Button variant="outline" onClick={onGoBack}>
                {goBack}
              </Button>
            )}
            <Button variant="ghost" asChild>
              <Link href="/cards">See my cards</Link>
            </Button>
          </div>
          {error && (
            <p role="alert" className="text-[13px] text-destructive">
              {error}
            </p>
          )}
        </>
      }
    >
      {said}
      {!resumeId && kept > 0 && (
        <span>
          {" "}
          Want your resume as you wrote it, made from them? You can reword it for a role after.
        </span>
      )}
    </PlytosSays>
  );
}
