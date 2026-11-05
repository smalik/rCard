"use client";

// The resume rebuilt from its cards, on paper, under the file's own headings.
// Tapping a line finds where it came from and shows what can be done with it:
// reword it, fix its dates, move it to another job, or leave it out. On a
// laptop or tablet a line can also be dragged onto the job or title it belongs
// under. Each job ends in one "Looks right" mark; the ones Plytos is sure of
// come marked already.

import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { ArrowRightLeft, Check, ChevronDown, CornerDownRight, Layers, Pencil, Undo2, X } from "lucide-react";
import { type ReactNode, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { contentFor, type MatchChoice, parentRef, type Proposal, type Review } from "@/lib/imports";
import {
  canMoveUnder,
  groupQuestions,
  isSettled,
  moveTargets,
  type Question,
  type RebuiltGroup,
  type RebuiltRow,
  type RebuiltSection,
} from "@/lib/rebuilt";
import { type Dates, datesOf, datesProblem, isFrame } from "@/lib/review";
import { cn } from "@/lib/utils";

export function rowId(ref: string): string {
  return `rebuilt-${ref}`;
}

export type RowActions = {
  busy: boolean;
  reword: (ref: string, text: string) => void;
  redate: (ref: string, dates: Dates) => void;
  move: (ref: string, to: string) => void;
  leaveOut: (ref: string) => void;
  bringBack: (ref: string) => void;
};

type Props = {
  sections: RebuiltSection[];
  review: Review;
  asked: Question[];
  // Lines lit up: the one picked, or the partners of a line picked in the file.
  lit: ReadonlySet<string>;
  // The line picked here, whose actions show under it.
  picked: string | null;
  marked: (group: RebuiltGroup) => boolean;
  onMark: (group: RebuiltGroup, marked: boolean) => void;
  onPick: (ref: string) => void;
  onPickHeading: (block: number) => void;
  onAnswer: (question: Question, choice: number) => void;
  // For a line that's already one of the person's cards: what keeping does.
  matchChoice: (ref: string) => MatchChoice;
  onChooseMatch: (ref: string, choice: MatchChoice) => void;
  actions: RowActions;
  // Shown under the picked line on a phone: where it came from in the file.
  peek?: (ref: string) => ReactNode;
};

// -- small pieces on the paper --------------------------------------------------

function PaperButton({
  children,
  className,
  ...props
}: React.ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-inset px-2 text-[12.5px] font-medium text-paper-soft transition-colors hover:bg-black/[0.06] hover:text-paper-ink focus-visible:outline-2 focus-visible:outline-paper-accent disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-3.5",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function Mark({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <label
      className={cn(
        "inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-inset px-1.5 text-[13px] font-medium select-none",
        checked ? "text-paper-accent" : "text-paper-ink",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={label}
      />
      <span
        aria-hidden
        className={cn(
          "grid size-[18px] place-items-center rounded-[4px] border-[1.5px] transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-paper-accent",
          checked ? "border-paper-accent bg-paper-accent text-white" : "border-paper-ink/40 bg-paper",
        )}
      >
        {checked && <Check className="size-3" strokeWidth={3} />}
      </span>
      Looks right
    </label>
  );
}

// -- a line that's already one of the person's cards -----------------------------

const MATCH_OPTIONS: Record<MatchChoice, string> = {
  update: "Save as its next version",
  keep: "Keep mine as it is",
  separate: "Make a separate card",
};

// What keeping a line does to the card of theirs it stands for, when it says
// something that card doesn't, and a way to change that. Earlier wording always
// stays in the card's history.
function MatchLine({
  match,
  chosen,
  busy,
  onChoose,
}: {
  match: { headline: string };
  chosen: MatchChoice;
  busy: boolean;
  onChoose: (choice: MatchChoice) => void;
}) {
  const options: MatchChoice[] = ["update", "keep", "separate"];
  const said =
    chosen === "separate" ? "Becomes a new card" : chosen === "keep" ? "Your card stays as it is" : "Updates your card";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <PaperButton disabled={busy} className="ml-3 h-7 px-1.5 text-[12px]">
          <Layers /> {said} <ChevronDown />
        </PaperButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-w-[min(22rem,90vw)]">
        <DropdownMenuLabel className="font-normal text-muted-foreground">
          It&apos;s your card “{match.headline}”. Earlier wording stays in its history.
        </DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem key={option} onSelect={() => onChoose(option)}>
            <Check className={cn("size-4", option !== chosen && "opacity-0")} />
            {MATCH_OPTIONS[option]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// -- a question, with Plytos's pick ----------------------------------------------

function QuestionCard({
  question,
  busy,
  onAnswer,
}: {
  question: Question;
  busy: boolean;
  onAnswer: (choice: number) => void;
}) {
  const [reopened, setReopened] = useState(false);
  const answered = question.answered;
  if (answered !== null && !reopened) {
    return (
      <div className="my-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-inset bg-black/[0.035] px-2.5 py-1.5 text-[12.5px] text-paper-soft">
        <Check className="size-3.5 text-paper-accent" strokeWidth={2.5} />
        <span className="min-w-0 flex-1">
          {question.prompt} <b className="font-semibold text-paper-ink">{question.choices[answered]?.label}</b>
        </span>
        <button
          type="button"
          className="font-medium text-paper-accent underline-offset-2 hover:underline"
          onClick={() => setReopened(true)}
        >
          Change
        </button>
      </div>
    );
  }
  return (
    <div
      role="group"
      aria-label={question.prompt}
      className="my-2 rounded-inset border border-live/40 bg-live-soft px-3 py-2.5"
    >
      <p className="text-[13px] font-semibold text-paper-ink">{question.prompt}</p>
      {question.why && <p className="mt-0.5 text-[12.5px] text-paper-soft">{question.why}</p>}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {question.choices.map((choice, i) => {
          const chosen = answered === i;
          const ours = answered === null && question.picked === i;
          return (
            <button
              key={choice.label}
              type="button"
              disabled={busy}
              onClick={() => {
                setReopened(false);
                onAnswer(i);
              }}
              className={cn(
                "inline-flex min-h-9 items-center gap-1.5 rounded-inset border bg-paper px-2.5 py-1 text-left text-[13px] font-medium text-paper-ink transition-colors hover:border-paper-accent focus-visible:outline-2 focus-visible:outline-paper-accent disabled:opacity-50",
                ours || chosen ? "border-paper-accent ring-1 ring-paper-accent" : "border-paper-rule",
              )}
            >
              {(ours || chosen) && <Check className="size-3.5 text-paper-accent" strokeWidth={2.5} />}
              {choice.label}
              {ours && <span className="font-normal text-paper-soft">(we think)</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// -- editing a line in place ----------------------------------------------------

function WordsEditor({
  text,
  onDone,
}: {
  text: string;
  onDone: (text: string | null) => void;
}) {
  const [value, setValue] = useState(text);
  const finish = (save: boolean) => onDone(save && value.trim() && value.trim() !== text ? value.trim() : null);
  return (
    <textarea
      aria-label="Reword this line"
      autoFocus
      enterKeyHint="done"
      value={value}
      rows={Math.min(6, Math.max(1, Math.ceil(value.length / 70)))}
      onChange={(e) => setValue(e.target.value.replace(/\n/g, " "))}
      onFocus={(e) => e.currentTarget.setSelectionRange(value.length, value.length)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          finish(true);
        } else if (e.key === "Escape") {
          e.preventDefault();
          finish(false);
        }
      }}
      onBlur={() => finish(true)}
      className="w-full resize-none rounded-inset border border-paper-accent bg-paper px-2 py-1 text-[13.5px] leading-[1.5] text-paper-ink outline-none focus:ring-2 focus:ring-paper-accent/30"
    />
  );
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function DateField({
  label,
  value,
  onChange,
  present,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  // The end of a job: it can be "present".
  present?: boolean;
}) {
  const now = value === "present";
  const [year = "", month = ""] = now ? [] : value.split("-");
  const set = (y: string, m: string) => onChange(y ? (m ? `${y}-${m}` : y) : "");
  return (
    <fieldset className="flex flex-wrap items-center gap-1.5">
      <legend className="sr-only">{label}</legend>
      <span className="w-10 text-[12px] font-medium text-paper-soft">{label}</span>
      <select
        aria-label={`${label} month`}
        disabled={now}
        value={month}
        onChange={(e) => set(year, e.target.value)}
        className="h-8 rounded-inset border border-paper-rule bg-paper px-1.5 text-[13px] text-paper-ink disabled:opacity-40"
      >
        <option value="">Month</option>
        {MONTH_NAMES.map((name, i) => (
          <option key={name} value={String(i + 1).padStart(2, "0")}>
            {name}
          </option>
        ))}
      </select>
      <input
        aria-label={`${label} year`}
        inputMode="numeric"
        maxLength={4}
        disabled={now}
        placeholder="Year"
        value={year}
        onChange={(e) => set(e.target.value.replace(/\D/g, "").slice(0, 4), month)}
        className="h-8 w-[4.5rem] rounded-inset border border-paper-rule bg-paper px-2 text-[13px] text-paper-ink tabular-nums disabled:opacity-40"
      />
      {present && (
        <label className="inline-flex items-center gap-1.5 text-[12.5px] text-paper-ink">
          <input
            type="checkbox"
            checked={now}
            onChange={(e) => onChange(e.target.checked ? "present" : "")}
            className="size-4 accent-[var(--paper-accent)]"
          />
          Still there
        </label>
      )}
    </fieldset>
  );
}

function DatesEditor({
  dates,
  onDone,
}: {
  dates: Dates;
  onDone: (dates: Dates | null) => void;
}) {
  const [value, setValue] = useState(dates);
  const problem = datesProblem(value);
  const changed = value.start !== dates.start || value.end !== dates.end;
  return (
    <div
      className="my-1.5 flex flex-col gap-1.5 rounded-inset border border-paper-accent/50 bg-paper px-2.5 py-2"
      onKeyDown={(e) => {
        if (e.key === "Escape") onDone(null);
        if (e.key === "Enter") {
          e.preventDefault();
          if (!problem) onDone(changed ? value : null);
        }
      }}
    >
      <DateField label="From" value={value.start} onChange={(start) => setValue({ ...value, start })} />
      <DateField label="To" present value={value.end} onChange={(end) => setValue({ ...value, end })} />
      {problem && changed && <p className="text-[12px] text-paper-removed">{problem}</p>}
      <div className="flex gap-1">
        <PaperButton
          className="bg-paper-accent text-white hover:bg-paper-accent hover:text-white"
          disabled={!!problem || !changed}
          onClick={() => onDone(value)}
        >
          <Check /> Use these dates
        </PaperButton>
        <PaperButton onClick={() => onDone(null)}>Never mind</PaperButton>
      </div>
    </div>
  );
}

// -- a line ---------------------------------------------------------------------

function RowText({ row }: { row: RebuiltRow }) {
  const struck = row.state === "dropped";
  const text = <span className={cn(struck && "text-paper-soft line-through")}>{row.text}</span>;
  if (row.kind === "employment") {
    return (
      <span className="flex flex-col gap-x-4 sm:flex-row sm:items-baseline sm:justify-between">
        <span className="min-w-0">
          <b className="font-semibold">{text}</b>
          {row.place && <span className="text-paper-ink/80">, {row.place}</span>}
        </span>
        {row.dates && <span className="shrink-0 text-[12.5px] text-paper-soft tabular-nums">{row.dates}</span>}
      </span>
    );
  }
  if (isFrame(row.kind)) {
    return (
      <span className="flex flex-col gap-x-4 sm:flex-row sm:items-baseline sm:justify-between">
        <span className="min-w-0 font-medium text-paper-ink/90 italic">{text}</span>
        {row.dates && <span className="shrink-0 text-[12.5px] text-paper-soft tabular-nums">{row.dates}</span>}
      </span>
    );
  }
  return (
    <span className="flex items-baseline justify-between gap-4">
      <span className="min-w-0">{text}</span>
      {row.dates && <span className="shrink-0 text-[12.5px] text-paper-soft tabular-nums">{row.dates}</span>}
    </span>
  );
}

function Row({
  row,
  card,
  review,
  lit,
  picked,
  dragging,
  canDrop,
  onPick,
  onPickLabel,
  match,
  actions,
  peek,
  before,
}: {
  row: RebuiltRow;
  card: Proposal;
  review: Review;
  lit: boolean;
  picked: boolean;
  dragging: Proposal | null;
  canDrop: boolean;
  onPick: () => void;
  onPickLabel: (block: number) => void;
  // What keeping this line does to the card of the person's it stands for.
  match?: ReactNode;
  actions: RowActions;
  peek?: ReactNode;
  // Questions asked at this line, shown above it.
  before?: ReactNode;
}) {
  const [editing, setEditing] = useState<"words" | "dates" | null>(null);
  const kept = row.state === "approved";
  const dropped = row.state === "dropped";
  const movable = !kept && !dropped && card.kind !== "employment" && moveTargets(card, review).length > 0;
  const {
    attributes,
    listeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({ id: row.ref, disabled: !movable || editing !== null });
  const { setNodeRef: setDropRef, isOver } = useDroppable({ id: row.ref, disabled: !canDrop });
  const bullet = row.kind === "accomplishment" || row.kind === "activity" || row.kind === "project";
  const targets = picked && movable ? moveTargets(card, review) : [];

  return (
    <li
      ref={setDropRef}
      className={cn(
        "relative",
        row.depth === 1 && isFrame(row.kind) && "mt-2",
        row.depth >= 1 && !isFrame(row.kind) && "pl-1",
        dragging && canDrop && "rounded-inset outline-1 outline-paper-accent/40 outline-dashed",
        isOver && canDrop && "bg-paper-accent/[0.1]",
      )}
    >
      {before}
      {row.label && (
        <button
          type="button"
          disabled={row.label.block === null}
          onClick={() => row.label?.block != null && onPickLabel(row.label.block)}
          className="mt-1 -mx-0.5 rounded-inset px-1.5 text-[11.5px] font-semibold tracking-[0.04em] text-paper-soft enabled:hover:bg-paper-accent/[0.07]"
        >
          {row.label.name}
        </button>
      )}
      {editing === "words" ? (
        <WordsEditor
          text={row.text}
          onDone={(text) => {
            setEditing(null);
            if (text) actions.reword(row.ref, text);
          }}
        />
      ) : (
        <button
          {...(movable ? attributes : {})}
          {...(movable ? listeners : {})}
          ref={setDragRef}
          id={rowId(row.ref)}
          type="button"
          role={undefined}
          aria-pressed={lit}
          onClick={onPick}
          className={cn(
            "flex w-full scroll-my-24 items-start gap-2.5 rounded-inset px-1.5 py-[3px] text-left transition-colors hover:bg-paper-accent/[0.07] focus-visible:outline-2 focus-visible:outline-paper-accent",
            lit && "bg-paper-accent/[0.14] outline-2 outline-paper-accent/70 hover:bg-paper-accent/[0.14]",
            isDragging && "opacity-40",
            movable && "pointer-fine:cursor-grab",
          )}
        >
          {bullet && <span aria-hidden className="mt-[0.62em] size-[4.5px] shrink-0 rounded-full bg-paper-ink/55" />}
          <span className="min-w-0 flex-1">
            <RowText row={row} />
          </span>
        </button>
      )}
      {!kept && !dropped && editing === null && match}
      {editing === "dates" && (
        <DatesEditor
          dates={datesOf(contentFor(card, review.progress))}
          onDone={(dates) => {
            setEditing(null);
            if (dates) actions.redate(row.ref, dates);
          }}
        />
      )}
      {picked && peek}
      {picked && editing === null && !kept && (
        <div className="flex flex-wrap items-center gap-0.5 py-1 pl-1">
          {dropped ? (
            <PaperButton disabled={actions.busy} onClick={() => actions.bringBack(row.ref)}>
              <Undo2 /> Bring it back
            </PaperButton>
          ) : (
            <>
              <PaperButton disabled={actions.busy} onClick={() => setEditing("words")}>
                <Pencil /> Reword
              </PaperButton>
              {isFrame(row.kind) && (
                <PaperButton disabled={actions.busy} onClick={() => setEditing("dates")}>
                  <CornerDownRight /> Fix the dates
                </PaperButton>
              )}
              {targets.length > 0 && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <PaperButton disabled={actions.busy}>
                      <ArrowRightLeft /> Move to…
                    </PaperButton>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="max-w-[min(22rem,90vw)]">
                    <DropdownMenuLabel>It belongs under</DropdownMenuLabel>
                    {targets.map((t) => (
                      <DropdownMenuItem key={t.ref} onSelect={() => actions.move(row.ref, t.ref)}>
                        {t.label}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              <PaperButton disabled={actions.busy} onClick={() => actions.leaveOut(row.ref)}>
                <X /> Leave out
              </PaperButton>
            </>
          )}
        </div>
      )}
    </li>
  );
}

// -- a job, or a section's lines ------------------------------------------------

function Group({
  group,
  review,
  asked,
  props,
  dragging,
}: {
  group: RebuiltGroup;
  review: Review;
  asked: Question[];
  props: Props;
  dragging: Proposal | null;
}) {
  const settled = isSettled(group, review);
  const marked = props.marked(group);
  const open = groupQuestions(group, asked).filter((q) => q.answered === null);
  const byRef = new Map(review.cards.map((c) => [c.ref, c]));
  const askedAt = new Map<string, Question[]>();
  for (const q of asked) askedAt.set(q.ref, [...(askedAt.get(q.ref) ?? []), q]);
  const rows = new Set(group.rows.map((r) => r.ref));
  const openHere = open.some((q) => rows.has(q.ref));
  const allDropped = group.rows.every((r) => r.state === "dropped");

  return (
    <section
      aria-label={group.name}
      className={cn(
        "relative -mx-2 border-l-2 px-2 py-1.5 sm:-mx-3 sm:px-3",
        settled ? "border-transparent" : marked ? "border-paper-accent/60" : "border-live/70",
      )}
    >
      <ul className="flex flex-col gap-0.5">
        {group.rows.map((row) => {
          const card = byRef.get(row.ref);
          if (!card) return null;
          const canDrop =
            dragging !== null &&
            isFrame(card.kind) &&
            row.state !== "approved" &&
            row.state !== "dropped" &&
            parentRef(dragging, review.progress) !== card.ref &&
            canMoveUnder(dragging, card);
          return (
            <Row
                key={row.ref}
                before={(askedAt.get(row.ref) ?? []).map((q) => (
                  <QuestionCard
                    key={q.key}
                    question={q}
                    busy={props.actions.busy}
                    onAnswer={(choice) => props.onAnswer(q, choice)}
                  />
                ))}
                row={row}
                card={card}
                review={review}
                lit={props.lit.has(row.ref)}
                picked={props.picked === row.ref}
                dragging={dragging}
                canDrop={canDrop}
                onPick={() => props.onPick(row.ref)}
                onPickLabel={props.onPickHeading}
                match={
                  // A line the person's card already says word for word changes
                  // nothing, so only the ones that would change it say so.
                  review.matches[row.ref] &&
                  !review.matches[row.ref]!.same && (
                    <MatchLine
                      match={review.matches[row.ref]!}
                      chosen={props.matchChoice(row.ref)}
                      busy={props.actions.busy}
                      onChoose={(choice) => props.onChooseMatch(row.ref, choice)}
                    />
                  )
                }
                actions={props.actions}
                peek={props.peek?.(row.ref)}
              />
          );
        })}
      </ul>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {settled ? (
          <p className="inline-flex min-h-9 items-center gap-1.5 px-1.5 text-[13px] font-medium text-paper-soft">
            <Check className="size-3.5" strokeWidth={2.5} />
            {allDropped ? "Left out" : "Kept"}
          </p>
        ) : (
          <>
            <Mark
              checked={marked}
              label={`${group.name} looks right`}
              disabled={props.actions.busy}
              onChange={(checked) => props.onMark(group, checked)}
            />
            {!marked && open.length > 0 && (
              <p className="text-[12px] text-paper-soft">
                {openHere ? "Answer above" : "Answer the question about it"}, or mark it to go with our pick
                {open.length > 1 ? "s" : ""}.
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export function RebuiltPane(props: Props) {
  const { sections, review, asked } = props;
  const [dragging, setDragging] = useState<Proposal | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 350, tolerance: 6 } }),
  );
  const byRef = new Map(review.cards.map((c) => [c.ref, c]));

  function onDragStart({ active }: DragStartEvent) {
    setDragging(byRef.get(String(active.id)) ?? null);
  }

  function onDragEnd({ active, over }: DragEndEvent) {
    setDragging(null);
    if (!over) return;
    const card = byRef.get(String(active.id));
    const parent = byRef.get(String(over.id));
    if (card && parent && parentRef(card, review.progress) !== parent.ref && canMoveUnder(card, parent)) {
      props.actions.move(card.ref, parent.ref);
    }
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setDragging(null)}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) => `Moving “${contentLine(byRef.get(String(active.id)), review)}”.`,
          onDragOver: ({ over }) =>
            over ? `Over ${contentLine(byRef.get(String(over.id)), review)}.` : "Not over a job.",
          onDragEnd: ({ over }) =>
            over ? `Moved under ${contentLine(byRef.get(String(over.id)), review)}.` : "Left where it was.",
          onDragCancel: () => "Left where it was.",
        },
      }}
    >
      <article
        aria-label="Your resume, rebuilt"
        className="rounded-card border border-black/[0.06] bg-paper px-4 py-5 text-[13.5px] leading-[1.5] text-paper-ink shadow-card sm:px-7 sm:py-7"
      >
        {sections.map((section, i) => (
          <section key={section.key} aria-label={section.heading} className={cn(i > 0 && "mt-6")}>
            <h3 className="mb-2 border-b border-paper-rule pb-1">
              {section.headingBlock !== null ? (
                <button
                  type="button"
                  onClick={() => props.onPickHeading(section.headingBlock!)}
                  className="-mx-1 rounded-inset px-1 text-[11px] font-semibold tracking-[0.14em] text-paper-soft uppercase hover:bg-paper-accent/[0.07]"
                >
                  {section.heading}
                </button>
              ) : (
                <span className="text-[11px] font-semibold tracking-[0.14em] text-paper-soft uppercase">
                  {section.heading}
                </span>
              )}
            </h3>
            <div className="flex flex-col gap-3">
              {section.groups.map((group) => (
                <Group key={group.key} group={group} review={review} asked={asked} props={props} dragging={dragging} />
              ))}
            </div>
          </section>
        ))}
      </article>
      <DragOverlay dropAnimation={null}>
        {dragging && (
          <div className="max-w-md rounded-inset border border-paper-rule bg-paper px-3 py-1.5 text-[13.5px] text-paper-ink shadow-lift">
            {contentLine(dragging, review)}
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function contentLine(card: Proposal | undefined, review: Review): string {
  return card ? contentFor(card, review.progress).framing.headline : "a line";
}
