// Step 2, "Check": what the audit found, as a starting point. The person can
// settle the few things that don't line up, or go straight to their cards.

import {
  faArrowRight,
  faCheck,
  faClock,
  faClone,
  faHashtag,
  faLightbulb,
  faLock,
  faPenNib,
  faUser,
  faWandMagicSparkles,
  type IconDefinition,
} from "@fortawesome/free-solid-svg-icons";
import type { Metadata } from "next";
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { PageHead } from "../../../components/hybrid";
import { Icon } from "../../../components/icon";
import { FannedCards, FileCard, fileDetail } from "../../../components/import-parts";
import {
  BATCH_SIZE,
  minutesFor,
  overview,
  plural,
  readerName,
  settledCount,
} from "../../../lib/imports";
import { DeleteImport } from "./delete-import";
import { loadReview } from "./load";

export const metadata: Metadata = { title: "What we found" };
export const dynamic = "force-dynamic";

type Status = {
  tone: "orange" | "teal" | "sand";
  text: string;
  icon?: IconDefinition;
};

function CheckItem({
  href,
  bar,
  icon,
  title,
  status,
  children,
}: {
  href: string;
  bar: string;
  icon: IconDefinition;
  title: string;
  status: Status;
  children: ReactNode;
}) {
  return (
    <li>
      <Link
        className="surface top-bar check-item"
        href={href}
        style={{ "--bar": bar } as CSSProperties}
      >
        <span className="icon-tile small">
          <Icon icon={icon} size={18} />
        </span>
        <span className="check-item-text">
          <span className="check-item-title">
            {title}
            <Icon icon={faArrowRight} size={14} />
          </span>
          <span className="check-item-detail">{children}</span>
          <span className={`pill ${status.tone}`}>
            {status.icon && <Icon icon={status.icon} size={10} />}
            {status.text}
          </span>
        </span>
      </Link>
    </li>
  );
}

