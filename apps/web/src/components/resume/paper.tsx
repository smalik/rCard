// A resume as it reads, on paper. Three ways to show it:
//   - reading: each line that has a card behind it opens that card;
//   - editing: each job and line carries the controls to arrange it, leave it
//     out, or bring in what's on file;
//   - comparing (DiffPaper): lines brought in, left out, reworded and moved,
//     marked in place.
// The paper keeps its colors in dark mode and prints black on white.

import {
  ArrowDown,
  ArrowUp,
  ChevronsDownUp,
  ChevronsUpDown,
  Pencil,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { DisclosureTriangle } from "@/components/cards/strength-card";
import type { DiffEntry, DiffLine, HeaderChange, ResumeDiff } from "@/lib/resume-diff";
import {
  lineParts,
  type RenderedEntry,
  type RenderedItem,
  type RenderedResume,
  type ResumeHeader,
} from "@/lib/resumes";
import { cn } from "@/lib/utils";

export type PaperEdits = {
  busy: boolean;
  switchOff: (card: string) => void;
  switchOn: (entry: string, card: string) => void;
  leaveOut: (entry: string) => void;
  setFold: (entry: string, fold: boolean) => void;
  moveEntry: (entry: string, by: -1 | 1) => void;
  moveLine: (entry: string, group: string[], card: string, by: -1 | 1) => void;
  moveContext: (group: string[], card: string, by: -1 | 1) => void;
  editHeader: () => void;
};

// -- pieces of the page --------------------------------------------------------

export function PaperSheet({ children, className, ...props }: ComponentProps<"article">) {
  return (
    <article
      className={cn(
        "relative min-w-0 rounded-[10px] border border-black/[0.06] bg-paper px-5 py-7 text-[13.5px] leading-[1.5] text-paper-ink shadow-card sm:px-10 sm:py-10 lg:px-14 lg:py-12",
        "print:rounded-none print:border-0 print:p-0 print:text-[10.5pt] print:shadow-none",
        className,
      )}
      {...props}
    >
      {children}
    </article>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="mt-7 mb-2.5 border-b border-paper-rule pb-1 text-[11px] font-semibold tracking-[0.14em] text-paper-soft uppercase print:mt-5 print:break-after-avoid">
      {children}
    </h3>
  );
}

/** A small control on the paper. The paper stays light in dark mode, so these
 * use the paper's colors rather than the app's. */
function PaperButton({
  label,
  children,
  className,
  ...props
}: ComponentProps<"button"> & { label?: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-7 min-w-7 items-center justify-center gap-1 rounded-full px-1.5 text-[12px] font-medium text-paper-soft transition-colors hover:bg-black/[0.06] hover:text-paper-ink focus-visible:ring-2 focus-visible:ring-paper-accent/50 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-35 print:hidden [&_svg]:size-3.5",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function Contact({ header }: { header: ResumeHeader }) {
  const contact = [header.location, header.email, header.phone, ...header.links].filter(Boolean);
  if (contact.length === 0) return null;
  return (
    <p className="mt-1.5 text-[12.5px] [overflow-wrap:anywhere] text-paper-soft">
      {contact.join("  ·  ")}
    </p>
  );
}

function Top({ header, edit }: { header: ResumeHeader; edit?: PaperEdits }) {
  const empty =
    !header.name &&
    !header.headline &&
    !header.email &&
    !header.phone &&
    !header.location &&
    header.links.length === 0;
  if (empty && !header.summary && !edit) return null;
  return (
    <header className="relative pb-1">
      {edit && (
        <PaperButton
          className="absolute -top-1 right-0 border border-paper-rule bg-paper px-2.5"
          disabled={edit.busy}
          onClick={edit.editHeader}
        >
          <Pencil /> {empty ? "Add your name and contact" : "Edit the top"}
        </PaperButton>
      )}
      {header.name && (
        <h2 className="pr-28 text-[26px] leading-tight font-semibold tracking-[-0.02em] sm:text-[28px] print:pr-0 print:text-[20pt]">
          {header.name}
        </h2>
      )}
      {header.headline && <p className="mt-0.5 text-[14px] text-paper-ink/85">{header.headline}</p>}
      <Contact header={header} />
      {header.summary && <p className="mt-3.5 text-[13.5px] leading-relaxed">{header.summary}</p>}
    </header>
  );
}

function Mark({ kind, children }: { kind: "added" | "removed" | "moved" | "note"; children: ReactNode }) {
  return (
    <span
      className={cn(
        "ml-1.5 inline-flex h-[18px] items-center rounded-full px-1.5 align-[1px] text-[10.5px] font-semibold tracking-[0.02em] whitespace-nowrap",
        kind === "added" && "bg-paper-accent text-white",
        kind === "removed" && "bg-paper-removed/12 text-paper-removed",
        kind === "moved" && "border border-paper-rule text-paper-soft",
        kind === "note" && "bg-black/[0.05] text-paper-soft",
      )}
    >
      {children}
    </span>
  );
}

function Worded({ wording }: { wording: RenderedItem["wording"] }) {
  if (wording === "main") return null;
  const label = wording === "target" ? "Worded for this version" : "Wording kept for this resume";
  return (
    <span
      title={label}
      className="ml-1 inline-flex align-[-1px] text-paper-accent print:hidden"
    >
      <Sparkles aria-hidden className="size-3" />
      <span className="sr-only">({label.toLowerCase()})</span>
    </span>
  );
}

// -- reading and editing -------------------------------------------------------

type LineProps = {
  item: RenderedItem;
  // Context lines, such as a degree, show their date at the right.
  dated?: boolean;
  edit?: PaperEdits;
  onOpen?: (card: string) => void;
  // For moving it among the lines shown with it.
  up?: () => void;
  down?: () => void;
};

/** A bullet drawn on the line's first row; list markers drift on lines that
 * hold controls. */
function Bullet() {
  return <span aria-hidden className="mt-[0.62em] size-[4.5px] shrink-0 rounded-full bg-paper-ink/55" />;
}

function Line({ item, dated, bullet, edit, onOpen, up, down }: LineProps & { bullet: boolean }) {
  const { text, detail } = lineParts(item);
  const words = (
    <>
      {text}
      <Worded wording={item.wording} />
    </>
  );
  return (
    <li className="group/line relative print:break-inside-avoid">
      <div className="flex items-start gap-2.5">
        {bullet && <Bullet />}
        <span className="min-w-0 flex-1">
          {onOpen && !edit ? (
            <button
              type="button"
              onClick={() => onOpen(item.card)}
              className="-mx-1 rounded-[5px] px-1 text-left transition-colors hover:bg-paper-accent/[0.08] focus-visible:ring-2 focus-visible:ring-paper-accent/50 focus-visible:outline-none"
            >
              {words}
              <span className="sr-only"> (open its card)</span>
            </button>
          ) : (
            words
          )}
        </span>
        {dated && item.date && (
          <span className="shrink-0 text-[12.5px] text-paper-soft tabular-nums">{item.date}</span>
        )}
        {edit && (
          // With a mouse the controls float over the line's end on hover, so
          // the page keeps its shape; on touch they always show.
          <span className="-mt-0.5 -mr-1.5 flex shrink-0 items-center pointer-fine:absolute pointer-fine:-top-0.5 pointer-fine:right-0 pointer-fine:mr-0 pointer-fine:mt-0 pointer-fine:rounded-full pointer-fine:border pointer-fine:border-paper-rule pointer-fine:bg-paper pointer-fine:px-0.5 pointer-fine:opacity-0 pointer-fine:shadow-sm pointer-fine:transition-opacity pointer-fine:group-focus-within/line:opacity-100 pointer-fine:group-hover/line:opacity-100">
            {up && (
              <PaperButton label={`Move up: ${text}`} disabled={edit.busy} onClick={up}>
                <ArrowUp />
              </PaperButton>
            )}
            {down && (
              <PaperButton label={`Move down: ${text}`} disabled={edit.busy} onClick={down}>
                <ArrowDown />
              </PaperButton>
            )}
            <PaperButton
              label={`Leave out: ${text}`}
              disabled={edit.busy}
              onClick={() => edit.switchOff(item.card)}
            >
              <X />
            </PaperButton>
          </span>
        )}
      </div>
      {detail && <p className={cn("text-[12.5px] text-paper-soft", bullet && "pl-[14.5px]")}>{detail}</p>}
    </li>
  );
}

function Lines({
  items,
  edit,
  onOpen,
  canOpen,
  move,
  bullets = true,
  dated = false,
}: {
  items: RenderedItem[];
  edit?: PaperEdits;
  onOpen?: (card: string) => void;
  canOpen?: (card: string) => boolean;
  move?: (group: string[], card: string, by: -1 | 1) => void;
  bullets?: boolean;
  dated?: boolean;
}) {
  if (items.length === 0) return null;
  const group = items.map((i) => i.card);
  return (
    <ul className={cn("mt-1 flex flex-col gap-1", bullets && "pl-1")}>
      {items.map((item, i) => (
        <Line
          key={item.card}
          item={item}
          bullet={bullets}
          dated={dated}
          edit={edit}
          onOpen={onOpen && (!canOpen || canOpen(item.card)) ? onOpen : undefined}
          up={move && i > 0 ? () => move(group, item.card, -1) : undefined}
          down={move && i < items.length - 1 ? () => move(group, item.card, 1) : undefined}
        />
      ))}
    </ul>
  );
}

function Employer({
  employer,
  location,
  dates,
  marks,
}: {
  employer: string;
  location: string;
  dates: string;
  marks?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-x-4 sm:flex-row sm:items-baseline sm:justify-between">
      <p className="min-w-0">
        <b className="font-semibold">{employer}</b>
        {location && <span className="text-paper-ink/80">, {location}</span>}
        {marks}
      </p>
      {dates && (
        <p className="shrink-0 text-[12.5px] text-paper-soft tabular-nums sm:text-right">{dates}</p>
      )}
    </div>
  );
}

function Title({ title, dates }: { title: string; dates: string }) {
  return (
    <p className="mt-1.5 flex flex-col gap-x-4 sm:flex-row sm:items-baseline sm:justify-between">
      <span className="font-medium text-paper-ink/90 italic">{title}</span>
      {dates && (
        <span className="shrink-0 text-[12.5px] text-paper-soft tabular-nums not-italic">{dates}</span>
      )}
    </p>
  );
}

function EntryTools({
  entry,
  index,
  count,
  edit,
}: {
  entry: RenderedEntry;
  index: number;
  count: number;
  edit: PaperEdits;
}) {
  const titled = entry.roles.filter((r) => r.card !== null);
  const canFold = titled.length > 1 || entry.earlier_titles.length > 0;
  return (
    <div className="mt-1 -ml-1.5 flex flex-wrap items-center gap-0.5 print:hidden">
      <PaperButton
        label={`Move ${entry.employer} up`}
        disabled={edit.busy || index === 0}
        onClick={() => edit.moveEntry(entry.card, -1)}
      >
        <ArrowUp />
      </PaperButton>
      <PaperButton
        label={`Move ${entry.employer} down`}
        disabled={edit.busy || index === count - 1}
        onClick={() => edit.moveEntry(entry.card, 1)}
      >
        <ArrowDown />
      </PaperButton>
      {canFold && (
        <PaperButton
          className="px-2"
          disabled={edit.busy}
          onClick={() => edit.setFold(entry.card, !entry.fold_earlier)}
        >
          {entry.fold_earlier ? <ChevronsUpDown /> : <ChevronsDownUp />}
          {entry.fold_earlier ? "Show each title" : "Fold earlier titles"}
        </PaperButton>
      )}
      <PaperButton className="px-2" disabled={edit.busy} onClick={() => edit.leaveOut(entry.card)}>
        <X /> Leave out
      </PaperButton>
    </div>
  );
}

function OnFile({ entry, edit }: { entry: RenderedEntry; edit: PaperEdits }) {
  if (entry.hidden.length === 0) return null;
  return (
    <details className="group/more mt-2 rounded-[8px] border border-dashed border-paper-rule print:hidden">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-1.5 text-[12.5px] font-medium text-paper-soft [&::-webkit-details-marker]:hidden">
        <DisclosureTriangle open={false} className="text-paper-soft group-open/more:rotate-90" />
        {entry.hidden.length} more {entry.hidden.length === 1 ? "line" : "lines"} on file for{" "}
        {entry.employer}
      </summary>
      <ul className="flex flex-col border-t border-dashed border-paper-rule px-1.5 py-1">
        {entry.hidden.map((item) => (
          <li key={item.card} className="flex items-start gap-2 rounded-[6px] px-1.5 py-1">
            <span className="min-w-0 flex-1 text-paper-ink/80">{lineParts(item).text}</span>
            <PaperButton
              label={`Add: ${item.text}`}
              disabled={edit.busy}
              onClick={() => edit.switchOn(entry.card, item.card)}
            >
              <Plus />
            </PaperButton>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function Paper({
  page,
  edit,
  onOpen,
  canOpen,
}: {
  page: RenderedResume;
  edit?: PaperEdits;
  onOpen?: (card: string) => void;
  canOpen?: (card: string) => boolean;
}) {
  const empty = page.entries.length === 0 && page.sections.length === 0;
  return (
    <PaperSheet aria-label="Resume">
      <Top header={page.header} edit={edit} />

      {page.entries.length > 0 && <SectionHeading>Experience</SectionHeading>}
      <div className="flex flex-col gap-4">
        {page.entries.map((entry, index) => (
          <section key={entry.card} aria-label={entry.employer} className="print:break-inside-avoid-page">
            <Employer employer={entry.employer} location={entry.location} dates={entry.dates} />
            {edit && (
              <EntryTools entry={entry} index={index} count={page.entries.length} edit={edit} />
            )}
            {entry.roles.map((role) => (
              <div key={role.card ?? "employment"}>
                {role.card !== null && <Title title={role.title} dates={role.dates} />}
                <Lines
                  items={role.items}
                  edit={edit}
                  onOpen={onOpen}
                  canOpen={canOpen}
                  // Folded titles share one list; their order follows each title.
                  move={
                    edit && !entry.fold_earlier
                      ? (group, card, by) => edit.moveLine(entry.card, group, card, by)
                      : undefined
                  }
                />
              </div>
            ))}
            {entry.earlier_titles.length > 0 && (
              <p className="mt-1.5 text-[12.5px] text-paper-soft">
                Earlier: {entry.earlier_titles.join("; ")}
              </p>
            )}
            {edit && <OnFile entry={entry} edit={edit} />}
          </section>
        ))}
      </div>

      {page.sections.map((section) => (
        <section key={section.kind} aria-label={section.label}>
          <SectionHeading>{section.label}</SectionHeading>
          <Lines
            items={section.items}
            edit={edit}
            onOpen={onOpen}
            canOpen={canOpen}
            bullets={section.kind === "accomplishment" || section.kind === "project"}
            dated
            move={edit ? edit.moveContext : undefined}
          />
        </section>
      ))}

      {empty && (
        <p className="mt-6 rounded-[8px] border border-dashed border-paper-rule px-4 py-6 text-center text-paper-soft">
          {edit
            ? "Nothing shows yet. Add jobs and cards from the list beside the page."
            : "Nothing shows on this resume yet. Choose Edit to bring in jobs and cards."}
        </p>
      )}
      {page.missing > 0 && (
        <p className="mt-6 text-[12.5px] text-paper-soft print:hidden">
          {page.missing} {page.missing === 1 ? "line is" : "lines are"} hidden because the card was
          archived.
        </p>
      )}
    </PaperSheet>
  );
}

// -- comparing -------------------------------------------------------------------

function DiffLineView({ line, bullet, dated }: { line: DiffLine; bullet: boolean; dated: boolean }) {
  const removed = line.presence === "removed";
  return (
    <li
      className={cn(
        "-mx-1.5 rounded-[4px] px-1.5 print:break-inside-avoid",
        line.presence === "added" && "bg-paper-added",
        removed && "bg-paper-removed/[0.06]",
      )}
    >
      <div className="flex items-start gap-2.5">
        {bullet && <Bullet />}
        <span className="min-w-0 flex-1">
          {line.presence === "added" && <span className="sr-only">Added: </span>}
          {removed && <span className="sr-only">Left out: </span>}
          <span className={cn(removed && "text-paper-removed line-through decoration-paper-removed/50")}>
            {line.text}
          </span>
          {line.moved && <Mark kind="moved">Moved</Mark>}
        </span>
        {dated && line.date && (
          <span className="shrink-0 text-[12.5px] text-paper-soft tabular-nums">{line.date}</span>
        )}
      </div>
      <div className={cn(bullet && "pl-[14.5px]")}>
        {line.was !== null && (
          <p className="mt-0.5 text-[12px] text-paper-soft">
            <span className="font-medium">Reworded.</span> It read:{" "}
            <span className="line-through decoration-paper-soft/60">{line.was}</span>
          </p>
        )}
        {line.detail && !removed && <p className="text-[12.5px] text-paper-soft">{line.detail}</p>}
      </div>
    </li>
  );
}

function DiffLines({
  lines,
  bullets = true,
  dated = false,
}: {
  lines: DiffLine[];
  bullets?: boolean;
  dated?: boolean;
}) {
  if (lines.length === 0) return null;
  return (
    <ul className={cn("mt-1 flex flex-col gap-1", bullets && "pl-1")}>
      {lines.map((l) => (
        <DiffLineView key={`${l.presence}-${l.card}`} line={l} bullet={bullets} dated={dated} />
      ))}
    </ul>
  );
}

function DiffJob({ entry }: { entry: DiffEntry }) {
  const removed = entry.presence === "removed";
  return (
    <section
      aria-label={entry.employer}
      className={cn(
        entry.presence === "added" && "-mx-3 border-l-2 border-paper-accent px-2.5 py-1",
        removed && "-mx-3 border-l-2 border-paper-removed/70 px-2.5 py-1 opacity-80",
      )}
    >
      <Employer
        employer={entry.employer}
        location={entry.location}
        dates={entry.dates}
        marks={
          <>
            {entry.presence === "added" && <Mark kind="added">Added</Mark>}
            {removed && <Mark kind="removed">Left out</Mark>}
            {entry.moved && <Mark kind="moved">Moved</Mark>}
            {entry.fold === "folded" && <Mark kind="note">Earlier titles folded</Mark>}
            {entry.fold === "unfolded" && <Mark kind="note">Each title shown</Mark>}
          </>
        }
      />
      {entry.roles.map((role) => (
        <div key={role.key}>
          {role.key !== "employment" && <Title title={role.title} dates={role.dates} />}
          <DiffLines lines={role.lines} />
        </div>
      ))}
      {entry.earlier_titles.length > 0 && (
        <p className="mt-1.5 text-[12.5px] text-paper-soft">Earlier: {entry.earlier_titles.join("; ")}</p>
      )}
    </section>
  );
}

function TopChanges({ changes }: { changes: HeaderChange[] }) {
  if (changes.length === 0) return null;
  return (
    <ul className="mt-3 flex flex-col gap-1 rounded-[8px] bg-black/[0.035] px-3 py-2 text-[12.5px]">
      {changes.map((c) => (
        <li key={c.field}>
          <span className="font-semibold">{c.label}</span>{" "}
          {c.was ? (
            <>
              changed. It read: <span className="text-paper-soft line-through">{c.was}</span>
            </>
          ) : (
            "added."
          )}
          {!c.now && " Now left blank."}
        </li>
      ))}
    </ul>
  );
}

export function DiffPaper({ diff, header }: { diff: ResumeDiff; header: ResumeHeader }) {
  return (
    <PaperSheet aria-label="Resume, with changes marked">
      <Top header={header} />
      <TopChanges changes={diff.header} />
      {diff.entries.length > 0 && <SectionHeading>Experience</SectionHeading>}
      <div className="flex flex-col gap-4">
        {diff.entries.map((entry) => (
          <DiffJob key={entry.card} entry={entry} />
        ))}
      </div>
      {diff.sections.map((section) => (
        <section key={section.kind} aria-label={section.label}>
          <SectionHeading>
            {section.label}
            {section.presence === "added" && <Mark kind="added">Added</Mark>}
            {section.presence === "removed" && <Mark kind="removed">Left out</Mark>}
          </SectionHeading>
          <DiffLines
            lines={section.lines}
            bullets={section.kind === "accomplishment" || section.kind === "project"}
            dated
          />
        </section>
      ))}
    </PaperSheet>
  );
}
