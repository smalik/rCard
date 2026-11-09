"use client";

// Your resume, rebuilt, beside your own file. The person has one thing to do:
// glance at it and say "yes, that's me". Tapping a line on either side lights
// up its partner on the other. Plytos asks only what it isn't sure of, with an
// answer already picked; jobs it's sure of come marked "Looks right". A fix
// (rewording, dates, moving a line to another job, leaving one out) happens at
// once, says what it did, and can be undone. Nothing becomes a card until the
// person says it's them.

import { ArrowLeft, ArrowRight, Check, Ellipsis, Undo2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { CardContent } from "@/lib/cards";
import {
  type CardMatch,
  contentFor,
  dateSpan,
  type MatchChoice,
  parentRef,
  plural,
  type Progress,
  type Proposal,
  type Review,
  stateOf,
  toProgress,
} from "@/lib/imports";
import {
  cardsByLine,
  coverage,
  coverageDetail,
  coverageText,
  fateOf,
  fateText,
  groupQuestions,
  isSettled,
  isSure,
  placeName,
  type Question,
  questions,
  rebuild,
  type RebuiltGroup,
  type ResumeFile,
  reworded,
} from "@/lib/rebuilt";
import { type Dates, keepRequest, NO_CHOICES } from "@/lib/review";
import { cn } from "@/lib/utils";

import { send } from "../talk/send";
import { FilePane, type FileMarks, lineId } from "./file-pane";
import { RebuiltPane, rowId } from "./rebuilt-pane";

type Pick = { side: "file"; block: number } | { side: "rebuilt"; ref: string } | { side: "heading"; block: number };

type Toast = { text: string; undo?: () => Promise<void> };

// What the screen's own routes answer: the new progress, and for a card, which
// of the person's cards the rest now stand for.
type Answered = Progress | { progress: Progress; matches?: Record<string, CardMatch> };

const TOAST_MS = 10_000;

function useWide(): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 768px)");
    const update = () => setWide(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

function smooth(): ScrollBehavior {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

function quoted(text: string, most = 60): string {
  return `“${text.length > most ? `${text.slice(0, most - 1).trimEnd()}…` : text}”`;
}

// The card and every card under it, as the person put them.
function withChildren(card: Proposal, review: Review): Proposal[] {
  const out = [card];
  for (let i = 0; i < out.length; i++) {
    const above = out[i]!.ref;
    out.push(...review.cards.filter((c) => parentRef(c, review.progress) === above && !out.includes(c)));
  }
  return out;
}

function withDates(content: CardContent, dates: Dates): CardContent {
  const facts = { ...content.facts };
  const start = dates.start.trim();
  const end = dates.end.trim().toLowerCase() === "present" ? "present" : dates.end.trim();
  if (start) facts.start = start;
  else delete facts.start;
  if (end) facts.end = end;
  else delete facts.end;
  return { ...content, facts };
}

export function ReviewScreen({ initial, file }: { initial: Review; file: ResumeFile }) {
  const router = useRouter();
  const wide = useWide();
  const [review, setReview] = useState(initial);
  const [pick, setPick] = useState<Pick | null>(null);
  const [tab, setTab] = useState<"rebuilt" | "file">("rebuilt");
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [kept, setKept] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  // For lines that are already the person's cards: what keeping does to them.
  const [matchChoices, setMatchChoices] = useState<Record<string, MatchChoice>>({});

  const id = review.id;
  const base = `/import/${encodeURIComponent(id)}`;
  const sections = useMemo(() => rebuild(review, file), [review, file]);
  const asked = useMemo(() => questions(review), [review]);
  const byLine = useMemo(() => cardsByLine(review), [review]);
  const counted = useMemo(() => coverage(file, review), [file, review]);
  const byRef = useMemo(() => new Map(review.cards.map((c) => [c.ref, c])), [review]);
  const groups = sections.flatMap((s) => s.groups);

  const marked = (group: RebuiltGroup) => marks[group.key] ?? isSure(group, review, asked);

  // -- what's lit -------------------------------------------------------------

  const litBlocks = new Set<number>();
  const litRefs = new Set<string>();
  if (pick?.side === "rebuilt") {
    litRefs.add(pick.ref);
    for (const b of byRef.get(pick.ref)?.source_blocks ?? []) litBlocks.add(b);
  } else if (pick) {
    litBlocks.add(pick.block);
    if (pick.side === "file") for (const r of byLine.get(pick.block) ?? []) litRefs.add(r);
  }
  const fileMarks: FileMarks = {
    lit: litBlocks,
    loose: new Set(counted.loose),
    quiet: new Set([...file.contact, ...Object.keys(file.skipped).map(Number)]),
    headings: new Set(file.headings),
  };

  // The partner of what was picked comes into view on the other side.
  useEffect(() => {
    if (!pick || !wide) return;
    const target =
      pick.side === "rebuilt"
        ? [...litBlocks].sort((a, b) => a - b).map(lineId)[0]
        : [...litRefs].map(rowId)[0];
    if (target) document.getElementById(target)?.scrollIntoView({ block: "nearest", behavior: smooth() });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the pick changes
  }, [pick, wide]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), TOAST_MS);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !(e.target instanceof HTMLTextAreaElement)) setPick(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // -- talking to the server ----------------------------------------------------

  function applied(data: Answered, to: Review): Review {
    return "progress" in data && typeof data.progress === "object" && "cards" in data.progress
      ? { ...to, progress: toProgress(data.progress), matches: data.matches ?? to.matches }
      : { ...to, progress: toProgress(data as Progress) };
  }

  // Sends one change; answers with the review after it, or null when it failed.
  async function post(url: string, body: unknown, to: Review = review): Promise<Review | null> {
    const result = await send<Answered>(url, body);
    if (!result.ok) {
      setError(result.error);
      return null;
    }
    const next = applied(result.data, to);
    setReview(next);
    return next;
  }

  async function act(label: string, work: () => Promise<boolean>, toastWith?: Toast) {
    if (busy) return;
    setBusy(label);
    setError(null);
    try {
      if ((await work()) && toastWith) setToast(toastWith);
    } finally {
      setBusy(null);
    }
  }

  const cardUrl = (ref: string) => `${base}/cards/${encodeURIComponent(ref)}`;

  function undoWith(label: string, work: () => Promise<boolean>) {
    return async () => {
      setToast(null);
      await act(label, work);
    };
  }

  function fix(ref: string, next: CardContent, said: string) {
    const card = byRef.get(ref);
    if (!card) return;
    const before = review.progress.fixes[ref] ?? null;
    void act(
      "Saving your change…",
      async () => (await post(cardUrl(ref), { action: "fix", content: next })) !== null,
      {
        text: said,
        undo: undoWith("Putting it back…", async () => (await post(cardUrl(ref), { action: "fix", content: before })) !== null),
      },
    );
  }

  const actions = {
    busy: busy !== null,
    reword(ref: string, text: string) {
      const card = byRef.get(ref);
      if (!card) return;
      fix(ref, reworded(card, contentFor(card, review.progress), text), "Reworded it.");
    },
    redate(ref: string, dates: Dates) {
      const card = byRef.get(ref);
      if (!card) return;
      const next = withDates(contentFor(card, review.progress), dates);
      const span = dateSpan(next.facts);
      fix(ref, next, span ? `Dates changed to ${span}.` : "Dates taken off.");
    },
    move(ref: string, to: string) {
      const card = byRef.get(ref);
      if (!card) return;
      const from = parentRef(card, review.progress);
      const text = contentFor(card, review.progress).framing.headline;
      void act(
        "Moving it…",
        async () => (await post(cardUrl(ref), { action: "place", parent_ref: to })) !== null,
        {
          text: `Moved ${quoted(text)} to ${placeName(to, review)}.`,
          undo: undoWith("Moving it back…", async () => (await post(cardUrl(ref), { action: "place", parent_ref: from })) !== null),
        },
      );
    },
    leaveOut(ref: string) {
      const card = byRef.get(ref);
      if (!card) return;
      const all = withChildren(card, review).filter((c) => {
        const state = stateOf(c.ref, review.progress);
        return state === "pending" || state === "later";
      });
      const refs = all.map((c) => c.ref);
      const text = contentFor(card, review.progress).framing.headline;
      const under = refs.length - 1;
      void act(
        "Leaving it out…",
        async () => (await post(`${base}/keep`, { leave_out: refs })) !== null,
        {
          text:
            under > 0
              ? `Left out ${quoted(text)} and the ${plural(under, "line")} under it.`
              : `Left out ${quoted(text)}.`,
          undo: undoWith("Bringing it back…", () => bringBack(refs)),
        },
      );
    },
    bringBack(ref: string) {
      const card = byRef.get(ref);
      if (!card) return;
      const refs = withChildren(card, review)
        .filter((c) => stateOf(c.ref, review.progress) === "dropped")
        .map((c) => c.ref);
      void act("Bringing it back…", () => bringBack(refs));
    },
  };

  async function bringBack(refs: string[]): Promise<boolean> {
    let current: Review | null = review;
    for (const ref of refs) {
      current = await post(cardUrl(ref), { action: "pending" }, current);
      if (!current) return false;
    }
    return true;
  }

  async function answerWith(question: Question, choice: number, to: Review): Promise<Review | null> {
    const picked = question.choices[choice];
    if (!picked) return to;
    if (picked.answer.kind === "place") {
      return post(cardUrl(picked.answer.ref), { action: "place", parent_ref: picked.answer.parentRef }, to);
    }
    return post(
      `${base}/answer`,
      { finding: picked.answer.index, answer: picked.answer.answer, value: picked.answer.value },
      to,
    );
  }

  function answer(question: Question, choice: number) {
    void act("Saving your answer…", async () => (await answerWith(question, choice, review)) !== null);
  }

  // "Yes, that's me": answers what's still asked in the jobs marked right with
  // Plytos's pick, then keeps each of them, a job at a time.
  async function confirm() {
    const keys = new Set(groups.filter((g) => !isSettled(g, review) && marked(g)).map((g) => g.key));
    if (keys.size === 0 || busy) return;
    setBusy("Keeping your resume…");
    setError(null);
    const approvedBefore = review.cards.filter((c) => stateOf(c.ref, review.progress) === "approved").length;
    let current: Review | null = review;
    try {
      for (const group of groups.filter((g) => keys.has(g.key))) {
        for (const q of groupQuestions(group, questions(current)).filter((q) => q.answered === null)) {
          current = await answerWith(q, q.picked, current);
          if (!current) return;
        }
      }
      // Answers can move a line between jobs, so the jobs are read again.
      const now: Review = current;
      const after = rebuild(now, file).flatMap((s) => s.groups);
      for (const group of after.filter((g) => keys.has(g.key) && !isSettled(g, now))) {
        setBusy(`Keeping ${group.name}…`);
        const request = keepRequest(group.group, current, { ...NO_CHOICES, choice: matchChoices });
        if (request.keep.length + request.leave_out.length + request.later.length === 0) continue;
        current = await post(`${base}/keep`, request, current);
        if (!current) return;
      }
      const approvedAfter = current.cards.filter((c) => stateOf(c.ref, current!.progress) === "approved").length;
      setKept(approvedAfter - approvedBefore);
      setToast(null);
      setPick(null);
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("Deleting…");
    const response = await fetch(`${base}/delete`, { method: "POST" }).catch(() => null);
    setBusy(null);
    if (!response?.ok) {
      setError("That didn't delete. Try again in a moment.");
      setDeleting(false);
      return;
    }
    router.replace("/import");
    router.refresh();
  }

  // -- picking lines -----------------------------------------------------------

  function pickRow(ref: string) {
    setPick((p) => (p?.side === "rebuilt" && p.ref === ref ? null : { side: "rebuilt", ref }));
  }

  function pickLine(block: number) {
    setPick((p) => (p?.side === "file" && p.block === block ? null : { side: "file", block }));
  }

  // Switches to the other side and brings a line into view once it's drawn.
  function showIn(where: "file" | "rebuilt", id: string) {
    setTab(where);
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        document.getElementById(id)?.scrollIntoView({ block: "center", behavior: smooth() }),
      ),
    );
  }

  // On a phone, under a picked line: where it came from in the file.
  function peek(ref: string) {
    if (wide) return null;
    const lines = (byRef.get(ref)?.source_blocks ?? []).flatMap((b) => file.lines.filter((l) => l.block === b));
    if (lines.length === 0) return null;
    return (
      <div className="mt-1 mb-0.5 ml-1.5 rounded-inset border-l-2 border-paper-accent/60 bg-black/[0.03] px-2.5 py-1.5 text-[12.5px] text-paper-soft">
        <p className="font-medium text-paper-ink/80">In your file{lines[0]!.page ? `, page ${lines[0]!.page}` : ""}</p>
        {lines.map((l) => (
          <p key={l.block} className="[overflow-wrap:anywhere]">
            {l.text}
          </p>
        ))}
        <button
          type="button"
          className="mt-1 inline-flex items-center gap-1 font-medium text-paper-accent"
          onClick={() => showIn("file", lineId(lines[0]!.block))}
        >
          See it in your file <ArrowRight className="size-3" />
        </button>
      </div>
    );
  }

  const fileFate = pick?.side === "file" ? fateOf(pick.block, file, byLine) : null;
  const fileNote = fileFate && fileFate.kind !== "cards" ? fateText(fileFate) : null;
  const fileCards =
    !wide && fileFate?.kind === "cards"
      ? fileFate.refs.flatMap((r) => (byRef.get(r) ? [byRef.get(r)!] : []))
      : [];

  // -- the dock ----------------------------------------------------------------

  const open = groups.filter((g) => !isSettled(g, review));
  const ready = open.filter(marked);
  const waiting = open.filter((g) => !marked(g));
  const jobsReady = ready.filter((g) => g.kind === "job").length;
  const restReady = ready.length - jobsReady;
  const readyText = [
    jobsReady > 0 ? plural(jobsReady, "job") : "",
    restReady > 0 ? plural(restReady, "section") : "",
  ]
    .filter(Boolean)
    .join(" and ");

  const waitText =
    waiting.length === 1 ? `${waiting[0]!.name} waits for you.` : `${waiting.length} parts wait for you.`;
  const dockText =
    kept !== null && ready.length === 0
      ? open.length === 0
        ? `Kept. ${plural(kept, "card")} from this resume ${kept === 1 ? "is" : "are"} yours now.`
        : `Kept ${plural(kept, "card")}. ${waitText}`
      : open.length === 0
        ? "Everything here is kept or left out."
        : ready.length === 0
          ? "Mark what looks right, then keep it."
          : `${readyText} look${ready.length === 1 ? "s" : ""} right.${waiting.length > 0 ? ` ${waitText}` : ""}`;

  const filePane = (
    <div className="flex flex-col gap-3">
      {wide && fileNote && (
        <p role="status" className="sticky top-0 z-10 rounded-inset border bg-card px-3 py-2 text-[13px] text-muted-foreground shadow-sheet">
          {fileNote}
        </p>
      )}
      <FilePane importId={id} file={file} marks={fileMarks} onPick={pickLine} />
    </div>
  );

  const rebuiltPane = (
    <RebuiltPane
      sections={sections}
      review={review}
      asked={asked}
      lit={litRefs}
      picked={pick?.side === "rebuilt" ? pick.ref : null}
      marked={marked}
      onMark={(group, value) => setMarks((m) => ({ ...m, [group.key]: value }))}
      onPick={pickRow}
      onPickHeading={(block) => setPick({ side: "heading", block })}
      onAnswer={answer}
      matchChoice={(ref) => matchChoices[ref] ?? "update"}
      onChooseMatch={(ref, choice) => setMatchChoices((c) => ({ ...c, [ref]: choice }))}
      actions={actions}
      peek={peek}
    />
  );

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col px-4 md:-mb-16 md:h-[calc(100dvh-3.5rem)] md:px-6">
      <header className="flex shrink-0 items-start gap-3 pt-3 pb-3 md:pt-5">
        <div className="min-w-0 flex-1">
          <Link
            href="/import"
            className="-ml-1 inline-flex items-center gap-1 rounded-full px-1 text-[14px] font-medium text-primary"
          >
            <ArrowLeft className="size-4" /> Your files
          </Link>
          <h1 className="mt-1 text-[24px] leading-tight font-semibold tracking-[-0.02em] md:text-[28px]">
            Your resume, rebuilt
          </h1>
          <p className="mt-1 text-[15px] text-foreground/85">
            {coverageText(counted)} Tap any line to see where it came from.
          </p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            {coverageDetail(counted)} · {review.file.name}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="More for this file" className="mt-6">
              <Ellipsis />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem asChild>
              <a href={`${base}/original`} target="_blank" rel="noreferrer">
                Open your file
              </a>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href={`/talk?review=${encodeURIComponent(id)}`}>Go through it in Talk instead</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href={`${base}/audit`}>See the full audit</Link>
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(true)}>
              Delete this file
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      {!wide && (
        <div
          role="tablist"
          aria-label="Show"
          className="sticky top-0 z-20 -mx-4 mb-3 grid grid-cols-2 gap-1 border-b border-border/70 bg-background/85 px-4 py-2 backdrop-blur-xl"
        >
          {(
            [
              ["rebuilt", "Rebuilt"],
              ["file", "Your file"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              type="button"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={cn(
                "h-9 rounded-[8px] text-[14px] font-medium text-muted-foreground transition-colors",
                tab === key && "bg-card text-foreground shadow-sheet",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {wide ? (
        <div className="grid min-h-0 flex-1 grid-cols-2 gap-4 lg:gap-6">
          <section aria-label="Your file" className="min-h-0 overflow-y-auto overscroll-contain pb-6">
            <h2 className="mb-2 text-[12px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
              Your file
            </h2>
            {filePane}
          </section>
          <section aria-label="Rebuilt by Plytos" className="min-h-0 overflow-y-auto overscroll-contain pb-6">
            <h2 className="mb-2 text-[12px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
              Rebuilt by Plytos
            </h2>
            {rebuiltPane}
          </section>
        </div>
      ) : (
        <div className="pb-28">{tab === "rebuilt" ? rebuiltPane : filePane}</div>
      )}

      <div
        className={cn(
          "z-30 flex flex-col gap-2",
          wide
            ? "shrink-0 border-t border-border/70 py-3"
            : "fixed inset-x-0 bottom-(--tab-bar-clear) border-t border-border/70 bg-background/90 px-4 py-2.5 backdrop-blur-xl",
        )}
      >
        {!wide && tab === "file" && pick?.side === "file" && (fileNote || fileCards.length > 0) && (
          <div role="status" className="rounded-inset border bg-card px-3 py-2 text-[13px] shadow-sheet">
            {fileNote ?? (
              <>
                <span className="text-muted-foreground">On your resume as </span>
                {fileCards.map((c) => quoted(contentFor(c, review.progress).framing.headline, 80)).join(", ")}
                <button
                  type="button"
                  className="ml-2 inline-flex items-center gap-1 font-medium text-primary"
                  onClick={() => showIn("rebuilt", rowId(fileCards[0]!.ref))}
                >
                  Show it <ArrowRight className="size-3" />
                </button>
              </>
            )}
          </div>
        )}
        {toast && (
          <div
            role="status"
            className="flex items-center gap-3 rounded-inset bg-foreground px-3 py-2 text-[13.5px] text-background shadow-lift"
          >
            <span className="min-w-0 flex-1">{toast.text}</span>
            {toast.undo && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void toast.undo?.()}
                className="inline-flex shrink-0 items-center gap-1 font-semibold text-background underline-offset-2 hover:underline"
              >
                <Undo2 className="size-3.5" /> Undo
              </button>
            )}
          </div>
        )}
        {error && (
          <p role="alert" className="text-[13px] text-destructive">
            {error}
          </p>
        )}
        <div className="flex items-center gap-3">
          <p aria-live="polite" className="min-w-0 flex-1 text-[13px] text-muted-foreground md:text-[14px]">
            {busy ?? dockText}
          </p>
          {open.length === 0 || (kept !== null && ready.length === 0) ? (
            <Button asChild size="lg">
              <Link href="/cards">
                See your cards <ArrowRight />
              </Link>
            </Button>
          ) : (
            <Button size="lg" disabled={ready.length === 0 || busy !== null} onClick={() => void confirm()}>
              <Check /> Yes, that&apos;s me
            </Button>
          )}
        </div>
      </div>

      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this file?</DialogTitle>
            <DialogDescription>
              This deletes your original file, what Plytos read from it, and anything you
              haven&apos;t kept. Cards you&apos;ve kept stay.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(false)}>
              Keep it
            </Button>
            <Button variant="destructive" disabled={busy !== null} onClick={() => void remove()}>
              Delete it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
