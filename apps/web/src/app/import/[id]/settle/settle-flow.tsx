"use client";

// Settling what doesn't line up: one question open at a time, each answered
// in a tap. Picking a number fixes it on every card that uses it; nothing
// changes the person's original file.

import {
  faArrowRight,
  faCheck,
  faChevronDown,
  faChevronUp,
  faCircleCheck,
  faFileLines,
  faHouse,
  faLock,
  faPenNib,
} from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { PageHead } from "../../../../components/hybrid";
import { Icon } from "../../../../components/icon";
import { FannedCards, Segments, type Segment } from "../../../../components/import-parts";
import {
  type Answer,
  figureChoices,
  type Finding,
  highlight,
  isFigureQuestion,
  lineLabel,
  overview,
  plural,
  type Review,
  settledCount,
  settleState,
} from "../../../../lib/imports";
import { post } from "../client";

type Choice = { answer: Answer; value: string | null };
type Option = Choice & { label: string; detail: string };

function question(finding: Finding): string {
  if (isFigureQuestion(finding)) return "These can't both be right. Which one is true?";
  if (finding.rule === "dates.gap") return "Is this gap right?";
  if (finding.rule === "dates.overlap") return "Is this overlap right?";
  if (finding.rule === "content.duplicates") return "Are these the same thing?";
  if (finding.rule.startsWith("dates.")) return "Are these dates right?";
  return "Is this right?";
}

function options(finding: Finding): Option[] {
  const later: Option = {
    answer: "later",
    value: null,
    label: "I'm not sure, flag it for later",
    detail: "No pressure. We'll hold this one.",
  };
  if (isFigureQuestion(finding)) {
    return [
      ...figureChoices(finding).map((figure) => ({
        answer: "chosen" as const,
        value: figure,
        label: `It was ${figure}`,
        detail: "Use this on every card that mentions it.",
      })),
      later,
    ];
  }
  if (finding.rule === "content.duplicates") {
    return [
      {
        answer: "as_is",
        value: null,
        label: "They're different, keep both",
        detail: "Each one stays its own card.",
      },
      {
        answer: "on_card",
        value: null,
        label: "I'll sort it out when I approve",
        detail: "Leave out the repeat, or reword it.",
      },
      later,
    ];
  }
  return [
    {
      answer: "as_is",
      value: null,
      label: "It's right as it is",
      detail: "Keep it the way your resume has it.",
    },
    {
      answer: "on_card",
      value: null,
      label: "I'll fix it on the card",
      detail: "You can change the facts when you approve it.",
    },
    later,
  ];
}

function submitLabel(choice: Choice | undefined): string {
  if (!choice) return "Pick one to continue";
  if (choice.answer === "chosen") return `Use ${choice.value} and continue`;
  if (choice.answer === "as_is") return "Keep it and continue";
  if (choice.answer === "on_card") return "Save and continue";
  return "Flag it and continue";
}

const QUOTE_COLORS = ["var(--orange)", "var(--blue)", "var(--teal)", "var(--ink-55)"];

function SourceTrace({ review, finding }: { review: Review; finding: Finding }) {
  const figures = isFigureQuestion(finding);
  const quotes = finding.locations.filter((loc) => loc.excerpt);
  if (quotes.length === 0) return null;
  return (
    <div className="trace">
      <p className="trace-head">
        <Icon icon={faFileLines} size={11} />
        Source trace · from your resume
      </p>
      {quotes.map((loc, i) => {
        const [before, hit, after] = loc.figure
          ? highlight(loc.excerpt, loc.figure)
          : [loc.excerpt, "", ""];
        return (
          <div key={i}>
            {i > 0 && <p className="trace-vs">{figures ? "vs" : "and"}</p>}
            <figure className="trace-quote" style={{ ["--quote" as string]: QUOTE_COLORS[i % 4] }}>
              <figcaption className="trace-where">
                {i === 0 ? "" : figures ? "Further down · " : ""}
                {lineLabel(review, loc.block)}
              </figcaption>
              <blockquote>
                {before}
                {hit && <mark>{hit}</mark>}
                {after}
              </blockquote>
            </figure>
          </div>
        );
      })}
    </div>
  );
}

