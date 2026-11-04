"use client";

// Step 3, "Approve": the proposed cards one at a time, strongest first, ten
// to a sitting. A card is made only when the person approves it; "Not now"
// keeps it as a draft in the import.

import {
  faArrowRight,
  faBell,
  faCheck,
  faLightbulb,
  faLock,
  faQuoteLeft,
  faRotate,
} from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { kindLabel, kindStyle, PageHead } from "../../../../components/hybrid";
import { Icon } from "../../../../components/icon";
import { KindPill, Segments, type Segment } from "../../../../components/import-parts";
import type { CardContent } from "../../../../lib/cards";
import {
  type Answer,
  BATCH_SIZE,
  cardPlace,
  contentFor,
  factRows,
  factsAbove,
  figureChoices,
  findingsForCard,
  highlight,
  isFigureQuestion,
  pathLabel,
  placementOpen,
  plural,
  type Proposal,
  type Review,
  reviewQueue,
  stateOf,
  wordingTips,
} from "../../../../lib/imports";
import { post } from "../client";
import { Editor } from "./editor";

type Busy = null | "approve" | "later" | "dropped" | "answer" | "place";

function figuresOf(content: CardContent): string[] {
  const figures = content.facts.figures;
  return Array.isArray(figures) ? figures : [];
}

