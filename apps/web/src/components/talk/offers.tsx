"use client";

import { Check, FileText, Pencil } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Paper } from "@/components/resume/paper";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { HEADLINE_MAX } from "@/lib/cards";
import type { ImportSummary } from "@/lib/imports";
import { proposalSize, type ProposedResume, type ResumeDetail } from "@/lib/resumes";
import { monthLabel, type Proposal, resumeProgress, withWording } from "@/lib/talk";
import { cn } from "@/lib/utils";

import { useMakeResume } from "./make-resume";
import { send } from "./send";

function Problem({ children }: { children: string | null }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-[13px] text-destructive">
      {children}
    </p>
  );
}

function Kind({ children, done }: { children: string; done?: string }) {
  return (
    <p className="flex items-center justify-between gap-3 text-[12px] font-semibold tracking-[0.04em] text-muted-foreground uppercase">
      <span>{children}</span>
      {done && (
        <span className="flex items-center gap-1 text-primary normal-case tracking-normal">
          <Check className="size-3.5" strokeWidth={2.6} />
          {done}
        </span>
      )}
    </p>
  );
}

const OFFER = "flex w-full max-w-[92%] flex-col gap-3 rounded-2xl border bg-card p-4 shadow-card sm:max-w-[85%]";

/** A win the Stitcher joined from the person's notes. Nothing is a card until
 * they keep it, as it is or in their words. */
export function WinOffer({
  proposal,
  onDecided,
}: {
  proposal: Proposal;
  onDecided: (p: Proposal) => void;
}) {
  const card = proposal.body.card!;
  const framing = card.content.framing;
  const [editing, setEditing] = useState(false);
  const [headline, setHeadline] = useState(framing.headline);
  const [body, setBody] = useState(framing.body);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The wording the person kept, when they edited it here. After a reload the
  // card itself holds it, so the thread just says it was kept in their words.
  const [keptWording, setKeptWording] = useState<string | null>(null);
  const date = card.content.facts.date;
  const figures = card.content.facts.figures;

  async function decide(decision: "keep" | "dismiss", content: unknown = null) {
    setBusy(true);
    setError(null);
    const url = `/talk/proposals/${proposal.id}/${decision}`;
    const result =
      decision === "keep"
        ? await send<{ proposal: Proposal }>(url, { content })
        : await send<Proposal>(url, {});
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if (content !== null) {
      setKeptWording(headline.trim());
      setEditing(false);
    }
    onDecided("proposal" in result.data ? result.data.proposal : (result.data as Proposal));
  }

  if (proposal.state !== "open") {
    const shown = proposal.state === "kept" ? framing.headline : keptWording;
    return (
      <article aria-label="Kept win" className={cn(OFFER, "gap-2")}>
        <Kind done="In your cards">{proposal.state === "kept" ? "Kept" : "Kept in your words"}</Kind>
        {shown && <h3 className="text-[16px] leading-snug font-semibold">{shown}</h3>}
        <Link href="/cards" className="text-[14px] font-medium text-primary">
          See it in your cards
        </Link>
      </article>
    );
  }
  const wording = headline.trim();
  return (
    <article aria-label="Suggested win" className={OFFER}>
      <Kind>{`Win${proposal.cites.length > 1 ? ` · from ${proposal.cites.length} notes` : ""}`}</Kind>
      {editing ? (
        <div className="flex flex-col gap-2">
          <label className="text-[12px] font-medium text-muted-foreground" htmlFor={`h-${proposal.id}`}>
            Headline
          </label>
          <Textarea
            id={`h-${proposal.id}`}
            value={headline}
            maxLength={HEADLINE_MAX}
            rows={3}
            onChange={(e) => setHeadline(e.target.value)}
          />
          <label className="text-[12px] font-medium text-muted-foreground" htmlFor={`b-${proposal.id}`}>
            More context (optional)
          </label>
          <Textarea id={`b-${proposal.id}`} value={body} rows={2} onChange={(e) => setBody(e.target.value)} />
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <h3 className="text-[17px] leading-snug font-semibold tracking-[-0.01em]">{framing.headline}</h3>
          {framing.body && <p className="text-[14px] text-muted-foreground">{framing.body}</p>}
        </div>
      )}
      {(typeof date === "string" || Array.isArray(figures)) && !editing && (
        <p className="flex flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground">
          {typeof date === "string" && <span>{monthLabel(date)}</span>}
          {Array.isArray(figures) &&
            figures.map((f) => (
              <span key={f} className="rounded-full bg-accent px-2 py-0.5 font-medium text-accent-foreground tabular-nums">
                {f}
              </span>
            ))}
        </p>
      )}
      {card.missing && !editing && (
        <p className="rounded-xl bg-live-soft px-3 py-2 text-[14px]">
          <b className="font-semibold">Still open:</b> {card.missing}{" "}
          <span className="text-muted-foreground">Answer below and I&apos;ll add it.</span>
        </p>
      )}
      <Problem>{error}</Problem>
      {editing ? (
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={busy || !wording}
            onClick={() => decide("keep", withWording(card, headline, body))}
          >
            Keep my wording
          </Button>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => {
              setEditing(false);
              setHeadline(framing.headline);
              setBody(framing.body);
            }}
          >
            Cancel
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => decide("keep")}>
            Keep it
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => setEditing(true)}>
            <Pencil />
            Edit
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => decide("dismiss")}>
            Not this
          </Button>
        </div>
      )}
    </article>
  );
}

