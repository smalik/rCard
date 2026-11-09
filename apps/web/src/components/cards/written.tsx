"use client";

import { Pencil, UserRound } from "lucide-react";
import { type KeyboardEvent, useEffect, useState } from "react";

import { useCardActions } from "@/components/cards/actions";
import { PlytosWroteGlyph } from "@/components/glyphs";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { BODY_MAX, type WrittenPart } from "@/lib/cards";
import { type LibraryCard, withWords, writtenBy } from "@/lib/library";
import { cn } from "@/lib/utils";

// Long enough for a job's one line; the API allows a little more.
const HEADLINE_LIMIT = 200;

/** Who wrote a part: Plytos, summing up the accomplishments, or the person. */
export function WrittenTag({ by, className }: { by: "plytos" | "person"; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[12px] font-medium",
        by === "plytos" ? "text-pen" : "text-muted-foreground",
        className,
      )}
    >
      {by === "plytos" ? (
        <PlytosWroteGlyph className="size-3.5" />
      ) : (
        <UserRound className="size-3" aria-hidden />
      )}
      {by === "plytos" ? "Plytos wrote this" : "Your words"}
    </span>
  );
}

/** A placeholder with light passing over it, while Plytos writes. */
export function Writing({ lines = 1, label }: { lines?: number; label: string }) {
  return (
    <div role="status" className="flex flex-col gap-1.5" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          aria-hidden
          className={cn(
            "block h-[0.95em] rounded-md bg-[linear-gradient(90deg,var(--muted)_25%,color-mix(in_oklab,var(--pen)_22%,var(--muted))_50%,var(--muted)_75%)] bg-[length:200%_100%] animate-writing motion-reduce:animate-none",
            i === lines - 1 && lines > 1 ? "w-3/5" : "w-full",
          )}
        />
      ))}
      <span aria-hidden className="flex items-center gap-1 text-[12px] font-medium text-pen">
        <PlytosWroteGlyph className="size-3.5 animate-live-dot motion-reduce:animate-none" />
        {label}
      </span>
    </div>
  );
}

/**
 * A job's headline or a title's story: Plytos's summary of the
 * accomplishments until the person writes their own. Shows who wrote it,
 * and edits in place; saving makes the card's next version.
 */
