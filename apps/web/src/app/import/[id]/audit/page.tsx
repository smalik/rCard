// The full audit: everything the import noticed, grouped the way the
// checklist groups it.

import { faArrowRight, faCheck } from "@fortawesome/free-solid-svg-icons";
import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "../../../../components/hybrid";
import { Icon } from "../../../../components/icon";
import {
  bySeverity,
  type Finding,
  lineLabel,
  plural,
  type Review,
  SEVERITY_LABELS,
  settleState,
} from "../../../../lib/imports";
import { loadReview } from "../load";

export const metadata: Metadata = { title: "The full audit" };
export const dynamic = "force-dynamic";

const SEVERITY_TONE = {
  fix: "orange",
  improve: "amber",
  note: "sand",
} as const;

type Group = {
  id: string;
  title: string;
  empty: string;
  match: (f: Finding) => boolean;
};

const GROUPS: Group[] = [
  {
    id: "dates",
    title: "Jobs and dates",
    empty: "The dates line up.",
    match: (f) => f.rule.startsWith("dates."),
  },
  {
    id: "numbers",
    title: "Numbers",
    empty: "No number says one thing here and another there.",
    match: (f) => f.rule === "consistency.figures",
  },
  {
    id: "repeats",
    title: "Possible repeats",
    empty: "No line says the same thing twice.",
    match: (f) => f.rule === "content.duplicates",
  },
  {
    id: "wording",
    title: "Wording tips",
    empty: "No wording tips.",
    match: (f) => f.about === "cards",
  },
  {
    id: "file",
    title: "About the file itself",
    empty: "Nothing to note about the layout.",
    match: (f) => f.about === "document",
  },
];

function Item({ review, finding, index }: { review: Review; finding: Finding; index: number }) {
  const asked = review.toSettle.includes(index);
  const state = asked ? settleState(index, review.progress) : null;
  return (
    <li className="surface audit-item">
      <div className="row start wrap">
        <span className={`pill small ${SEVERITY_TONE[finding.severity]}`}>
          {SEVERITY_LABELS[finding.severity]}
        </span>
        {state === "settled" && (
          <span className="pill small outline-teal">
            <Icon icon={faCheck} size={8} />
            Settled
          </span>
        )}
        {state === "later" && <span className="pill small sand">Later</span>}
      </div>
      <h3 className="audit-title">{finding.title}</h3>
      <p className="small-copy muted">{finding.detail}</p>
      {finding.locations
        .filter((loc) => loc.excerpt)
        .slice(0, 3)
        .map((loc, i) => (
          <figure key={i} className="audit-quote">
            <figcaption className="label small">{lineLabel(review, loc.block)}</figcaption>
            <blockquote>{loc.excerpt}</blockquote>
          </figure>
        ))}
    </li>
  );
}

export default async function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await loadReview(id);
  const sorted = bySeverity(review.findings);
  const used = new Set<number>();
  const skills = review.cards.filter((c) => c.kind === "skill");

  return (
    <main className="page">
      <PageHead back={{ href: `/import/${id}`, label: "Back to what we found" }} step={2} />
      <div className="stack tight">
        <h1 className="title compact">The full audit</h1>
        <p className="lede">
          {plural(review.findings.length, "thing")} we noticed reading your resume. None of it
          changes your original file.
        </p>
      </div>

      {GROUPS.map((group) => {
        const items = sorted.filter(({ finding, index }) => {
          if (used.has(index) || !group.match(finding)) return false;
          used.add(index);
          return true;
        });
        return (
          <section
            key={group.id}
            id={group.id}
            className="stack"
            aria-labelledby={`${group.id}-title`}
          >
            <div className="row">
              <h2 className="section-title" id={`${group.id}-title`}>
                {group.title}
              </h2>
              <span className="label medium">{items.length}</span>
            </div>
            {items.length === 0 ? (
              <p className="small-copy muted">{group.empty}</p>
            ) : (
              <ul className="audit-list">
                {items.map(({ finding, index }) => (
                  <Item key={index} review={review} finding={finding} index={index} />
                ))}
              </ul>
            )}
          </section>
        );
      })}

      <section id="skills" className="stack" aria-labelledby="skills-title">
        <h2 className="section-title" id="skills-title">
          Skills
        </h2>
        {skills.length === 0 ? (
          <p className="small-copy muted">No skills section was found.</p>
        ) : (
          <ul className="audit-list">
            {skills.map((card) => {
              const list = card.content.facts.skills;
              return (
                <li key={card.ref} className="surface audit-item">
                  <h3 className="audit-title">{card.content.framing.headline}</h3>
                  <p className="small-copy muted">
                    {Array.isArray(list) ? list.join(", ") : card.content.framing.body}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section id="private" className="sand-panel stack tight" aria-labelledby="private-title">
        <h2 className="panel-title" id="private-title">
          Things we left out
        </h2>
        <p className="small-copy">
          {review.contactKept
            ? "Your contact details were found and stay in this import, encrypted. They never go on cards."
            : "No contact details needed setting aside."}{" "}
          Headings, page numbers and layout don&apos;t become cards either.
        </p>
      </section>

      <div className="dock">
        <Link className="button primary" href={`/import/${id}`}>
          Back to what we found
          <Icon icon={faArrowRight} size={16} />
        </Link>
      </div>
    </main>
  );
}