/** A version of a resume the Assembler put together for a target. The person
 * can read it as it would read before keeping it. */
export function ResumeOffer({
  proposal,
  onDecided,
}: {
  proposal: Proposal;
  onDecided: (p: Proposal) => void;
}) {
  const resume = proposal.body.resume!;
  const [preview, setPreview] = useState<ProposedResume | null>(null);
  const [showing, setShowing] = useState(false);
  const [kept, setKept] = useState<ResumeDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = `/talk/proposals/${proposal.id}`;

  async function show() {
    if (showing) {
      setShowing(false);
      return;
    }
    if (!preview) {
      setBusy(true);
      setError(null);
      const result = await send<ProposedResume>(`${url}/resume`);
      setBusy(false);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setPreview(result.data);
    }
    setShowing(true);
  }

  async function decide(decision: "keep-resume" | "dismiss") {
    setBusy(true);
    setError(null);
    const result =
      decision === "keep-resume"
        ? await send<{ proposal: Proposal; resume: ResumeDetail }>(`${url}/${decision}`, {})
        : await send<Proposal>(`${url}/${decision}`, {});
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if ("resume" in result.data) {
      setKept(result.data.resume);
      onDecided(result.data.proposal);
    } else {
      onDecided(result.data as Proposal);
    }
  }

  if (proposal.state !== "open") {
    const href = kept ? `/resumes/${encodeURIComponent(kept.id)}` : "/resumes";
    return (
      <article aria-label="Kept resume" className={cn(OFFER, "gap-2")}>
        <Kind done="Kept">Resume version</Kind>
        <h3 className="text-[16px] leading-snug font-semibold">{resume.name}</h3>
        <Link href={href} className="text-[14px] font-medium text-primary">
          {kept ? "Open it" : "See it in your resumes"}
        </Link>
      </article>
    );
  }
  return (
    <div className="flex w-full flex-col gap-3">
      <article aria-label="Suggested resume" className={OFFER}>
        <Kind>{`Resume version · for ${resume.target}`}</Kind>
        <div className="flex flex-col gap-1">
          <h3 className="text-[17px] leading-snug font-semibold tracking-[-0.01em]">{resume.name}</h3>
          <p className="text-[13px] text-muted-foreground">{proposalSize(resume)}</p>
        </div>
        {showing && preview?.parent_name && (
          <p className="text-[14px] text-muted-foreground">
            Made from {preview.parent_name}. Lines worded for this version are marked.
          </p>
        )}
        <Problem>{error}</Problem>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => decide("keep-resume")}>
            Keep it
          </Button>
          <Button variant="outline" disabled={busy} onClick={show} aria-expanded={showing}>
            {showing ? "Hide it" : "Read it"}
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => decide("dismiss")}>
            Not now
          </Button>
        </div>
      </article>
      {showing && preview && (
        <div className="w-full">
          <Paper page={preview.page} />
        </div>
      )}
    </div>
  );
}