function Facts({
  card,
  content,
  review,
}: {
  card: Proposal;
  content: CardContent;
  review: Review;
}) {
  const rows = factRows(card, content, factsAbove(card, review));
  if (rows.length === 0) return null;
  return (
    <div className="facts">
      <p className="facts-head">
        <Icon icon={faLock} size={10} />
        Facts · change only on purpose
      </p>
      <dl>
        {rows.map((row) => (
          <div key={row.key} className="fact-row">
            <dt>{row.label}</dt>
            <dd className={row.numbers ? "numbers" : undefined}>
              {row.value}
              {row.note && <span className="fact-note">{row.note}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// Where the card belongs, when the checks disagreed with the reading.
function PlaceQuestion({
  card,
  review,
  busy,
  onPlace,
}: {
  card: Proposal;
  review: Review;
  busy: boolean;
  onPlace: (parentRef: string | null) => void;
}) {
  const placement = card.placement;
  if (!placement) return null;
  const answered = card.ref in review.progress.moves;
  const chosen = review.progress.moves[card.ref] ?? null;
  const from = placement.choices.find((c) => c.parent_ref === placement.moved_from);
  return (
    <div className="stack tight">
      <p className="small-copy">
        <strong>{placement.question}</strong> {placement.reason}
        {from && ` Plytos moved it here from ${from.label}.`}
      </p>
      <div className="choice-row" role="group" aria-label={placement.question}>
        {placement.choices.map((choice) => {
          const pressed = answered && chosen === choice.parent_ref;
          return (
            <button
              key={choice.parent_ref ?? "top"}
              type="button"
              className="choice-pill"
              aria-pressed={pressed}
              disabled={busy}
              onClick={() => onPlace(choice.parent_ref)}
            >
              {pressed && <Icon icon={faCheck} size={11} />}
              {choice.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Checks({
  card,
  review,
  busy,
  onAnswer,
  onEdit,
  onPlace,
}: {
  card: Proposal;
  review: Review;
  busy: boolean;
  onAnswer: (finding: number, answer: Answer, value: string | null) => void;
  onEdit: () => void;
  onPlace: (parentRef: string | null) => void;
}) {
  const questions = findingsForCard(card, review).filter((i) => review.toSettle.includes(i));
  if (questions.length === 0 && card.needs_check.length === 0 && !card.placement) return null;
  return (
    <div className="needs-check">
      <p className="label orange">
        <Icon icon={faBell} size={11} />
        Needs your check
      </p>
      <PlaceQuestion card={card} review={review} busy={busy} onPlace={onPlace} />
      {questions.map((index) => {
        const finding = review.findings[index]!;
        const settled = review.progress.settled[String(index)];
        if (isFigureQuestion(finding)) {
          const figures = figureChoices(finding);
          return (
            <div key={index} className="stack tight">
              <p className="small-copy">
                Your resume gives this result two numbers: {figures.join(" and ")}. Which is right?
              </p>
              <div className="choice-row" role="group" aria-label="Pick the right number">
                {figures.map((figure) => {
                  const chosen = settled?.answer === "chosen" && settled.value === figure;
                  return (
                    <button
                      key={figure}
                      type="button"
                      className="choice-pill"
                      aria-pressed={chosen}
                      disabled={busy}
                      onClick={() => onAnswer(index, "chosen", figure)}
                    >
                      {chosen && <Icon icon={faCheck} size={11} />}
                      {figure}
                    </button>
                  );
                })}
                <button
                  type="button"
                  className="unsure"
                  aria-pressed={settled?.answer === "later"}
                  disabled={busy}
                  onClick={() => onAnswer(index, "later", null)}
                >
                  I&apos;m not sure
                </button>
              </div>
            </div>
          );
        }
        return (
          <div key={index} className="stack tight">
            <p className="small-copy">
              <strong>{finding.title}.</strong> {finding.detail}
            </p>
            <div className="choice-row" role="group" aria-label={finding.title}>
              <button
                type="button"
                className="choice-pill"
                aria-pressed={settled?.answer === "as_is"}
                disabled={busy}
                onClick={() => onAnswer(index, "as_is", null)}
              >
                {settled?.answer === "as_is" && <Icon icon={faCheck} size={11} />}
                It&apos;s right
              </button>
              <button
                type="button"
                className="choice-pill"
                aria-pressed={settled?.answer === "on_card"}
                disabled={busy}
                onClick={() => {
                  onAnswer(index, "on_card", null);
                  onEdit();
                }}
              >
                {settled?.answer === "on_card" && <Icon icon={faCheck} size={11} />}
                I&apos;ll fix it
              </button>
              <button
                type="button"
                className="unsure"
                aria-pressed={settled?.answer === "later"}
                disabled={busy}
                onClick={() => onAnswer(index, "later", null)}
              >
                I&apos;m not sure
              </button>
            </div>
          </div>
        );
      })}
      {card.needs_check.map((guess) => (
        <div key={guess} className="stack tight">
          <p className="small-copy">{guess}</p>
          <div className="choice-row">
            <button type="button" className="choice-pill" onClick={onEdit}>
              Check it in Edit wording
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function SourceCard({ card, content, id }: { card: Proposal; content: CardContent; id: string }) {
  const lines = card.source.slice(0, 3);
  if (lines.length === 0) return null;
  const figure = figuresOf(content)[0] ?? "";
  const page = lines[0]?.page;
  return (
    <section className="surface source-card" aria-label="Where this card came from">
      <p className="label blue">
        <Icon icon={faQuoteLeft} size={11} />
        Source trace
      </p>
      <p className="source-where">From your resume{page ? `, page ${page}` : ""}</p>
      {lines.map((line) => {
        const [before, hit, after] = figure ? highlight(line.text, figure) : [line.text, "", ""];
        return (
          <p key={line.block} className="source-quote">
            {before}
            {hit && <mark>{hit}</mark>}
            {after}
          </p>
        );
      })}
      <a
        className="text-button teal small self-start"
        href={`/import/${id}/original`}
        target="_blank"
        rel="noopener"
      >
        See in original
        <Icon icon={faArrowRight} size={12} />
      </a>
      <hr className="rule" />
      <p className="label ink">Proof: self-stated · 1 of 3 steps</p>
      <div className="proof-steps" aria-hidden="true">
        <span data-state="done" />
        <span />
        <span />
      </div>
      <p className="fine-print">Add a link or a photo later to make it stronger.</p>
    </section>
  );
}

export function ApproveFlow({ review: initial }: { review: Review }) {
  const [review, setReview] = useState(initial);
  const [batch, setBatch] = useState(() => reviewQueue(initial).slice(0, BATCH_SIZE));
  const [position, setPosition] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);

  useEffect(() => {
    if (!moved.current) return;
    window.scrollTo({ top: 0 });
    heading.current?.focus();
  }, [position, batch]);

  const approvedTotal = review.cards.filter(
    (c) => stateOf(c.ref, review.progress) === "approved",
  ).length;
  const ref = batch[position];
  const card = review.cards.find((c) => c.ref === ref);

  function next() {
    moved.current = true;
    setFlipped(false);
    setEditing(false);
    setError(null);
    setPosition((p) => p + 1);
  }

  async function act(action: "approve" | "later" | "dropped", content: CardContent | null = null) {
    if (!card) return;
    setBusy(action);
    setError(null);
    const body = action === "approve" ? { action, content } : { action };
    const outcome = await post(`/import/${review.id}/cards/${card.ref}`, body);
    setBusy(null);
    if (!outcome.ok) {
      setError(outcome.error);
      return;
    }
    setReview({ ...review, progress: outcome.progress });
    next();
  }

  async function moveTo(parentRef: string | null) {
    if (!card) return;
    setBusy("place");
    setError(null);
    const outcome = await post(`/import/${review.id}/cards/${card.ref}`, {
      action: "place",
      parent_ref: parentRef,
    });
    setBusy(null);
    if (!outcome.ok) {
      setError(outcome.error);
      return;
    }
    setReview({ ...review, progress: outcome.progress });
  }

  async function answer(finding: number, value: Answer, figure: string | null) {
    setBusy("answer");
    setError(null);
    const outcome = await post(`/import/${review.id}/answer`, {
      finding,
      answer: value,
      value: figure,
    });
    setBusy(null);
    if (!outcome.ok) {
      setError(outcome.error);
      return;
    }
    setReview({ ...review, progress: outcome.progress });
  }

  if (!card) {
    const left = reviewQueue(review);
    const approvedHere = batch.filter((r) => stateOf(r, review.progress) === "approved").length;
    return (
      <main className="page">
        <PageHead
          back={{
            href: `/import/${review.id}`,
            label: "Back to what we found",
          }}
          step={3}
        />
        <div className="stack tight">
          <h1 className="title" ref={heading} tabIndex={-1}>
            {batch.length === 0
              ? "No cards waiting."
              : approvedHere > 0
                ? `Nice work. ${plural(approvedHere, "card")} approved.`
                : "That's this set."}
          </h1>
          <p className="lede">
            {left.length > 0
              ? `${plural(left.length, "card is", "cards are")} still waiting. Keep going, or stop here and they'll wait for you.`
              : "That's every card from this resume. You'll find the ones you approved in your cards."}
          </p>
        </div>
        {batch.length > 0 && (
          <section className="stack tight" aria-label="This set">
            <Segments
              states={batch.map((r) => {
                const s = stateOf(r, review.progress);
                return s === "approved" ? "done" : s === "pending" ? "pending" : "later";
              })}
            />
            <p className="label medium">
              {approvedHere} approved ·{" "}
              {batch.filter((r) => stateOf(r, review.progress) === "later").length} for later ·{" "}
              {batch.filter((r) => stateOf(r, review.progress) === "dropped").length} left out
            </p>
          </section>
        )}
        <div className="dock">
          {left.length > 0 ? (
            <>
              <button
                className="button primary"
                type="button"
                onClick={() => {
                  moved.current = true;
                  setBatch(left.slice(0, BATCH_SIZE));
                  setPosition(0);
                }}
              >
                Review {Math.min(BATCH_SIZE, left.length)} more
                <Icon icon={faArrowRight} size={16} />
              </button>
              <Link className="text-button" href="/cards">
                Stop here and see your cards
              </Link>
            </>
          ) : (
            <Link className="button primary" href="/cards">
              See your cards
              <Icon icon={faArrowRight} size={16} />
            </Link>
          )}
        </div>
      </main>
    );
  }

  const content = contentFor(card, review.progress);
  const unplaced = placementOpen(card, review.progress);
  const style = kindStyle(card.kind);
  const place = cardPlace(content, factsAbove(card, review));
  const path = pathLabel(card, review);
  const tips = wordingTips(card, review).slice(0, 2);
  const segments: Segment[] = batch.map((r, i) => {
    if (i === position) return "current";
    if (i > position) return "pending";
    const s = stateOf(r, review.progress);
    return s === "approved" ? "done" : "later";
  });

  return (
    <main className="page wide">
      <PageHead
        back={{ href: `/import/${review.id}`, label: "Back to what we found" }}
        step={3}
        progress={position / batch.length}
      />
      <div className="stack tight">
        <h1 className="title compact">Review your cards, one at a time</h1>
        <p className="lede">Nothing goes on your cards until you say so.</p>
      </div>

      <div className="stack tight">
        <div className="row">
          <p className="label ink wide-track">
            Card {position + 1} of {batch.length}
          </p>
          <p className="label teal">{approvedTotal} approved so far</p>
        </div>
        <Segments states={segments} />
      </div>

      <div className="split">
        <div className="split-main">
          <div className="hero-stack">
            <article className={`hero kind-${style}`} aria-labelledby="card-headline">
              <div className="row">
                <KindPill kind={card.kind} content={content} />
                <button
                  type="button"
                  className="flip-button"
                  aria-pressed={flipped}
                  onClick={() => setFlipped(!flipped)}
                >
                  <Icon icon={faRotate} size={11} />
                  {flipped ? "Flip to the front" : "Flip to see it in full"}
                </button>
              </div>
              <p className="label small">{flipped ? "Back · in full" : "Front · how it's told"}</p>
              {path && <p className="hero-path">Under {path}</p>}
              <h2
                id="card-headline"
                className={`hero-headline${content.framing.headline.length > 110 ? " long" : ""}`}
                ref={heading}
                tabIndex={-1}
              >
                {content.framing.headline}
              </h2>
              {!flipped && (
                <>
                  <p className="hero-meta">
                    {[kindLabel(card.kind, content.facts), place].filter(Boolean).join(" · ")}
                  </p>
                  <Facts card={card} content={content} review={review} />
                </>
              )}
              {flipped && (
                <p className="hero-body">
                  {content.framing.body ||
                    "Nothing more than the headline yet. Add more with Edit wording."}
                </p>
              )}
              <Checks
                card={card}
                review={review}
                busy={busy !== null}
                onAnswer={(finding, value, figure) => void answer(finding, value, figure)}
                onEdit={() => setEditing(true)}
                onPlace={(parentRef) => void moveTo(parentRef)}
              />
            </article>
          </div>
        </div>
        <aside className="split-side stack">
          <SourceCard card={card} content={content} id={review.id} />
          {tips.map((index) => {
            const finding = review.findings[index]!;
            return (
              <p key={index} className="tip">
                <span className="tip-icon">
                  <Icon icon={faLightbulb} size={12} />
                </span>
                <span>
                  <strong>{finding.title}.</strong> {finding.detail}
                </span>
              </p>
            );
          })}
        </aside>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <div className="dock">
        <button
          className={`button primary${busy === "approve" ? " busy" : ""}`}
          type="button"
          disabled={busy !== null || unplaced}
          onClick={() => void act("approve")}
        >
          <Icon icon={faCheck} size={16} />
          {busy === "approve" ? "Approving…" : "Approve"}
        </button>
        {unplaced && <p className="note">Say where this belongs first.</p>}
        <div className="dock-row">
          <button
            className="button outline"
            type="button"
            disabled={busy !== null}
            onClick={() => setEditing(true)}
          >
            Edit wording
          </button>
          <button
            className="text-button"
            type="button"
            disabled={busy !== null}
            onClick={() => void act("later")}
          >
            {busy === "later" ? "Saving…" : "Not now"}
          </button>
        </div>
        <p className="note">Skip a card and it stays a draft. Nothing is deleted.</p>
      </div>

      {editing && (
        <Editor
          key={card.ref}
          content={content}
          busy={busy !== null}
          error={error}
          onCancel={() => setEditing(false)}
          onSave={(edited) => void act("approve", edited)}
          onLeaveOut={() => void act("dropped")}
        />
      )}
    </main>
  );
}