export function SettleFlow({ review: initial }: { review: Review }) {
  const [review, setReview] = useState(initial);
  const items = review.toSettle;
  const total = items.length;
  const [expanded, setExpanded] = useState<number | null>(
    () => items.find((i) => settleState(i, initial.progress) === "open") ?? null,
  );
  const [choices, setChoices] = useState<Record<number, Choice>>(() => {
    const out: Record<number, Choice> = {};
    for (const i of items) {
      const s = initial.progress.settled[String(i)];
      if (s) out[i] = { answer: s.answer, value: s.value };
    }
    return out;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const openRef = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);

  useEffect(() => {
    if (!moved.current) return;
    openRef.current?.focus();
    openRef.current?.closest("section")?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [expanded]);

  const settled = settledCount(review);
  const open = items.filter((i) => settleState(i, review.progress) !== "settled").length;
  const waiting = overview(review).pending;
  const segments: Segment[] = items.map((i) =>
    i === expanded
      ? "current"
      : settleState(i, review.progress) === "settled"
        ? "done"
        : settleState(i, review.progress) === "later"
          ? "later"
          : "pending",
  );

  function expand(index: number | null) {
    moved.current = true;
    setError(null);
    setExpanded(index);
  }

  async function submit(index: number) {
    const choice = choices[index];
    if (!choice) return;
    setBusy(true);
    setError(null);
    const outcome = await post(`/import/${review.id}/answer`, {
      finding: index,
      ...choice,
    });
    setBusy(false);
    if (!outcome.ok) {
      setError(outcome.error);
      return;
    }
    const progress = outcome.progress;
    const changed = progress.settled[String(index)]?.changed.length ?? 0;
    setReview({ ...review, progress });
    setStatus(
      choice.answer === "chosen"
        ? `Used ${choice.value}${changed > 0 ? ` on ${plural(changed, "card")}` : ""}.`
        : choice.answer === "later"
          ? "Flagged for later."
          : "Saved.",
    );
    const after = [
      ...items.slice(items.indexOf(index) + 1),
      ...items.slice(0, items.indexOf(index)),
    ];
    expand(after.find((i) => settleState(i, progress) === "open") ?? null);
  }

  return (
    <main className="page">
      <PageHead
        back={{ href: `/import/${review.id}`, label: "Back to what we found" }}
        step={2}
        progress={total > 0 ? settled / total : 1}
      />
      <div className="stack tight">
        <h1 className="title">
          {total === 0 ? "Everything lines up." : "A few things don't line up."}
        </h1>
        <p className="lede">
          {total === 0
            ? "There's nothing to settle. Your cards are ready to review."
            : "That's normal with older resumes. Settle each one in a tap. Nothing changes your original file."}
        </p>
      </div>

      {total > 0 && (
        <section className="sand-panel stack settle-summary" aria-label="Progress">
          <div className="row">
            <div className="stack tight">
              <p className="label">Step 2 · Check</p>
              <p className="summary-count">
                {settled} of {total} settled
              </p>
            </div>
            <div className="waiting">
              <FannedCards size="small" />
              <span className="badge">{waiting}</span>
              <span className="label small">{plural(waiting, "card")} waiting</span>
            </div>
          </div>
          <Segments states={segments} />
          <p className="row start small-copy">
            <Icon icon={faCircleCheck} size={14} className="teal" />
            Your original resume is kept untouched.
          </p>
        </section>
      )}

      <p className="visually-hidden" role="status">
        {status}
      </p>

      {total > 0 && (
        <section className="stack" aria-labelledby="to-settle">
          <h2 className="label" id="to-settle">
            {plural(total, "thing")} to settle
          </h2>
          {items.map((index, position) => {
            const finding = review.findings[index]!;
            const state = settleState(index, review.progress);
            if (index !== expanded) {
              return (
                <button
                  key={index}
                  type="button"
                  className="surface top-bar settle-item"
                  data-state={state}
                  aria-expanded={false}
                  onClick={() => expand(index)}
                >
                  <span className="settle-item-text">
                    {state === "settled" ? (
                      <span className="pill small outline-teal">
                        <Icon icon={faCheck} size={8} />
                        Settled
                        {review.progress.settled[String(index)]?.value
                          ? ` · ${review.progress.settled[String(index)]?.value}`
                          : ""}
                      </span>
                    ) : state === "later" ? (
                      <span className="pill small sand">Later</span>
                    ) : (
                      <span className="pill small amber">Needs you</span>
                    )}
                    <span className="settle-item-title">{finding.title}</span>
                    <span className="settle-item-detail">{finding.detail}</span>
                  </span>
                  <span className="settle-item-go">
                    <Icon icon={faArrowRight} size={14} />
                  </span>
                </button>
              );
            }
            const choice = choices[index];
            const isFigure = isFigureQuestion(finding);
            return (
              <section key={index} className="surface settle-open" aria-labelledby={`q-${index}`}>
                <div className="row">
                  <span className="pill small amber">Needs your eye</span>
                  <button
                    type="button"
                    className="round-button plain"
                    onClick={() => expand(null)}
                    aria-label="Close this item"
                  >
                    <Icon icon={faChevronUp} size={14} />
                  </button>
                </div>
                <p className="label">
                  Item {position + 1} of {total}
                </p>
                <h2 className="item-title" id={`q-${index}`} ref={openRef} tabIndex={-1}>
                  {finding.title}
                </h2>
                <p className="small-copy muted">{finding.detail}</p>
                <SourceTrace review={review} finding={finding} />
                <fieldset className="options">
                  <legend className="question">{question(finding)}</legend>
                  {options(finding).map((option) => {
                    const selected =
                      choice?.answer === option.answer && choice.value === option.value;
                    return (
                      <label
                        key={`${option.answer}-${option.value}`}
                        className="option"
                        data-selected={selected}
                      >
                        <input
                          type="radio"
                          name={`q-${index}-answer`}
                          checked={selected}
                          onChange={() =>
                            setChoices({
                              ...choices,
                              [index]: {
                                answer: option.answer,
                                value: option.value,
                              },
                            })
                          }
                        />
                        <span className="option-mark" aria-hidden="true">
                          {selected && <Icon icon={faCheck} size={11} />}
                        </span>
                        <span className="option-text">
                          <span className="option-label">
                            {option.label}
                            {selected && option.answer === "chosen" && " (use this)"}
                          </span>
                          <span className="option-detail">{option.detail}</span>
                        </span>
                      </label>
                    );
                  })}
                </fieldset>
                {isFigure && (
                  <div className="info-box">
                    <div className="info-row">
                      <span className="circle-icon">
                        <Icon icon={faLock} size={11} />
                      </span>
                      <span>
                        <span className="label small">Fact · locked</span>
                        <span className="info-value">
                          {choice?.answer === "chosen"
                            ? `${choice.value} on your cards`
                            : "Pick the number you can back up"}
                        </span>
                      </span>
                    </div>
                    <div className="info-row">
                      <span className="circle-icon">
                        <Icon icon={faPenNib} size={11} />
                      </span>
                      <span>
                        <span className="label small">Wording · plain words</span>
                        <span className="info-value light">Yours to reword any time.</span>
                      </span>
                    </div>
                  </div>
                )}
                <p className="fine-print">
                  {isFigure
                    ? "Picking one fixes the fact on the card. Facts stay locked and only change when you choose to change them."
                    : "Your answer is saved with this import. You can change it any time before you approve the card."}
                </p>
                {error && (
                  <p className="alert" role="alert">
                    {error}
                  </p>
                )}
                <button
                  type="button"
                  className="button primary square"
                  disabled={!choice || busy}
                  onClick={() => void submit(index)}
                >
                  {busy ? "Saving…" : submitLabel(choice)}
                </button>
              </section>
            );
          })}
          {expanded === null && open > 0 && (
            <button
              type="button"
              className="text-button teal self-start"
              onClick={() =>
                expand(items.find((i) => settleState(i, review.progress) !== "settled") ?? null)
              }
            >
              <Icon icon={faChevronDown} size={12} />
              Open the next one
            </button>
          )}
        </section>
      )}

      <div className="dock sheet">
        <Link className="button primary" href={`/import/${review.id}/approve`}>
          Continue to review cards
          <Icon icon={faArrowRight} size={16} />
        </Link>
        <p className="label small">
          {open > 0
            ? `${plural(open, "item")} left · you can still continue`
            : "Everything is settled"}
        </p>
        {open > 0 && (
          <>
            <Link className="text-button" href="/cards">
              Come back to the rest later
            </Link>
            <p className="note">
              <Icon icon={faHouse} size={11} />
              Unsettled items wait for you in this import.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
