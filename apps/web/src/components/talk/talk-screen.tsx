"use client";

// The conversation with Plytos. The person tells it what happened at work;
// Plytos answers, keeps the notes, and later offers wins it joined from them.
// A resume shared here is gone through here too: the questions, then each job.
// Nothing becomes a card until the person keeps it.

import { ArrowUp, Paperclip } from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { Button } from "@/components/ui/button";
import { ACCEPT_RESUME, FILENAME_HEADER, fileProblem, type ImportSummary } from "@/lib/imports";
import { activeImport } from "@/lib/review";
import {
  awaitingReply,
  type CheckIns,
  type CheckInSlot,
  cleanMessage,
  fromNotes,
  groupByDay,
  MAX_MESSAGE,
  type Message,
  merge,
  nextCheckInLabel,
  offerCheckIns,
  type Proposal,
  readingShared,
  type Thread,
  AGENT_LABELS,
} from "@/lib/talk";

import { DayLabel, PersonSays, PlytosMark, PlytosSays, Replies, Reply, Thinking } from "./bubbles";
import { CheckInOffer, CheckInSettings, type Plan } from "./check-ins";
import { ImportReview, type ReviewCounts } from "./import-review";
import { ResumeOffer, Settled, SharedResume, WinOffer } from "./offers";
import { type Sent, send } from "./send";

const CHECK_WHILE_WAITING_MS = 2_000;
const CHECK_WHILE_OPEN_MS = 20_000;

// Times and day names depend on where the person is, so they show once the
// page is running in their browser.
function useInBrowser(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

function timeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

type Resumes = Record<string, ImportSummary>;

function byId(resumes: ImportSummary[]): Resumes {
  return Object.fromEntries(resumes.map((r) => [r.id, r]));
}

// The resume to go through, and whether to go back to what was set aside.
type Going = { id: string; goBack: boolean } | null;

export function TalkScreen({
  initial,
  failed,
  asked,
  madeFrom,
}: {
  initial: Thread;
  failed: boolean;
  // A resume the person came here to go through (?review=).
  asked: string | null;
  // The resume made from each file, by import id.
  madeFrom: Record<string, string>;
}) {
  const [thread, setThread] = useState(initial.messages);
  const [resumes, setResumes] = useState(() => byId(initial.resumes));
  const [checkIns, setCheckIns] = useState<CheckIns>(initial.check_ins);
  const [planning, setPlanning] = useState(false);
  const [clock, setClock] = useState(() => new Date());
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  // The name of a resume on its way to Plytos.
  const [sharing, setSharing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [going, setGoing] = useState<Going>(() => {
    const active = activeImport(initial.resumes, asked);
    return active ? { id: active.id, goBack: active.id === asked } : null;
  });
  const end = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const inBrowser = useInBrowser();
  const busy = pending !== null || sharing !== null;
  const readingResume = sharing !== null || readingShared(thread, resumes);
  const waiting = busy || readingResume || awaitingReply(thread, clock);

  // The newest resume with cards to decide when the page opened. One shared
  // since, once it's read, is the one to go through next.
  const [since, setSince] = useState(() => activeImport(initial.resumes, null)?.created_at ?? "");
  const newest = activeImport(Object.values(resumes), null);
  if (newest && newest.created_at > since) {
    setSince(newest.created_at);
    setGoing({ id: newest.id, goBack: false });
  }
  const current = going ? resumes[going.id] : undefined;
  const reviewing = going !== null && current !== undefined && current.state === "read";

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
          setCheckIns(fresh.data.check_ins);
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

  const toEnd = useCallback(() => {
    window.requestAnimationFrame(() => end.current?.scrollIntoView({ block: "end" }));
  }, []);

  // Day labels appear once the page runs in the browser, so it scrolls again then.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [thread.length, pending, sharing, waiting, inBrowser, going?.id]);

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

  const plan: Plan = async (slot: CheckInSlot, state = "on") => {
    const saved = await send<{ check_ins: CheckIns; message: Message }>("/talk/check-ins", {
      ...slot,
      state,
      time_zone: timeZone(),
    });
    if (!saved.ok) return saved.error;
    setCheckIns(saved.data.check_ins);
    setThread((t) => merge(t, [saved.data.message]));
    setPlanning(false);
    return null;
  };

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void say();
    }
  }

  function decided(proposal: Proposal) {
    setThread((t) => t.map((m) => (m.proposal?.id === proposal.id ? { ...m, proposal } : m)));
  }

  function counted(id: string, counts: ReviewCounts) {
    setResumes((r) => (r[id] ? { ...r, [id]: { ...r[id]!, ...counts } } : r));
  }

  function goThrough(id: string, goBack: boolean) {
    setGoing({ id, goBack });
    toEnd();
  }

  const groups = inBrowser ? groupByDay(thread, clock) : [{ label: "", messages: thread }];

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col px-4 sm:px-6">
      <h1 className="sr-only">Talk with Plytos</h1>
      <header className="sticky top-0 z-30 -mx-4 border-b border-border/60 bg-background/85 px-4 py-2.5 backdrop-blur-xl backdrop-saturate-150 sm:-mx-6 sm:px-6 md:top-14">
        <div className="flex items-center gap-3">
          <PlytosMark className="size-9 text-[15px]" />
          <div className="min-w-0 flex-1">
            <p className="text-[16px] leading-tight font-semibold">Plytos</p>
            <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground" aria-live="polite">
              {waiting ? (
                readingResume ? (
                  "Reading your resume…"
                ) : (
                  "Reading your note…"
                )
              ) : checkIns.plan ? (
                <>
                  <span className="truncate">
                    {checkIns.plan.state === "on"
                      ? inBrowser && checkIns.next_at
                        ? `Next check-in ${nextCheckInLabel(checkIns.next_at)}`
                        : "Monthly check-ins"
                      : "Check-ins are off"}
                  </span>
                  <button
                    type="button"
                    aria-expanded={planning}
                    onClick={() => setPlanning((open) => !open)}
                    className="shrink-0 font-medium text-primary"
                  >
                    {checkIns.plan.state === "on" ? "Change" : "Turn on"}
                  </button>
                </>
              ) : (
                "Tell it as it happens. I'll join your notes into wins."
              )}
            </p>
          </div>
        </div>
        {planning && checkIns.plan && (
          <CheckInSettings checkIns={checkIns} onPlan={plan} onClose={() => setPlanning(false)} />
        )}
      </header>

      <section aria-label="Your conversation with Plytos" className="flex flex-col gap-3 pt-4 pb-3">
        {failed && (
          <p role="alert" className="rounded-2xl border bg-card px-4 py-3 text-[14px] shadow-sheet">
            Plytos couldn&apos;t load the conversation just now. Try again in a moment.
          </p>
        )}
        {!failed && thread.length === 0 && !busy && <Welcome onResume={pick} />}
        {groups.map((group, i) => (
          <div className="flex flex-col gap-3" key={group.label || i}>
            {group.label && <DayLabel>{group.label}</DayLabel>}
            {group.messages.map((m) => {
              const resume = m.import_id ? resumes[m.import_id] : undefined;
              return (
                <Line
                  key={m.id}
                  message={m}
                  resume={resume}
                  reviewing={reviewing && resume?.id === going?.id}
                  resumeId={resume ? (madeFrom[resume.id] ?? null) : null}
                  onGoThrough={(goBack) => resume && goThrough(resume.id, goBack)}
                  onDecided={decided}
                />
              );
            })}
          </div>
        ))}
        {pending !== null && <PersonSays pending>{pending}</PersonSays>}
        {sharing !== null && <PersonSays pending file={sharing} />}
        {!failed && !reviewing && offerCheckIns(thread, checkIns, waiting) && (
          <CheckInOffer onPlan={plan} />
        )}
        {reviewing && (
          <ImportReview
            key={`${going!.id}-${going!.goBack}`}
            importId={going!.id}
            goBack={going!.goBack}
            resumeId={madeFrom[going!.id] ?? null}
            onCounts={counted}
            onAdvance={toEnd}
          />
        )}
        {waiting && pending === null && <Thinking />}
        <div ref={end} className="scroll-mb-32" />
      </section>

      <form
        onSubmit={say}
        className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-20 -mx-4 flex flex-col gap-1.5 bg-gradient-to-t from-background from-70% to-transparent px-4 pt-4 pb-3 sm:-mx-6 sm:px-6 md:bottom-0 md:pb-6"
      >
        {error && (
          <p role="alert" className="px-2 text-[13px] text-destructive">
            {error}
          </p>
        )}
        <div className="flex items-end gap-1.5 rounded-[24px] border bg-card p-1.5 shadow-card">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Share your resume"
            title="Share your resume"
            disabled={busy}
            onClick={pick}
            className="text-muted-foreground"
          >
            <Paperclip />
          </Button>
          <input
            ref={picker}
            className="sr-only"
            type="file"
            accept={ACCEPT_RESUME}
            tabIndex={-1}
            aria-hidden="true"
            onChange={share}
          />
          <label className="sr-only" htmlFor="say">
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
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-[1.35] outline-none [field-sizing:content] placeholder:text-muted-foreground"
          />
          <Button
            type="submit"
            size="icon"
            aria-label="Send"
            disabled={cleanMessage(draft) === null || busy}
          >
            <ArrowUp strokeWidth={2.5} />
          </Button>
        </div>
      </form>
    </main>
  );
}

