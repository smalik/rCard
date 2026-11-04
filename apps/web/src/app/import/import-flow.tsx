"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { BODY_MAX, type CardContent, type FactValue, HEADLINE_MAX, KIND_LABELS } from "../../lib/cards";
import {
  type CardGroup,
  type Decision,
  type Decisions,
  FACT_HINTS,
  FILENAME_HEADER,
  type Finding,
  type ImportPreview,
  MAX_ACCEPT_CARDS,
  MAX_IMPORT_BYTES,
  type ProposedCard,
  SEVERITY_LABELS,
  type Severity,
  acceptBody,
  bySeverity,
  cardsForFinding,
  contentProblems,
  factLabel,
  factToText,
  findingKey,
  findingsForCard,
  groupCards,
  initialDecisions,
  isAboutCards,
  isRoleContext,
  keptCards,
  roleSubtitle,
  severityCounts,
  textToFact,
  visibleFacts,
} from "../../lib/import-review";

const ACCEPTED_TYPES = [
  ".docx",
  ".pdf",
  ".txt",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/pdf",
  "text/plain",
].join(",");

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { error?: unknown };
    return typeof body.error === "string" ? body.error : fallback;
  } catch {
    return fallback;
  }
}

export function ImportFlow() {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function read(file: File) {
    setError(null);
    if (file.size > MAX_IMPORT_BYTES) {
      setError("Resumes over 5 MB aren't supported.");
      return;
    }
    setReading(true);
    try {
      const response = await fetch("/import/preview", {
        method: "POST",
        body: file,
        headers: { [FILENAME_HEADER]: encodeURIComponent(file.name) },
      });
      if (!response.ok) {
        setError(await errorMessage(response, "Plytos couldn't read that file. Try again."));
        return;
      }
      setPreview((await response.json()) as ImportPreview);
    } catch {
      setError("Plytos couldn't reach the server. Check your connection and try again.");
    } finally {
      setReading(false);
    }
  }

  if (preview) return <Review preview={preview} onRestart={() => setPreview(null)} />;

  return (
    <main className="screen">
      <header className="topbar">
        <Link className="back small" href="/cards">
          Your cards
        </Link>
        <h1>Import your resume</h1>
      </header>
      <section className="panel">
        <p>
          Plytos reads your resume, splits it into cards in your own words, and checks it for
          problems a recruiter or hiring software would trip on.
        </p>
        <p className="muted small">
          Nothing is saved until you choose which cards to keep. Word (.docx), PDF or plain text,
          up to 5 MB.
        </p>
        <label className={`button primary file-button${reading ? " busy" : ""}`}>
          {reading ? "Reading your resume…" : "Choose your resume"}
          <input
            className="visually-hidden"
            type="file"
            accept={ACCEPTED_TYPES}
            disabled={reading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void read(file);
            }}
          />
        </label>
        {error && (
          <p className="attention" role="alert">
            {error}
          </p>
        )}
      </section>
    </main>
  );
}

type Tab = "audit" | "cards";
type Filter = { title: string; refs: string[] };