export default async function ImportOverview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await loadReview(id);
  const o = overview(review);
  const base = `/import/${id}`;
  const without = o.accomplishments - o.withNumbers;
  const total = review.toSettle.length;
  const settled = settledCount(review);
  const done: Status = { tone: "teal", text: "Done", icon: faCheck };

  const checks = [
    { open: o.dateQuestions, label: "to confirm" },
    { open: o.figureQuestions, label: "to check" },
    { open: o.repeatQuestions, label: "to review" },
  ];
  const steps = checks.length;
  const stepsDone = checks.filter((c) => c.open === 0).length;

  return (
    <main className="page wide">
      <PageHead
        back={{ href: "/import", label: "Back" }}
        step={2}
        progress={total > 0 ? settled / total : 1}
      />
      <div className="stack tight">
        <h1 className="title">Here&apos;s what we found. A solid start.</h1>
        <p className="lede">
          {plural(o.things, "thing was", "things were")} pulled from your resume.{" "}
          {o.open > 0
            ? "A few need your eye before they become cards."
            : "Nothing becomes a card until you approve it."}
        </p>
      </div>

      <div className="split">
        <div className="split-main stack roomy">
          {o.accomplishments > 0 && (
            <section
              className="surface top-bar proof"
              style={{ "--bar": "var(--teal)" } as CSSProperties}
              aria-labelledby="proof"
            >
              <div className="row">
                <h2 className="label teal wide-track" id="proof">
                  Starting proof
                </h2>
                <span className="label medium">{plural(o.accomplishments, "accomplishment")}</span>
              </div>
              <div
                className="proof-bar"
                role="img"
                aria-label={`${o.withNumbers} of ${o.accomplishments} accomplishments have numbers`}
              >
                {o.withNumbers > 0 && (
                  <span className="proof-with" style={{ flexGrow: o.withNumbers }}>
                    {o.withNumbers}
                  </span>
                )}
                {without > 0 && (
                  <span className="proof-without" style={{ flexGrow: without }}>
                    {without}
                  </span>
                )}
              </div>
              <div className="proof-evidence" aria-hidden="true">
                <span className="proof-evidence-bar" />
                <span className="label medium">0</span>
              </div>
              <ul className="legend" aria-hidden="true">
                <li>
                  <span className="swatch with" /> With numbers
                </li>
                <li>
                  <span className="swatch without" /> Without
                </li>
                <li>
                  <span className="swatch evidence" /> Evidence
                </li>
              </ul>
              <p className="label ink">
                {o.withNumbers} of {o.accomplishments} have numbers · 0 have evidence
              </p>
              <p className="tip">
                <span className="tip-icon">
                  <Icon icon={faLightbulb} size={12} />
                </span>
                <span>
                  That&apos;s normal for an older resume. Evidence, like a link or a photo, is the
                  easiest thing to add later.
                </span>
              </p>
            </section>
          )}

          <section className="stack" aria-labelledby="checklist">
            <div className="row">
              <h2 className="section-title" id="checklist">
                Audit checklist
              </h2>
              <span className="label medium">
                {steps} steps · {stepsDone} done
              </span>
            </div>
            <ul className="check-list">
              <CheckItem
                href={o.dateQuestions > 0 ? `${base}/settle` : `${base}/audit#dates`}
                bar={o.dateQuestions > 0 ? "var(--blue)" : "var(--teal)"}
                icon={faUser}
                title="Jobs and dates"
                status={
                  o.dateQuestions > 0
                    ? { tone: "orange", text: `${o.dateQuestions} to confirm` }
                    : done
                }
              >
                {plural(o.roles, "role")}
                {o.years ? `, ${o.years[0]}–${o.years[1]}` : ""}.{" "}
                {o.dateQuestions > 0
                  ? `${plural(o.dateQuestions, "date question")} to confirm.`
                  : "The dates line up."}
              </CheckItem>
              <CheckItem
                href={o.figureQuestions > 0 ? `${base}/settle` : `${base}/audit#numbers`}
                bar={o.figureQuestions > 0 ? "var(--orange)" : "var(--teal)"}
                icon={faHashtag}
                title="Numbers"
                status={
                  o.figureQuestions > 0
                    ? { tone: "orange", text: `${o.figureQuestions} to check` }
                    : done
                }
              >
                {o.figureQuestions > 0
                  ? `${plural(o.figureQuestions, "result has", "results have")} a different number in two places. Which is right?`
                  : "No number says one thing here and another there."}
              </CheckItem>
              <CheckItem
                href={o.repeatQuestions > 0 ? `${base}/settle` : `${base}/audit#repeats`}
                bar={o.repeatQuestions > 0 ? "var(--orange)" : "var(--teal)"}
                icon={faClone}
                title="Possible repeats"
                status={
                  o.repeatQuestions > 0
                    ? { tone: "orange", text: `${o.repeatQuestions} to review` }
                    : done
                }
              >
                {o.repeatQuestions > 0
                  ? `${plural(o.repeatQuestions, "line says", "lines say")} the same thing more than once.`
                  : "No line says the same thing twice."}
              </CheckItem>
              <CheckItem
                href={`${base}/audit#skills`}
                bar="var(--teal)"
                icon={faWandMagicSparkles}
                title="Skills"
                status={{ tone: "teal", text: "Grouped", icon: faCheck }}
              >
                {plural(o.skills, "skill")}, grouped the way your resume lists them.
              </CheckItem>
              <CheckItem
                href={`${base}/audit#wording`}
                bar="var(--ink-12)"
                icon={faPenNib}
                title="Wording tips"
                status={{ tone: "sand", text: "On your cards" }}
              >
                {o.wordingTips > 0
                  ? `${plural(o.wordingTips, "tip")} on wording. You'll see each one on its card.`
                  : "No wording tips. Your lines read cleanly."}
              </CheckItem>
              <CheckItem
                href={`${base}/audit#private`}
                bar="var(--ink-30)"
                icon={faLock}
                title="Things we left out"
                status={{ tone: "sand", text: "Kept private", icon: faLock }}
              >
                {review.contactKept
                  ? "Your contact details stay in this import, never on cards."
                  : "Nothing personal needed setting aside."}
                {o.documentNotes > 0 &&
                  ` ${plural(o.documentNotes, "note")} about the file's layout too.`}
              </CheckItem>
            </ul>
            <Link className="text-button teal small self-start" href={`${base}/audit`}>
              See the full audit
              <Icon icon={faArrowRight} size={12} />
            </Link>
          </section>
        </div>

        <aside className="split-side stack roomy">
          <section className="ready" aria-labelledby="ready">
            <FannedCards />
            <div className="stack tight">
              <h2 className="label teal wide-track" id="ready">
                {o.pending > 0 ? "Ready to approve" : "All reviewed"}
              </h2>
              <p className="ready-count">
                {o.pending > 0
                  ? plural(o.pending, "draft card")
                  : plural(o.approved, "card approved", "cards approved")}
              </p>
              <p className="small-copy muted">
                {o.pending > BATCH_SIZE
                  ? `Start with the ${BATCH_SIZE} strongest. You can do the rest any time.`
                  : o.pending > 0
                    ? "Approve the ones you want. Skip any you don't."
                    : "Every card from this resume has been approved, skipped or left out."}
                {o.approved > 0 && o.pending > 0 && ` ${o.approved} approved so far.`}
              </p>
            </div>
          </section>

          <section className="stack tight" aria-labelledby="file">
            <h2 className="label" id="file">
              Your file
            </h2>
            <FileCard
              name={review.file.name}
              detail={fileDetail(review.file)}
              href={`${base}/original`}
            />
            <p className="fine-print">
              {review.readBy
                ? `${readerName(review.readBy)} sorted your lines into cards. Every detail was checked against your file.`
                : "Our built-in rules sorted your lines into cards."}
            </p>
            <DeleteImport id={id} approved={o.approved} />
          </section>
        </aside>
      </div>

      <div className="dock">
        {o.pending > 0 ? (
          <>
            <Link className="button primary" href={`${base}/approve`}>
              Review my cards
              <Icon icon={faArrowRight} size={16} />
            </Link>
            <p className="note">
              <Icon icon={faClock} size={11} />
              About {plural(minutesFor(Math.min(o.pending, BATCH_SIZE)), "minute")} · you can stop
              and come back
            </p>
            {o.open > 0 && (
              <Link className="text-button teal" href={`${base}/settle`}>
                Settle the {plural(o.open, "item")} first
                <Icon icon={faArrowRight} size={14} />
              </Link>
            )}
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
