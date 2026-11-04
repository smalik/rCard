"use client";

// One resume: how it reads now, changing which lines show, its versions
// (restore any of them, name the ones you send), the changes in the resume it
// was made from, and making a version of it for a role or company.

import { faClockRotateLeft, faPen, faPrint } from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { AppHeader, TabBar } from "../../../components/hybrid";
import { Icon } from "../../../components/icon";
import { ResumeDocument, type ResumeEdits } from "../../../components/resume-document";
import {
  askText,
  bringBack,
  changesLabel,
  type LabeledChange,
  leaveOut,
  move,
  type RenderedResume,
  type ResumeContent,
  resumeFor,
  type ResumePage,
  type ResumeVersion,
  type ResumeVersionPage,
  sameContent,
  setFold,
  switchOff,
  switchOn,
  TARGET_MAX,
  versionAuthor,
  versionLabel,
} from "../../../lib/resumes";

type Sent<T> = { ok: true; data: T } | { ok: false; error: string };

async function send<T>(url: string, body?: unknown): Promise<Sent<T>> {
  try {
    const response = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = (await response.json().catch(() => null)) as (T & { error?: string }) | null;
    if (response.ok && data) return { ok: true, data };
    return { ok: false, error: data?.error ?? "That didn't go through. Try again in a moment." };
  } catch {
    return { ok: false, error: "The connection dropped. Check you're online and try again." };
  }
}