/** A suggestion the person passed on, or one a fuller draft replaced. */
export function Settled({ proposal }: { proposal: Proposal }) {
  const headline = proposal.body.card?.content.framing.headline ?? proposal.body.message;
  return (
    <p className="px-9 text-[13px] text-muted-foreground">
      {proposal.state === "dismissed" ? "You passed on " : "Replaced by a fuller draft: "}
      <span className="line-through decoration-muted-foreground/40">{headline}</span>
    </p>
  );
}

/** A resume shared in the conversation: what was read, and where it stands. */
export function SharedResume({
  resume,
  reviewing,
  resumeId,
  onGoThrough,
}: {
  resume: ImportSummary;
  // Whether it's being gone through further down the conversation.
  reviewing: boolean;
  // The resume made from it, if one was.
  resumeId: string | null;
  onGoThrough: (setAside: boolean) => void;
}) {
  const id = encodeURIComponent(resume.id);
  const pending = resume.cards - resume.approved - resume.dropped - resume.later;
  const making = useMakeResume(resume.id);
  // Everything's decided and some of it was kept, but no resume was made yet.
  const canMake =
    resume.state === "read" && !reviewing && !resumeId && pending === 0 && resume.approved > 0;
  return (
    <article
      aria-label="Your resume"
      className="flex w-full max-w-[92%] flex-col gap-2 rounded-2xl border bg-card p-4 shadow-card sm:max-w-[85%]"
    >
      <p className="flex items-center gap-2 text-[14px] font-semibold">
        <FileText className="size-4 shrink-0 text-primary" />
        <span className="truncate">{resume.file.name}</span>
      </p>
      <p className="text-[13px] text-muted-foreground">{resumeProgress(resume)}</p>
      <div className="flex flex-wrap gap-2 pt-1">
        {resume.state === "read" && reviewing && (
          <p className="text-[13px] font-medium text-primary">We&apos;re going through it below.</p>
        )}
        {resume.state === "read" && !reviewing && pending > 0 && (
          <Button size="sm" onClick={() => onGoThrough(false)}>
            Go through it
          </Button>
        )}
        {canMake && (
          <Button size="sm" disabled={making.busy} onClick={making.make}>
            {making.busy ? "Setting it up…" : "Make my resume"}
          </Button>
        )}
        {resume.state === "read" && !reviewing && pending === 0 && (resume.later > 0 || resume.to_settle > 0) && (
          <Button size="sm" variant="outline" onClick={() => onGoThrough(true)}>
            {resume.later > 0 && resume.to_settle > 0
              ? "Go back to what's set aside"
              : resume.later > 0
                ? `Go through the ${resume.later} set aside`
                : resume.to_settle === 1
                  ? "Answer the question left"
                  : `Answer the ${resume.to_settle} questions left`}
          </Button>
        )}
        {resumeId && (
          <Button size="sm" variant={pending > 0 ? "outline" : "default"} asChild>
            <Link href={`/resumes/${encodeURIComponent(resumeId)}`}>Open my resume</Link>
          </Button>
        )}
        <Button size="sm" variant="ghost" asChild>
          <Link href={`/import/${id}`}>
            {resume.state === "failed" ? "See what went wrong" : resume.state === "reading" ? "See how it's going" : "See what I read"}
          </Link>
        </Button>
      </div>
      <Problem>{making.error}</Problem>
    </article>
  );
}