export function WrittenText({
  card,
  part,
  label,
  writing,
  ready,
  empty,
  className,
  textClassName,
}: {
  card: LibraryCard;
  part: WrittenPart;
  // What a screen reader and the editor call it: "Headline", "The story".
  label: string;
  // Plytos is writing this part now.
  writing: boolean;
  // There's something for Plytos to sum up.
  ready: boolean;
  // What shows when nobody has written it yet.
  empty: string;
  className?: string;
  textClassName?: string;
}) {
  const { save } = useCardActions();
  const by = writtenBy(card, part);
  const text = by === null ? "" : part === "headline" ? card.content!.framing.headline : card.content!.framing.body;
  const [editing, setEditing] = useState(false);
  // The card as it was when editing started, so a change made meanwhile is
  // refused rather than overwritten.
  const [base, setBase] = useState(card);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const limit = part === "headline" ? HEADLINE_LIMIT : BODY_MAX;

  function start() {
    setBase(card);
    setDraft(text);
    setError(null);
    setEditing(true);
  }

  async function submit() {
    const content = withWords(base, part, draft);
    if (!content) return;
    setSaving(true);
    setError(null);
    try {
      await save(base, content);
      setEditing(false);
    } catch (e) {
      // Saving again uses the latest version, keeping what they wrote.
      setBase(card);
      setError(
        e instanceof Error && /changed/i.test(e.message)
          ? "This changed while you were writing. Save again to use your words."
          : e instanceof Error
            ? e.message
            : "That didn't save. Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  function keys(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      setEditing(false);
    } else if (event.key === "Enter" && (part === "headline" || event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void submit();
    }
  }

  if (editing) {
    const id = `${card.id}-${part}-edit`;
    return (
      <div className={cn("flex flex-col gap-2", className)}>
        <label htmlFor={id} className="sr-only">
          {label}
        </label>
        <Textarea
          id={id}
          autoFocus
          value={draft}
          maxLength={limit}
          rows={part === "headline" ? 2 : 4}
          onKeyDown={keys}
          onChange={(e) =>
            setDraft(part === "headline" ? e.target.value.replace(/\s*\n\s*/g, " ") : e.target.value)
          }
          className={cn("min-h-0 text-[15px] leading-relaxed", part === "headline" && "font-medium")}
        />
        <p className="text-[12px] text-muted-foreground">
          {part === "headline"
            ? "One line for the whole job. Leave it empty and Plytos sums it up."
            : "Leave it empty and Plytos writes it from the accomplishments."}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => void submit()} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={saving}>
            Cancel
          </Button>
          {error && (
            <span role="alert" className="text-[13px] text-destructive">
              {error}
            </span>
          )}
        </div>
      </div>
    );
  }

  // Plytos writes what it wrote before, and what nobody has written yet.
  const rewriting = writing && by !== "person" && ready;
  if (rewriting && !text) {
    return (
      <div className={className}>
        <Writing
          lines={part === "headline" ? 1 : 2}
          label={part === "headline" ? "Plytos is writing the headline…" : "Plytos is writing the story…"}
        />
      </div>
    );
  }

  return (
    <div className={cn("group/written flex flex-col gap-1", className)}>
      {text ? (
        <p className={cn("whitespace-pre-line text-pretty", textClassName)}>{text}</p>
      ) : (
        <p className="text-[13.5px] text-muted-foreground">{empty}</p>
      )}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        {rewriting ? (
          // What it wrote before stays readable while it writes again.
          <span role="status" className="inline-flex items-center gap-1 text-[12px] font-medium text-pen">
            <PlytosWroteGlyph className="size-3.5 animate-live-dot motion-reduce:animate-none" />
            Rewriting…
          </span>
        ) : (
          by && <WrittenTag by={by} />
        )}
        {(by || rewriting) && <span aria-hidden className="text-[12px] text-muted-foreground/70">·</span>}
        <button
          type="button"
          onClick={start}
          className="inline-flex items-center gap-1 rounded-md text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
        >
          <Pencil className="size-3" aria-hidden />
          {text ? "Edit" : "Write your own"}
          <span className="sr-only"> {label.toLowerCase()}</span>
        </button>
      </div>
    </div>
  );
}

export type RewriteTargets = {
  // Parts Plytos would write: the headline and each title's story.
  parts: number;
  // Of those, how many are the person's own words now.
  own: number;
};

/** The little button that asks Plytos to sum the job up again now. When some
 * parts are the person's own words, it asks first whether to replace them. */
export function RewriteButton({
  jobId,
  employer,
  targets,
  onBusy,
}: {
  jobId: string;
  employer: string;
  targets: RewriteTargets;
  onBusy: (busy: boolean) => void;
}) {
  const { rewrite } = useCardActions();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; failed?: boolean } | null>(null);
  // A note on what was written fades after a while; a failure stays.
  useEffect(() => {
    if (!note || note.failed) return;
    const done = window.setTimeout(() => setNote(null), 8_000);
    return () => window.clearTimeout(done);
  }, [note]);
  if (!rewrite) return null;
  const nothing = targets.parts === 0;

  async function run(replaceOwn: boolean) {
    if (!rewrite) return;
    setAsking(false);
    setBusy(true);
    onBusy(true);
    setNote(null);
    try {
      const done = await rewrite(jobId, replaceOwn);
      const wrote = [
        done.headline ? "the headline" : "",
        done.stories > 0 ? `${done.stories} ${done.stories === 1 ? "story" : "stories"}` : "",
      ].filter(Boolean);
      const left =
        done.dropped > 0
          ? ` It left ${done.dropped === 1 ? "one part" : `${done.dropped} parts`} as ${done.dropped === 1 ? "it was" : "they were"}: the wording used a number your cards don't have.`
          : "";
      setNote({
        text:
          wrote.length > 0
            ? `Plytos rewrote ${wrote.join(" and ")}.${left}`
            : `Nothing changed.${left || " Every part already says what the accomplishments do."}`,
      });
    } catch (e) {
      setNote({ text: e instanceof Error ? e.message : "That didn't work. Try again.", failed: true });
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            disabled={busy || nothing}
            aria-label={`Rewrite the headline and stories for ${employer}`}
            onClick={() => (targets.own > 0 ? setAsking(true) : void run(false))}
            className="inline-flex h-7 items-center gap-1 rounded-full border bg-card px-2.5 text-[12px] font-medium text-pen shadow-sheet transition-colors hover:bg-accent disabled:opacity-50 focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
          >
            <PlytosWroteGlyph className={cn("size-3.5", busy && "animate-live-dot motion-reduce:animate-none")} />
            {busy ? "Writing…" : "Rewrite"}
          </button>
        </TooltipTrigger>
        <TooltipContent>
          {nothing
            ? "Add an accomplishment and Plytos can sum this job up"
            : "Sum up the headline and each title's story again from the accomplishments"}
        </TooltipContent>
      </Tooltip>
      {note && (
        <p
          role={note.failed ? "alert" : "status"}
          className={cn("basis-full text-[12.5px]", note.failed ? "text-destructive" : "text-muted-foreground")}
        >
          {note.text}
        </p>
      )}
      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rewrite your own words too?</DialogTitle>
            <DialogDescription>
              Plytos sums up the headline and each title&apos;s story from the accomplishments.{" "}
              {targets.own === 1 ? "One of them is" : `${targets.own} of them are`} in your own
              words. Anything replaced stays in the card&apos;s history.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => void run(true)}>
              Rewrite mine too
            </Button>
            <Button onClick={() => void run(false)} autoFocus>
              Keep my words
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