function Welcome({ onResume }: { onResume: () => void }) {
  return (
    <PlytosSays
      attached={
        <Replies>
          <Reply onClick={onResume}>Start from my resume</Reply>
        </Replies>
      }
    >
      <p>
        Hi. Tell me what happened at work: something you fixed, a number that moved, a thank-you
        you got. A sentence is plenty.
      </p>
      <p className="mt-2">
        I&apos;ll keep every note as you wrote it. When a few of them add up to a win, I&apos;ll show
        it to you, and nothing becomes a card until you keep it.
      </p>
    </PlytosSays>
  );
}

function Line({
  message,
  resume,
  reviewing,
  resumeId,
  onGoThrough,
  onDecided,
}: {
  message: Message;
  resume: ImportSummary | undefined;
  reviewing: boolean;
  resumeId: string | null;
  onGoThrough: (goBack: boolean) => void;
  onDecided: (p: Proposal) => void;
}) {
  if (message.author === "person") {
    return <PersonSays file={resume?.file.name}>{message.text}</PersonSays>;
  }
  const proposal = message.proposal;
  if (proposal && (proposal.state === "dismissed" || proposal.state === "superseded")) {
    return <Settled proposal={proposal} />;
  }
  return (
    <PlytosSays
      attached={
        <>
          {resume && (
            <SharedResume
              resume={resume}
              reviewing={reviewing}
              resumeId={resumeId}
              onGoThrough={onGoThrough}
            />
          )}
          {proposal?.body.card && <WinOffer proposal={proposal} onDecided={onDecided} />}
          {proposal?.body.resume && <ResumeOffer proposal={proposal} onDecided={onDecided} />}
          {proposal && (
            <p className="text-[12px] text-muted-foreground">
              How I got here · {AGENT_LABELS[proposal.agent]}
              {fromNotes(proposal) && `, ${fromNotes(proposal)}`}
            </p>
          )}
        </>
      }
    >
      {message.text}
    </PlytosSays>
  );
}
