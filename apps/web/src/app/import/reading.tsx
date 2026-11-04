"use client";

// The Reading screen. The resume is kept as soon as it arrives and read in the
// background, so this screen follows the reading: it asks where it is every
// second or two and shows the real stage. Once it's read, each line of what
// was found ticks off in turn. The person can leave and come back; the import's
// own page shows this screen until the reading is done.

import { faArrowRight, faCheck, faCircleInfo, faPlus } from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHead, SketchCard } from "../../components/hybrid";
import { Icon } from "../../components/icon";
import { FileCard, fileDetail, formatSize, MiniCard } from "../../components/import-parts";
import {
  factsAbove,
  failureText,
  foundRows,
  foundSoFar,
  type ImportStatus,
  plural,
  READING_STAGES,
  type ReadingStatus,
  type Review,
  stageSpan,
  stageStates,
} from "../../lib/imports";
import { DeleteImport } from "./[id]/delete-import";

const STEP_MS = 380;
const ASK_EVERY_MS = 1_500;
const ASK_WHILE_HIDDEN_MS = 6_000;

function prefersLessMotion(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

// The file on its way, before the server has kept it.
export type Sending = { name: string; size: number; error: string | null };

export function Reading({
  status: initial,
  sending,
  onRetry,
}: {
  status: ImportStatus | null;
  sending?: Sending;
  onRetry?: () => void;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<ImportStatus | null>(initial);
  const [review, setReview] = useState<Review | null>(null);
  const [gone, setGone] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  // While it's read, the bar creeps across the current stage's stretch.
  const [creep, setCreep] = useState(() => stageSpan(initial?.stage ?? null)[0]);
  const [ticked, setTicked] = useState(0);
  const [lessMotion] = useState(prefersLessMotion);

  const id = status?.id ?? null;
  const reading = status?.state === "reading" || (status === null && !sending?.error);
  const stage = status?.stage ?? null;

  // Asks where the reading is until it's read or has failed.
  useEffect(() => {
    if (id === null || status?.state !== "reading") return;
    let stopped = false;
    const timer = window.setTimeout(
      async () => {
        try {
          const response = await fetch(`/import/${id}/status`, { cache: "no-store" });
          if (stopped) return;
          if (response.status === 404) {
            setGone(true);
            return;
          }
          const body = (await response.json().catch(() => null)) as ReadingStatus | null;
          if (stopped) return;
          if (response.ok && body) {
            const { review: found, ...fresh } = body;
            if (found) setReview(found);
            setStatus(fresh);
            return;
          }
        } catch {
          // Offline for a moment: ask again.
        }
        // Same state again, so the effect runs once more.
        if (!stopped) setStatus((s) => (s ? { ...s } : s));
      },
      document.visibilityState === "visible" ? ASK_EVERY_MS : ASK_WHILE_HIDDEN_MS,
    );
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [id, status]);

  useEffect(() => {
    if (!reading) return;
    const [from, to] = stageSpan(stage);
    const timer = window.setInterval(() => {
      setCreep((p) => {
        const at = Math.max(p, from);
        return at + (to - at) * 0.05;
      });
    }, 200);
    return () => window.clearInterval(timer);
  }, [reading, stage]);

  const rows = review ? foundRows(review) : null;
  const total = rows?.length ?? 0;

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

  async function readAgain() {
    if (!id) return;
    setRetrying(true);
    setRetryError(null);
    try {
      const response = await fetch(`/import/${id}/read-again`, { method: "POST" });
      const body = (await response.json().catch(() => null)) as
        | (ImportStatus & { error?: string })
        | null;
      if (response.ok && body) {
        setCreep(stageSpan(null)[0]);
        setStatus(body);
      } else {
        setRetryError(body?.error ?? "That didn't start. Try again in a moment.");
      }
    } catch {
      setRetryError("The connection dropped. Check you're online and try again.");
    }
    setRetrying(false);
  }

  const startOver = onRetry ?? (() => router.push("/import"));
  const name = status?.file.name ?? sending?.name ?? "resume";
  const size = status?.file.size ?? sending?.size ?? 0;

  if (gone) {
    return (
      <main className="page">
        <PageHead back={{ href: "/import", label: "Back" }} step={1} />
        <div className="stack tight">
          <h1 className="title">That import isn&apos;t here any more.</h1>
          <p className="lede">It was deleted, so there&apos;s nothing left to read.</p>
        </div>
        <div className="dock">
          <Link className="button primary" href="/import">
            Bring in a resume
          </Link>
        </div>
      </main>
    );
  }

  if (sending?.error && status === null) {
    return (
      <main className="page">
        <PageHead back={{ onClick: startOver, label: "Back" }} step={1} />
        <FileCard name={name} detail={`${formatSize(size)} · not saved`} href={null} />
        <div className="stack tight">
          <h1 className="title">That one didn&apos;t come through.</h1>
          <p className="lede">Nothing was saved, and no cards were made.</p>
        </div>
        <p className="alert" role="alert">
          {sending.error}
        </p>
        <div className="dock">
          <button className="button primary" type="button" onClick={startOver}>
            Try another way
          </button>
        </div>
      </main>
    );
  }

  if (status?.state === "failed") {
    // Trying an unreadable file again won't help; any other failure might pass.
    const canRetry = status.error_code !== "unreadable";
    return (
      <main className="page">
        <PageHead back={{ href: "/import", label: "Back" }} step={1} />
        <FileCard
          name={name}
          detail={`${formatSize(size)} · kept private`}
          href={`/import/${status.id}/original`}
        />
        <div className="stack tight">
          <h1 className="title">We couldn&apos;t read this one.</h1>
          <p className="lede">{failureText(status.error_code)}</p>
        </div>
        {retryError && (
          <p className="alert" role="alert">
            {retryError}
          </p>
        )}
        <div className="dock">
          {canRetry ? (
            <button className="button primary" type="button" onClick={readAgain} disabled={retrying}>
              {retrying ? "Starting…" : "Try again"}
            </button>
          ) : (
            <Link className="button primary" href="/import">
              Try another way
            </Link>
          )}
          {canRetry && (
            <Link className="text-button" href="/import">
              Try another way
            </Link>
          )}
          <p className="note">Nothing was made into a card.</p>
        </div>
        <DeleteImport id={status.id} approved={0} />
      </main>
    );
  }

  const revealed = review && lessMotion ? total : ticked;
  const done = review !== null && revealed >= total;
  const percent = review
    ? Math.round(60 + (40 * revealed) / Math.max(total, 1))
    : Math.round(Math.max(creep, stageSpan(stage)[0]) * 100);
  const shown = review ? foundSoFar(review).slice(0, done ? 4 : Math.max(0, revealed - 2)) : [];
  const steps = stageStates(stage, review !== null || status?.state === "read");
  const current = READING_STAGES[steps.indexOf("working")];

  return (
    <main className="page">
      <PageHead step={2} progress={percent / 100} />
      <FileCard
        name={review?.file.name ?? name}
        detail={review ? fileDetail(review.file) : `${formatSize(size)} · kept private`}
        href={id ? `/import/${id}/original` : null}
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
            : "This usually takes under a minute. You can leave this page: we'll keep reading, and it'll be here when you come back."}
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
            {review
              ? `${Math.min(revealed, total)} of ${total} checks complete`
              : status === null
                ? "Sending your file"
                : (current?.label ?? "Opening your file")}
          </span>
        </div>
      </section>

      <section className="surface top-bar found" style={{ ["--bar" as string]: "var(--teal)" }}>
        {rows ? (
          <>
            <div className="row found-head">
              <h2 className="label">What we&apos;ve found</h2>
              <span className="label medium">
                {Math.min(revealed, total)} of {total} done
              </span>
            </div>
            <ul className="found-rows" aria-live="polite">
              {rows.map((row, i) => {
                const state = i < revealed ? "done" : i === revealed ? "working" : "pending";
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
              })}
            </ul>
          </>
        ) : (
          <>
            <div className="row found-head">
              <h2 className="label">Where we are</h2>
              <span className="label medium">
                {steps.filter((s) => s === "done").length} of {READING_STAGES.length} steps
              </span>
            </div>
            <ul className="found-rows" aria-live="polite">
              {READING_STAGES.map((step, i) => {
                const state = status === null ? (i === 0 ? "working" : "pending") : steps[i];
                return (
                  <li key={step.stage} className="found-row" data-state={state}>
                    <span className="found-mark">
                      {state === "done" && <Icon icon={faCheck} size={10} />}
                    </span>
                    <span className="found-text">
                      <span className="found-label">{step.label}</span>
                    </span>
                    {state === "done" && <span className="label teal">Done</span>}
                    {state === "working" && <span className="label orange">In progress</span>}
                  </li>
                );
              })}
            </ul>
          </>
        )}
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
                above={factsAbove(card, review)}
              />
            ))}
          </div>
        </section>
      )}

      <div className="dock">
        {done && review ? (
          // This screen is the import's own page until it's read, so the page
          // is drawn again to show what was found.
          <button className="button primary" type="button" onClick={() => router.refresh()}>
            See what we found
            <Icon icon={faArrowRight} size={16} />
          </button>
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
