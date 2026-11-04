"use client";

// The conversation with Plytos. The person tells it what happened at work;
// Plytos answers, keeps the notes, and later offers wins it joined from them.
// Nothing becomes a card until the person keeps it.

import {
  faArrowUp,
  faCheck,
  faFileLines,
  faPaperclip,
  faPen,
} from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { useSyncExternalStore } from "react";

import { AppHeader, TabBar } from "../../components/hybrid";
import { Icon } from "../../components/icon";
import { HEADLINE_MAX } from "../../lib/cards";
import {
  ACCEPT_RESUME,
  FILENAME_HEADER,
  fileProblem,
  type ImportSummary,
} from "../../lib/imports";
import {
  AGENT_LABELS,
  awaitingReply,
  cleanMessage,
  fromNotes,
  groupByDay,
  MAX_MESSAGE,
  type Message,
  merge,
  monthLabel,
  type Proposal,
  resumeNext,
  resumeProgress,
  type Thread,
  withWording,
} from "../../lib/talk";

const CHECK_WHILE_WAITING_MS = 2_000;
const CHECK_WHILE_OPEN_MS = 20_000;

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

// Times and day names depend on where the person is, so they show once the
// page is running in their browser.
function useInBrowser(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

type Resumes = Record<string, ImportSummary>;

function byId(resumes: ImportSummary[]): Resumes {
  return Object.fromEntries(resumes.map((r) => [r.id, r]));
}

export function Talk({ initial, failed }: { initial: Thread; failed: boolean }) {
  const [thread, setThread] = useState(initial.messages);
  const [resumes, setResumes] = useState(() => byId(initial.resumes));
  const [clock, setClock] = useState(() => new Date());
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  // The name of a resume on its way to Plytos.
  const [sharing, setSharing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const inBrowser = useInBrowser();
  const busy = pending !== null || sharing !== null;
  const waiting = busy || awaitingReply(thread, clock);

  // Checks for Plytos's answer often while it's thinking, and now and then
  // otherwise, since the wins it joins arrive a little after a note.
  useEffect(() => {
    let stopped = false;
    const timer = window.setTimeout(
      async () => {
        if (!waiting && document.visibilityState !== "visible") {
          if (!stopped) setClock(new Date());
          return;
        }
        const fresh = await send<Thread>("/talk/messages");
        if (stopped) return;
        if (fresh.ok) {
          setThread((t) => merge(t, fresh.data.messages));
          setResumes(byId(fresh.data.resumes));
        }
        setClock(new Date());
      },
      waiting ? CHECK_WHILE_WAITING_MS : CHECK_WHILE_OPEN_MS,
    );
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [waiting, clock]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [thread.length, pending, sharing, waiting]);

  async function say(event?: FormEvent) {
    event?.preventDefault();
    const text = cleanMessage(draft);
    if (text === null || busy) return;
    setPending(text);
    setDraft("");
    setError(null);
    const saved = await send<Message>("/talk/messages", { text });
    if (saved.ok) {
      setThread((t) => merge(t, [saved.data]));
      setClock(new Date());
    } else {
      setDraft(text);
      setError(saved.error);
    }
    setPending(null);
  }

  async function share(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || busy) return;
    const problem = fileProblem(file);
    setError(problem);
    if (problem) return;
    setSharing(file.name);
    let result: Sent<{ messages: Message[]; resume: ImportSummary }>;
    try {
      const response = await fetch("/talk/resume", {
        method: "POST",
        body: file,
        headers: {
          "Content-Type": "application/octet-stream",
          [FILENAME_HEADER]: encodeURIComponent(file.name),
        },
      });
      const data = (await response.json().catch(() => null)) as
        | { messages: Message[]; resume: ImportSummary; error?: string }
        | null;
      result =
        response.ok && data
          ? { ok: true, data }
          : { ok: false, error: data?.error ?? "Plytos couldn't read that just now." };
    } catch {
      result = { ok: false, error: "The connection dropped. Check you're online and try again." };
    }
    if (result.ok) {
      const { messages, resume } = result.data;
      setResumes((r) => ({ ...r, [resume.id]: resume }));
      setThread((t) => merge(t, messages));
    } else {
      setError(result.error);
    }
    setSharing(null);
  }

  function pick() {
    picker.current?.click();
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void say();
    }
  }

  function decided(proposal: Proposal) {
    setThread((t) =>
      t.map((m) => (m.proposal?.id === proposal.id ? { ...m, proposal } : m)),
    );
  }

  const groups = inBrowser ? groupByDay(thread, clock) : [{ label: "", messages: thread }];

  return (
    <main className="talk">
      <header className="talk-head">
        <AppHeader />
        <p className="talk-status" aria-live="polite">
          {waiting ? (
            <>
              <span className="talk-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              {sharing !== null ? "Plytos is reading your resume" : "Plytos is reading your note"}
            </>
          ) : (
            "Tell it as it happens. I'll join your notes into wins."
          )}
        </p>
      </header>

      <section className="talk-thread" aria-label="Your conversation with Plytos">
        {failed && (
          <p className="panel attention" role="alert">
            Plytos couldn&apos;t load the conversation just now. Try again in a moment.
          </p>
        )}
        {!failed && thread.length === 0 && !busy && <Welcome onResume={pick} />}
        {groups.map((group, i) => (
          <div className="talk-day" key={group.label || i}>
            {group.label && <p className="talk-day-label">{group.label}</p>}
            {group.messages.map((m) => (
              <Line
                key={m.id}
                message={m}
                resume={m.import_id ? resumes[m.import_id] : undefined}
                onDecided={decided}
              />
            ))}
          </div>
        ))}
        {pending !== null && (
          <div className="said said-pending">
            <p>{pending}</p>
          </div>
        )}
        {sharing !== null && (
          <div className="said said-pending">
            <p className="said-file">
              <Icon icon={faFileLines} size={14} /> {sharing}
            </p>
          </div>
        )}
        {waiting && pending === null && (
          <div className="plytos thinking" aria-hidden="true">
            <span className="plytos-mark">P</span>
            <span className="talk-dots">
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
        <div ref={end} />
      </section>

      <form className="composer" onSubmit={say}>
        {error && (
          <p className="composer-error" role="alert">
            {error}
          </p>
        )}
        <button
          className="attach"
          type="button"
          aria-label="Share your resume"
          title="Share your resume"
          disabled={busy}
          onClick={pick}
        >
          <Icon icon={faPaperclip} size={16} />
        </button>
        <input
          ref={picker}
          className="visually-hidden"
          type="file"
          accept={ACCEPT_RESUME}
          tabIndex={-1}
          aria-hidden="true"
          onChange={share}
        />
        <label className="visually-hidden" htmlFor="say">
          Tell Plytos what happened
        </label>
        <textarea
          id="say"
          rows={1}
          value={draft}
          maxLength={MAX_MESSAGE}
          placeholder="Tell Plytos what happened…"
          enterKeyHint="send"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
        />
        <button
          className="send"
          type="submit"
          aria-label="Send"
          disabled={cleanMessage(draft) === null || busy}
        >
          <Icon icon={faArrowUp} size={16} />
        </button>
      </form>
      <TabBar current="/talk" />
    </main>
  );
}

function Welcome({ onResume }: { onResume: () => void }) {
  return (
    <div className="plytos">
      <span className="plytos-mark" aria-hidden="true">
        P
      </span>
      <div className="plytos-body">
        <p className="plytos-text">
          Hi. Tell me what happened at work: something you fixed, a number that moved, a thank-you
          you got. A sentence is plenty.
        </p>
        <p className="plytos-text">
          I&apos;ll keep every note as you wrote it. When a few of them add up to a win, I&apos;ll
          show it to you, and nothing becomes a card until you keep it.
        </p>
        <div className="talk-chips">
          <button className="talk-chip" type="button" onClick={onResume}>
            Start from my resume
          </button>
        </div>
      </div>
    </div>
  );
}

function Line({
  message,
  resume,
  onDecided,
}: {
  message: Message;
  resume: ImportSummary | undefined;
  onDecided: (p: Proposal) => void;
}) {
  if (message.author === "person") {
    return (
      <div className="said">
        <p>{message.text}</p>
        {resume && (
          <p className="said-file">
            <Icon icon={faFileLines} size={14} /> {resume.file.name}
          </p>
        )}
      </div>
    );
  }
  const proposal = message.proposal;
  const quiet = proposal && (proposal.state === "dismissed" || proposal.state === "superseded");
  if (proposal && quiet) return <Settled proposal={proposal} />;
  return (
    <div className="plytos">
      <span className="plytos-mark" aria-hidden="true">
        P
      </span>
      <div className="plytos-body">
        <p className="plytos-text">{message.text}</p>
        {resume && <ResumeCard resume={resume} />}
        {proposal?.body.card && <Offer proposal={proposal} onDecided={onDecided} />}
        {proposal && (
          <p className="trail">
            How I got here · {AGENT_LABELS[proposal.agent]}
            {fromNotes(proposal) && `, ${fromNotes(proposal)}`}
          </p>
        )}
      </div>
    </div>
  );
}

// A resume shared in the conversation: what was read, and the next step.
function ResumeCard({ resume }: { resume: ImportSummary }) {
  const next = resumeNext(resume);
  return (
    <article className="resume-card" aria-label="Your resume">
      <p className="resume-file">
        <Icon icon={faFileLines} size={14} />
        <span>{resume.file.name}</span>
      </p>
      <p className="resume-progress">{resumeProgress(resume)}</p>
      <div className="offer-actions">
        <Link className="keep" href={next.href}>
          {next.label}
        </Link>
        {next.href !== `/import/${encodeURIComponent(resume.id)}` && (
          <Link className="quiet" href={`/import/${encodeURIComponent(resume.id)}`}>
            See what I read
          </Link>
        )}
      </div>
    </article>
  );
}

// A suggestion the person passed on, or one a fuller draft replaced.
function Settled({ proposal }: { proposal: Proposal }) {
  const headline = proposal.body.card?.content.framing.headline ?? proposal.body.message;
  return (
    <p className="settled">
      {proposal.state === "dismissed" ? "You passed on " : "Replaced by a fuller draft: "}
      <span>{headline}</span>
    </p>
  );
}

function Offer({ proposal, onDecided }: { proposal: Proposal; onDecided: (p: Proposal) => void }) {
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
  const open = proposal.state === "open";
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

  const wording = headline.trim();
  if (!open) {
    const shown = proposal.state === "kept" ? framing.headline : keptWording;
    return (
      <article className="offer offer-kept" aria-label="Kept win">
        <p className="offer-kind">
          <span>{proposal.state === "kept" ? "Kept" : "Kept in your words"}</span>
          <em>
            <Icon icon={faCheck} size={9} /> In your cards
          </em>
        </p>
        {shown && <h3>{shown}</h3>}
        <Link className="offer-link" href="/cards">
          See it in your cards
        </Link>
      </article>
    );
  }
  return (
    <article className="offer" aria-label="Suggested win">
      <p className="offer-kind">
        <span>
          Accomplishment{proposal.cites.length > 1 && ` · from ${proposal.cites.length} notes`}
        </span>
      </p>
      {editing ? (
        <div className="offer-edit">
          <label className="label small" htmlFor={`h-${proposal.id}`}>
            Headline
          </label>
          <textarea
            id={`h-${proposal.id}`}
            value={headline}
            maxLength={HEADLINE_MAX}
            rows={3}
            onChange={(e) => setHeadline(e.target.value)}
          />
          <label className="label small" htmlFor={`b-${proposal.id}`}>
            More context (optional)
          </label>
          <textarea
            id={`b-${proposal.id}`}
            value={body}
            rows={2}
            onChange={(e) => setBody(e.target.value)}
          />
        </div>
      ) : (
        <>
          <h3>{framing.headline}</h3>
          {framing.body && <p className="offer-body">{framing.body}</p>}
        </>
      )}
      {(typeof date === "string" || Array.isArray(figures)) && !editing && (
        <p className="offer-meta">
          {typeof date === "string" && <span>{monthLabel(date)}</span>}
          {Array.isArray(figures) &&
            figures.map((f) => (
              <span className="figure" key={f}>
                {f}
              </span>
            ))}
        </p>
      )}
      {card.missing && !editing && (
        <p className="offer-gap">
          <b>Still open:</b> {card.missing} <span>Answer below and I&apos;ll add it.</span>
        </p>
      )}
      {error && (
        <p className="offer-error" role="alert">
          {error}
        </p>
      )}
      {!editing && (
        <div className="offer-actions">
          <button className="keep" type="button" disabled={busy} onClick={() => decide("keep")}>
            Keep it
          </button>
          <button className="soft" type="button" disabled={busy} onClick={() => setEditing(true)}>
            <Icon icon={faPen} size={11} /> Edit
          </button>
          <button
            className="quiet"
            type="button"
            disabled={busy}
            onClick={() => decide("dismiss")}
          >
            Not this
          </button>
        </div>
      )}
      {editing && (
        <div className="offer-actions">
          <button
            className="keep"
            type="button"
            disabled={busy || !wording}
            onClick={() => decide("keep", withWording(card, headline, body))}
          >
            Keep my wording
          </button>
          <button
            className="quiet"
            type="button"
            disabled={busy}
            onClick={() => {
              setEditing(false);
              setHeadline(framing.headline);
              setBody(framing.body);
            }}
          >
            Cancel
          </button>
        </div>
      )}
    </article>
  );
}
