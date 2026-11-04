"use client";

// The Reading screen: shows the resume being read, then lists what was found
// one line at a time. The counts are the real ones from the import.

import { faArrowRight, faCheck, faCircleInfo, faPlus } from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHead, SketchCard } from "../../components/hybrid";
import { Icon } from "../../components/icon";
import { FileCard, fileDetail, formatSize, MiniCard } from "../../components/import-parts";
import {
  FOUND_LABELS,
  type FoundRow,
  foundRows,
  factsAbove,
  foundSoFar,
  plural,
  type Review,
} from "../../lib/imports";

const STEP_MS = 380;

function prefersLessMotion(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function Reading({
  name,
  size,
  review,
  error,
  onRetry,
}: {
  name: string;
  size: number;
  review: Review | null;
  error: string | null;
  onRetry: () => void;
}) {
  const rows = review ? foundRows(review) : null;
  const total = rows?.length ?? FOUND_LABELS.length;
  // While the server reads, the bar creeps toward 60%. Once it answers, each
  // line of what was found ticks off in turn.
  const [waiting, setWaiting] = useState(4);
  const [ticked, setTicked] = useState(0);
  const [lessMotion] = useState(prefersLessMotion);

  useEffect(() => {
    if (review || error) return;
    const timer = window.setInterval(() => setWaiting((p) => p + (60 - p) * 0.06), 200);
    return () => window.clearInterval(timer);
  }, [review, error]);

  useEffect(() => {
    if (!review || lessMotion) return;
    const timer = window.setInterval(() => {
      setTicked((n) => {
        if (n + 1 >= total) window.clearInterval(timer);
        return Math.min(total, n + 1);
      });
    }, STEP_MS);
    return () => window.clearInterval(timer);
  }, [review, total, lessMotion]);

  const revealed = review && lessMotion ? total : ticked;
  const done = review !== null && revealed >= total;
  const percent = review ? Math.round(60 + (40 * revealed) / total) : Math.round(waiting);
  const shown = review ? foundSoFar(review).slice(0, done ? 4 : Math.max(0, revealed - 2)) : [];

  if (error) {
    return (
      <main className="page">
        <PageHead back={{ onClick: onRetry, label: "Back" }} step={1} />
        <FileCard name={name} detail={`${formatSize(size)} · not saved`} href={null} />
        <div className="stack tight">
          <h1 className="title">That one didn&apos;t come through.</h1>
          <p className="lede">Nothing was saved, and no cards were made.</p>
        </div>
        <p className="alert" role="alert">
          {error}
        </p>
        <div className="dock">
          <button className="button primary" type="button" onClick={onRetry}>
            Try another way
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="page">
      <PageHead step={2} progress={percent / 100} />
      <FileCard
        name={review?.file.name ?? name}
        detail={review ? fileDetail(review.file) : `${formatSize(size)} · kept private`}
        href={review ? `/import/${review.id}/original` : null}
      />
      <div className="stack tight">
        <h1 className="title">
          {done
            ? "Here's what we lifted out."
            : "Reading it through. Nothing is saved as a card yet."}
        </h1>
        <p className="lede">
          {done
            ? "Nothing is a card yet. Next, check what we found, then approve the cards you want."
            : "This usually takes under a minute."}
        </p>
      </div>

      <section className="sand-panel reading-panel" aria-label="Reading progress">
        <div className={`lift-art${done ? " still" : ""}`} aria-hidden="true">
          <div className="lift-page">
            {[92, 70, 84, 56, 88, 64, 76].map((w, i) => (
              <span key={i} className="lift-line" style={{ width: `${w}%` }} />
            ))}
          </div>
          <span className="lift-arrow">
            <Icon icon={faArrowRight} size={12} />
          </span>
          <div className="lift-cards">
            <SketchCard kind="role" label="Role" lines={[100, 60]} className="lift-card c1" />
            <SketchCard kind="result" label="Result" lines={[100, 60]} className="lift-card c2" />
            <SketchCard kind="skill" label="Skill" lines={[100, 60]} className="lift-card c3" />
          </div>
        </div>
        <p className="start-art-caption">
          <span className="plus-dot">
            <Icon icon={faPlus} size={10} />
          </span>
          <span className="label medium">Lifting lines onto cards</span>
        </p>
        <div className="reading-meter">
          <div className="row">
            <span className="label ink">{done ? "Read" : "Reading"}</span>
            <span className="meter-figure" aria-live="polite">
              {percent}%
            </span>
          </div>
          <span className="meter-track">
            <span className="meter-fill" style={{ width: `${percent}%` }} />
          </span>
          <span className="label small medium">
            {Math.min(revealed, total)} of {total} checks complete
          </span>
        </div>
      </section>

      <section className="surface top-bar found" style={{ ["--bar" as string]: "var(--teal)" }}>
        <div className="row found-head">
          <h2 className="label">What we&apos;ve found</h2>
          <span className="label medium">
            {Math.min(revealed, total)} of {total} done
          </span>
        </div>
        <ul className="found-rows" aria-live="polite">
          {(rows ?? FOUND_LABELS.map((label): FoundRow => ({ label, count: null }))).map(
            (row, i) => {
              const state =
                review && i < revealed
                  ? "done"
                  : i === (review ? revealed : 0)
                    ? "working"
                    : "pending";
              return (
                <li key={row.label} className="found-row" data-state={state}>
                  <span className="found-mark">
                    {state === "done" && <Icon icon={faCheck} size={10} />}
                  </span>
                  <span className="found-text">
                    <span className="found-label">{row.label}</span>
                    {row.detail && state === "done" && (
                      <span className="found-detail">{row.detail}</span>
                    )}
                  </span>
                  {state === "done" &&
                    (row.count === null ? (
                      <span className="label teal">Done</span>
                    ) : (
                      <span className="count-pill">{row.count} found</span>
                    ))}
                  {state === "working" && <span className="label orange">In progress</span>}
                </li>
              );
            },
          )}
        </ul>
      </section>

      <section className="sand-panel stack tight">
        <div className="row start">
          <span className="circle-icon">
            <Icon icon={faCircleInfo} size={12} />
          </span>
          <h2 className="panel-title">Why this takes a moment</h2>
        </div>
        <p className="small-copy">
          We only read what&apos;s on the page. We won&apos;t add anything that isn&apos;t there.
        </p>
      </section>

      {review && shown.length > 0 && (
        <section className="stack">
          <div className="row">
            <h2 className="label">Found so far</h2>
            <span className="label medium">
              Showing {shown.length} of {review.cards.length}
            </span>
          </div>
          <div className="mini-grid">
            {shown.map((card) => (
              <MiniCard
                key={card.ref}
                card={card}
                content={card.content}
                above={review ? factsAbove(card, review) : undefined}
              />
            ))}
          </div>
        </section>
      )}

      <div className="dock">
        {done && review ? (
          <Link className="button primary" href={`/import/${review.id}`}>
            See what we found
            <Icon icon={faArrowRight} size={16} />
          </Link>
        ) : (
          <button className="button" type="button" disabled>
            Almost ready
            <Icon icon={faArrowRight} size={16} />
          </button>
        )}
        <p className="note">
          {review
            ? `${plural(review.cards.length, "thing")} found. Nothing is a card until you say yes.`
            : "Nothing is a card until you say yes."}
        </p>
      </div>
    </main>
  );
}