function Review({ preview, onRestart }: { preview: ImportPreview; onRestart: () => void }) {
  const router = useRouter();
  const [decisions, setDecisions] = useState<Decisions>(() => initialDecisions(preview.cards));
  const [tab, setTab] = useState<Tab>("audit");
  const [filter, setFilter] = useState<Filter | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saved = useRef(false);

  const groups = useMemo(() => groupCards(preview.cards), [preview.cards]);
  const byRef = useMemo(() => new Map(preview.cards.map((c) => [c.ref, c])), [preview.cards]);
  const counts = severityCounts(preview.findings);
  const kept = keptCards(preview.cards, decisions);
  const blocked = kept.filter((c) => contentProblems(decisions[c.ref]!.content).length > 0);

  // The review lives only in this page. Leaving it loses the work, so ask.
  useEffect(() => {
    function warn(event: BeforeUnloadEvent) {
      if (!saved.current) event.preventDefault();
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  function update(ref: string, change: Partial<Decision>) {
    setDecisions((current) => ({ ...current, [ref]: { ...current[ref]!, ...change } }));
  }

  function setKeep(refs: string[], keep: boolean) {
    setDecisions((current) => {
      const next = { ...current };
      for (const ref of refs) next[ref] = { ...next[ref]!, keep };
      return next;
    });
  }

  function showCards(title: string, refs: string[]) {
    setFilter({ title, refs });
    setTab("cards");
    window.scrollTo({ top: 0 });
  }

  function restart() {
    if (window.confirm("Start over with another file? Your choices here will be lost.")) onRestart();
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const response = await fetch("/import/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(acceptBody(preview.cards, decisions)),
      });
      if (!response.ok) {
        setSaveError(await errorMessage(response, "Plytos couldn't save your cards. Try again."));
        return;
      }
      const { saved: count } = (await response.json()) as { saved: number };
      saved.current = true;
      router.push(`/cards?imported=${count}`);
    } catch {
      setSaveError("Plytos couldn't reach the server. Nothing was saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  const editingCard = editing ? byRef.get(editing) : undefined;
  const dropped = preview.cards.length - kept.length;
  const tooMany = kept.length > MAX_ACCEPT_CARDS;

  return (
    <main className="screen wide">
      <header className="review-head">
        <div className="topbar-row">
          <h1>Review your import</h1>
          <button className="link small" type="button" onClick={restart}>
            Start over
          </button>
        </div>
        <p className="muted small">
          {preview.cards.length} proposed cards from a {preview.file.words.toLocaleString()}-word
          resume. The audit found {counts.fix} to fix, {counts.improve} to improve and {counts.note}{" "}
          {counts.note === 1 ? "note" : "notes"}.
        </p>
      </header>
      <div className="tabs-bar">
        <div className="tabs" role="tablist" aria-label="Review">
          <TabButton tab="audit" current={tab} onSelect={setTab}>
            Audit <span className="count">{preview.findings.length}</span>
          </TabButton>
          <TabButton tab="cards" current={tab} onSelect={setTab}>
            Cards{" "}
            <span className="count">
              {kept.length}/{preview.cards.length}
            </span>
          </TabButton>
        </div>
      </div>

      <div className="review">
        <section
          className="pane"
          id="pane-audit"
          role="tabpanel"
          aria-label="Audit"
          data-active={tab === "audit"}
        >
          <AuditPane findings={preview.findings} cards={preview.cards} onShowCards={showCards} />
        </section>
        <section
          className="pane"
          id="pane-cards"
          role="tabpanel"
          aria-label="Proposed cards"
          data-active={tab === "cards"}
        >
          {filter && (
            <div className="filter-bar">
              <p className="small">
                Cards for <strong>{filter.title}</strong>
              </p>
              <button className="link small" type="button" onClick={() => setFilter(null)}>
                Show all
              </button>
            </div>
          )}
          {groups.map((group) => (
            <GroupSection
              key={group.key}
              group={group}
              filter={filter}
              byRef={byRef}
              decisions={decisions}
              findings={preview.findings}
              cards={preview.cards}
              onKeep={setKeep}
              onEdit={setEditing}
            />
          ))}
        </section>
      </div>

      <footer className="actionbar">
        {saveError && (
          <p className="attention small" role="alert">
            {saveError}
          </p>
        )}
        <p className="muted small">
          {dropped > 0 ? `${dropped} dropped. ` : ""}
          {blocked.length > 0
            ? `${blocked.length} ${blocked.length === 1 ? "card needs" : "cards need"} a fix before saving.`
            : tooMany
              ? `Keep ${MAX_ACCEPT_CARDS} cards or fewer in one import.`
              : "Saved cards stay private to you."}
        </p>
        <button
          className="button primary"
          type="button"
          disabled={saving || kept.length === 0 || blocked.length > 0 || tooMany}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : `Save ${kept.length} ${kept.length === 1 ? "card" : "cards"}`}
        </button>
      </footer>

      {editingCard && (
        <CardEditor
          card={editingCard}
          content={decisions[editingCard.ref]!.content}
          onCancel={() => setEditing(null)}
          onSave={(content) => {
            const edited = JSON.stringify(content) !== JSON.stringify(editingCard.content);
            update(editingCard.ref, { content, edited });
            setEditing(null);
          }}
        />
      )}
    </main>
  );
}

function TabButton({
  tab,
  current,
  onSelect,
  children,
}: {
  tab: Tab;
  current: Tab;
  onSelect: (tab: Tab) => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={tab === current}
      aria-controls={`pane-${tab}`}
      onClick={() => onSelect(tab)}
    >
      {children}
    </button>
  );
}

function SeverityTag({ severity }: { severity: Severity | "check" }) {
  return (
    <span className={`sev sev-${severity}`}>
      {severity === "check" ? "Check" : SEVERITY_LABELS[severity]}
    </span>
  );
}

function AuditPane({
  findings,
  cards,
  onShowCards,
}: {
  findings: Finding[];
  cards: ProposedCard[];
  onShowCards: (title: string, refs: string[]) => void;
}) {
  const indexed = findings.map((finding, i) => ({ finding, key: findingKey(finding, i) }));
  const keys = new Map(indexed.map(({ finding, key }) => [finding, key]));
  const aboutCards = bySeverity(findings.filter(isAboutCards));
  const aboutFile = bySeverity(findings.filter((f) => !isAboutCards(f)));

  const list = (items: Finding[], withCards: boolean) => (
    <ul className="finding-list">
      {items.map((finding) => (
        <FindingItem
          key={keys.get(finding)}
          finding={finding}
          refs={withCards ? cardsForFinding(finding, cards) : []}
          onShowCards={onShowCards}
        />
      ))}
    </ul>
  );

  if (findings.length === 0) {
    return (
      <div className="pane-section">
        <h2>Nothing to flag</h2>
        <p className="muted small">The audit didn&apos;t find any problems in this resume.</p>
      </div>
    );
  }

  return (
    <>
      {aboutCards.length > 0 && (
        <div className="pane-section">
          <h2>In your words</h2>
          <p className="muted small">
            These travel with your cards. Edit the cards to fix them, now or after you save.
          </p>
          {list(aboutCards, true)}
        </div>
      )}
      {aboutFile.length > 0 && (
        <div className="pane-section">
          <h2>In the file</h2>
          <p className="muted small">
            These are about how this file is laid out and formatted, and how hiring software reads
            it. They don&apos;t come along into your cards. Fix them in any copy you still send
            out.
          </p>
          {list(aboutFile, false)}
        </div>
      )}
    </>
  );
}

function FindingItem({
  finding,
  refs,
  onShowCards,
}: {
  finding: Finding;
  refs: string[];
  onShowCards: (title: string, refs: string[]) => void;
}) {
  const excerpts = [...new Set(finding.locations.map((loc) => loc.excerpt).filter(Boolean))];
  return (
    <li className="finding">
      <details>
        <summary>
          <SeverityTag severity={finding.severity} />
          <span className="finding-title">{finding.title}</span>
        </summary>
        <div className="finding-body">
          <p className="small">{finding.detail}</p>
          {excerpts.length > 0 && (
            <ul className="excerpts small">
              {excerpts.slice(0, 3).map((excerpt) => (
                <li key={excerpt}>“{excerpt}”</li>
              ))}
              {excerpts.length > 3 && <li className="muted">and {excerpts.length - 3} more</li>}
            </ul>
          )}
        </div>
      </details>
      {refs.length > 0 && (
        <button
          className="link small"
          type="button"
          onClick={() => onShowCards(finding.title, refs)}
        >
          {refs.length === 1 ? "See the card" : `See the ${refs.length} cards`}
        </button>
      )}
    </li>
  );
}

function GroupSection({
  group,
  filter,
  byRef,
  decisions,
  findings,
  cards,
  onKeep,
  onEdit,
}: {
  group: CardGroup;
  filter: Filter | null;
  byRef: Map<string, ProposedCard>;
  decisions: Decisions;
  findings: Finding[];
  cards: ProposedCard[];
  onKeep: (refs: string[], keep: boolean) => void;
  onEdit: (ref: string) => void;
}) {
  const refs = filter ? group.refs.filter((ref) => filter.refs.includes(ref)) : group.refs;
  if (refs.length === 0) return null;
  const role = group.roleCard ? decisions[group.roleCard]!.content : null;
  const title = role ? role.framing.headline : group.title;
  const subtitle = role ? roleSubtitle(role) : null;
  const keptCount = group.refs.filter((ref) => decisions[ref]!.keep).length;

  return (
    <section className="group" aria-label={title}>
      <div className="group-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        <button
          className="link small"
          type="button"
          onClick={() => onKeep(group.refs, keptCount === 0)}
        >
          {keptCount === 0 ? "Keep all" : "Drop all"}
        </button>
      </div>
      <ul className="card-list single">
        {refs.map((ref) => (
          <ReviewCard
            key={ref}
            card={byRef.get(ref)!}
            decision={decisions[ref]!}
            findings={findings}
            cards={cards}
            onKeep={(keep) => onKeep([ref], keep)}
            onEdit={() => onEdit(ref)}
          />
        ))}
      </ul>
    </section>
  );
}

function ReviewCard({
  card,
  decision,
  findings,
  cards,
  onKeep,
  onEdit,
}: {
  card: ProposedCard;
  decision: Decision;
  findings: Finding[];
  cards: ProposedCard[];
  onKeep: (keep: boolean) => void;
  onEdit: () => void;
}) {
  const { content, keep } = decision;
  const facts = visibleFacts(card, content);
  const notes = findingsForCard(card, findings, cards);
  const problems = contentProblems(content);

  return (
    <li className={`card review-card${keep ? "" : " dropped"}`}>
      <div className="card-top">
        <span className="chip">{KIND_LABELS[card.kind]}</span>
        <span className="muted small">{keep ? (decision.edited ? "Edited" : "") : "Dropped"}</span>
      </div>
      <p className="card-headline">{content.framing.headline}</p>
      {content.framing.body && <p className="card-body small">{content.framing.body}</p>}
      {facts.length > 0 && (
        <dl className="facts small">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {keep && (notes.length > 0 || card.needs_check.length > 0) && (
        <ul className={`card-notes small${decision.edited ? " stale" : ""}`}>
          {decision.edited && <li className="muted">Found before your edit:</li>}
          {card.needs_check.map((question) => (
            <li key={question}>
              <SeverityTag severity="check" /> {question}
            </li>
          ))}
          {notes.map(({ finding }, i) => (
            <li key={`${finding.rule}-${i}`}>
              <details>
                <summary>
                  <SeverityTag severity={finding.severity} /> {finding.title}
                </summary>
                <p className="muted">{finding.detail}</p>
              </details>
            </li>
          ))}
        </ul>
      )}
      {keep && problems.length > 0 && (
        <p className="attention small" role="alert">
          {problems[0]}
        </p>
      )}
      <div className="card-actions">
        {keep && (
          <button className="button compact" type="button" onClick={onEdit}>
            Edit
          </button>
        )}
        <button
          className="button compact"
          type="button"
          aria-pressed={!keep}
          onClick={() => onKeep(!keep)}
        >
          {keep ? "Drop" : "Keep"}
        </button>
      </div>
    </li>
  );
}

function CardEditor({
  card,
  content,
  onCancel,
  onSave,
}: {
  card: ProposedCard;
  content: CardContent;
  onCancel: () => void;
  onSave: (content: CardContent) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [headline, setHeadline] = useState(content.framing.headline);
  const [body, setBody] = useState(content.framing.body);
  // The card's own facts first, then the ones it shares with its role.
  const editable = Object.entries(content.facts)
    .filter(([key]) => key !== "use")
    .sort(([a], [b]) => Number(isRoleContext(card, a)) - Number(isRoleContext(card, b)));
  const [facts, setFacts] = useState<Record<string, string>>(() =>
    Object.fromEntries(editable.map(([key, value]) => [key, factToText(value)])),
  );

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => element?.close();
  }, []);

  function draft(): CardContent {
    const next: Record<string, FactValue> = {};
    for (const [key, original] of Object.entries(content.facts)) {
      const value = key in facts ? textToFact(facts[key]!, original) : original;
      if (value !== undefined) next[key] = value;
    }
    return { facts: next, framing: { ...content.framing, headline: headline.trim(), body } };
  }

  const problems = contentProblems(draft());

  function submit(event: FormEvent) {
    event.preventDefault();
    if (problems.length === 0) onSave(draft());
  }

  return (
    <dialog
      ref={dialog}
      className="sheet"
      aria-labelledby="editor-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form className="sheet-form" onSubmit={submit}>
        <header className="sheet-head">
          <h2 id="editor-title">Edit {KIND_LABELS[card.kind].toLowerCase()} card</h2>
          <p className="muted small">
            Changes here shape the first version of the card. Facts can change later too, and every
            version is kept.
          </p>
        </header>
        <label className="field">
          <span>Headline</span>
          <textarea
            rows={3}
            maxLength={HEADLINE_MAX + 50}
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Description</span>
          <textarea
            rows={4}
            maxLength={BODY_MAX}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
        {editable.length > 0 && (
          <fieldset className="field-group">
            <legend>Facts</legend>
            {editable.map(([key]) => (
              <label className="field" key={key}>
                <span>
                  {factLabel(key)}
                  {FACT_HINTS[key] && <span className="muted"> · {FACT_HINTS[key]}</span>}
                </span>
                <input
                  value={facts[key] ?? ""}
                  onChange={(e) => setFacts((current) => ({ ...current, [key]: e.target.value }))}
                />
              </label>
            ))}
            <p className="muted small">Clear a field to remove that fact.</p>
          </fieldset>
        )}
        {problems.length > 0 && (
          <ul className="attention small" role="alert">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        <div className="sheet-actions">
          <button className="button" type="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="button primary" type="submit" disabled={problems.length > 0}>
            Save changes
          </button>
        </div>
      </form>
    </dialog>
  );
}