function when(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function ResumeScreen({
  initial,
  viewing,
}: {
  initial: ResumePage;
  viewing: ResumeVersionPage | null;
}) {
  const router = useRouter();
  const [current, setCurrent] = useState(initial);
  const [draft, setDraft] = useState<ResumeContent | null>(null);
  const [draftPage, setDraftPage] = useState<RenderedResume | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const resume = current.resume;
  const base = `/resumes/${encodeURIComponent(resume.id)}`;

  async function act<T>(action: string, body: unknown): Promise<T | null> {
    setBusy(true);
    setError(null);
    const result = await send<T>(`${base}/${action}`, body);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return null;
    }
    return result.data;
  }

  async function change(next: ResumeContent) {
    setDraft(next);
    const page = await act<RenderedResume>("preview", { content: next });
    if (page) setDraftPage(page);
  }

  async function save() {
    if (!draft) return;
    const saved = await act<ResumePage>("save", {
      content: draft,
      base_version_id: resume.head.id,
    });
    if (saved) {
      setCurrent(saved);
      setDraft(null);
      setDraftPage(null);
    }
  }

  async function restore(number: number) {
    const restored = await act<ResumePage>("restore", {
      number,
      base_version_id: resume.head.id,
    });
    if (restored) {
      setCurrent(restored);
      if (viewing) router.replace(base);
    }
  }

  const edits: ResumeEdits | undefined = draft
    ? {
        busy,
        switchOff: (item) => change(switchOff(draft, item)),
        switchOn: (entry, item) => change(switchOn(draft, entry, item)),
        leaveOut: (entry) => change(leaveOut(draft, entry)),
        bringBack: (entry) => change(bringBack(draft, entry)),
        setFold: (entry, fold) => change(setFold(draft, entry, fold)),
        move: (entry, by) => change(move(draft, entry, by)),
      }
    : undefined;

  if (viewing) {
    return (
      <main className="screen resume-screen">
        <AppHeader back={{ href: base, label: "Back to the latest version" }} />
        <section className="panel notice resume-viewing" role="status">
          <p>
            <b>{versionLabel(viewing.version)}</b>, from {when(viewing.version.created_at)}. Your
            resume is at version {resume.head.number}.
          </p>
          {error && (
            <p className="attention small" role="alert">
              {error}
            </p>
          )}
          <div className="row wrap">
            <button
              className="button primary"
              type="button"
              disabled={busy}
              onClick={() => restore(viewing.version.number)}
            >
              Bring this version back
            </button>
            <Link className="link small" href={base}>
              Back to the latest
            </Link>
          </div>
        </section>
        <ResumeDocument page={viewing.page} />
      </main>
    );
  }

  const page = draftPage ?? current.page;
  const changed = draft !== null && !sameContent(draft, resume.content);

  return (
    <main className="screen resume-screen">
      <AppHeader back={{ href: "/resumes", label: "All resumes" }} />
      <div className="resume-title">
        <h1>{resume.name}</h1>
        <p className="muted small">
          {resumeFor(resume)}
          {resume.parent_name && ` · made from ${resume.parent_name}`} · version{" "}
          {resume.head.number}
        </p>
      </div>

      {resume.parent_changes > 0 && !draft && (
        <ParentChanges
          base={base}
          parentName={resume.parent_name ?? "the resume it was made from"}
          count={resume.parent_changes}
          headId={resume.head.id}
          onTaken={setCurrent}
        />
      )}

      <div className="resume-actions">
        {draft ? (
          <>
            <button
              className="button primary"
              type="button"
              disabled={busy || !changed}
              onClick={save}
            >
              Save as version {resume.head.number + 1}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => {
                setDraft(null);
                setDraftPage(null);
                setError(null);
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              className="chip-button"
              type="button"
              onClick={() => setDraft(structuredClone(resume.content))}
            >
              <Icon icon={faPen} size={11} /> Change what shows
            </button>
            <button
              className="chip-button"
              type="button"
              aria-expanded={showVersions}
              onClick={() => setShowVersions((open) => !open)}
            >
              <Icon icon={faClockRotateLeft} size={11} /> Versions ({resume.versions.length})
            </button>
            <button className="chip-button" type="button" onClick={() => window.print()}>
              <Icon icon={faPrint} size={11} /> Print or PDF
            </button>
          </>
        )}
      </div>
      {draft && (
        <p className="muted small">
          Tap × to leave a line out, or open &ldquo;more lines on file&rdquo; to bring one in.
          Saving makes a new version; the old one stays.
        </p>
      )}
      {error && (
        <p className="panel attention" role="alert">
          {error}
        </p>
      )}

      {showVersions && !draft && (
        <Versions
          versions={resume.versions}
          headNumber={resume.head.number}
          base={base}
          busy={busy}
          onRestore={restore}
          onNamed={(detail) => setCurrent({ ...current, resume: detail })}
          act={act}
        />
      )}

      <ResumeDocument page={page} edit={edits} />

      {!draft && <MakeVersion base={base} resumeName={resume.name} />}
      <TabBar current="/resumes" />
    </main>
  );
}

function Versions({
  versions,
  headNumber,
  base,
  busy,
  onRestore,
  onNamed,
  act,
}: {
  versions: ResumeVersion[];
  headNumber: number;
  base: string;
  busy: boolean;
  onRestore: (number: number) => void;
  onNamed: (detail: ResumePage["resume"]) => void;
  act: <T>(action: string, body: unknown) => Promise<T | null>;
}) {
  const [naming, setNaming] = useState<number | null>(null);
  const [name, setName] = useState("");

  async function saveName(event: FormEvent) {
    event.preventDefault();
    if (naming === null || !name.trim()) return;
    const detail = await act<ResumePage["resume"]>("name", { number: naming, name: name.trim() });
    if (detail) {
      onNamed(detail);
      setNaming(null);
      setName("");
    }
  }

  return (
    <section className="panel versions" aria-label="Versions">
      <p className="muted small">
        Every change is kept. Bring any version back, or name the ones you send.
      </p>
      <ol className="version-list">
        {[...versions].reverse().map((v) => (
          <li key={v.id}>
            <div className="version-line">
              <b>{versionLabel(v)}</b>
              <span className="muted small">
                {versionAuthor(v)} · {when(v.created_at)}
                {v.note && ` · ${v.note}`}
              </span>
            </div>
            <div className="version-tools">
              {v.number !== headNumber && !v.redacted && (
                <>
                  <Link className="link small" href={`${base}?v=${v.number}`}>
                    See it
                  </Link>
                  <button
                    className="text-button small"
                    type="button"
                    disabled={busy}
                    onClick={() => onRestore(v.number)}
                  >
                    Bring back
                  </button>
                </>
              )}
              {v.number === headNumber && <span className="pill small teal">Now</span>}
              <button
                className="text-button small"
                type="button"
                disabled={busy}
                onClick={() => {
                  setNaming(v.number);
                  setName(v.names[0] ?? "");
                }}
              >
                Name it
              </button>
            </div>
            {naming === v.number && (
              <form className="version-name" onSubmit={saveName}>
                <label className="visually-hidden" htmlFor={`name-${v.number}`}>
                  Name for version {v.number}
                </label>
                <input
                  id={`name-${v.number}`}
                  value={name}
                  maxLength={120}
                  placeholder="Sent to Contoso"
                  onChange={(e) => setName(e.target.value)}
                />
                <button className="text-button small" type="submit" disabled={busy || !name.trim()}>
                  Save
                </button>
              </form>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function ParentChanges({
  base,
  parentName,
  count,
  headId,
  onTaken,
}: {
  base: string;
  parentName: string;
  count: number;
  headId: string;
  onTaken: (page: ResumePage) => void;
}) {
  const [changes, setChanges] = useState<LabeledChange[] | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function review() {
    setBusy(true);
    setError(null);
    const result = await send<LabeledChange[]>(`${base}/parent-changes`);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setChanges(result.data);
    setChosen(new Set(result.data.map((c) => c.change.key)));
  }

  async function take(keys: string[]) {
    setBusy(true);
    setError(null);
    const result = await send<ResumePage>(`${base}/take`, { keys, base_version_id: headId });
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onTaken(result.data);
  }

  return (
    <section className="panel parent-changes" aria-label="Changes to take">
      <p>
        <b>{parentName}</b> has {changesLabel(count)} since this version was made.
      </p>
      {error && (
        <p className="attention small" role="alert">
          {error}
        </p>
      )}
      {changes === null ? (
        <button className="text-button teal" type="button" disabled={busy} onClick={review}>
          See what changed
        </button>
      ) : (
        <>
          <ul className="change-list">
            {changes.map(({ change, label }) => (
              <li key={change.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={chosen.has(change.key)}
                    onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(change.key);
                      else next.delete(change.key);
                      setChosen(next);
                    }}
                  />
                  <span>{label}</span>
                </label>
              </li>
            ))}
          </ul>
          <div className="row wrap">
            <button
              className="button primary"
              type="button"
              disabled={busy || chosen.size === 0}
              onClick={() => take([...chosen])}
            >
              Take {chosen.size === changes.length ? "them" : changesLabel(chosen.size)}
            </button>
            <button className="text-button" type="button" disabled={busy} onClick={() => take([])}>
              Not these
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function MakeVersion({ base, resumeName }: { base: string; resumeName: string }) {
  const router = useRouter();
  const [forWhom, setForWhom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = forWhom.trim().length > 0;

  async function ask(event?: FormEvent) {
    event?.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    const result = await send(`${base}/ask`, { text: askText(resumeName, forWhom) });
    if (!result.ok) {
      setBusy(false);
      setError(result.error);
      return;
    }
    router.push("/talk");
  }

  async function copy() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    const result = await send<ResumePage>(`${base}/copy`, { target: forWhom });
    if (!result.ok) {
      setBusy(false);
      setError(result.error);
      return;
    }
    router.push(`/resumes/${encodeURIComponent(result.data.resume.id)}`);
  }

  return (
    <form className="panel make-version" onSubmit={ask}>
      <h2>Make a version for a role or company</h2>
      <p className="muted small">
        Plytos picks the jobs and lines that fit and words them for it. You keep it or change it,
        and this resume stays as it is.
      </p>
      <label className="label small" htmlFor="for-whom">
        Who is it for?
      </label>
      <input
        id="for-whom"
        value={forWhom}
        maxLength={TARGET_MAX}
        placeholder="Operations roles at fintech companies"
        onChange={(e) => setForWhom(e.target.value)}
      />
      {error && (
        <p className="attention small" role="alert">
          {error}
        </p>
      )}
      <div className="row wrap">
        <button className="button primary" type="submit" disabled={busy || !ready}>
          Ask Plytos
        </button>
        <button className="text-button" type="button" disabled={busy || !ready} onClick={copy}>
          Copy it and change it myself
        </button>
      </div>
    </form>
  );
}
