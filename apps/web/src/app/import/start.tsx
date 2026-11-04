"use client";

// Step 1, "Bring in": pick a way to begin, then watch the resume being read.
// The file goes to Plytos's own server, which keeps it encrypted with the
// person's key. Nothing becomes a card until they approve it.

import {
  faArrowRight,
  faCamera,
  faCheck,
  faCircleCheck,
  faHouse,
  faLock,
  faMicrophone,
  faNoteSticky,
  faPaperclip,
  faPlus,
  type IconDefinition,
} from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import { type ChangeEvent, type ReactNode, useRef, useState } from "react";

import { PageHead, SketchCard } from "../../components/hybrid";
import { Icon } from "../../components/icon";
import {
  FILENAME_HEADER,
  MAX_IMPORT_BYTES,
  MAX_PASTE_CHARS,
  plural,
  type Review,
} from "../../lib/imports";
import { Reading } from "./reading";

export type Unfinished = { id: string; name: string; left: number };

type Sending = {
  name: string;
  size: number;
  review: Review | null;
  error: string | null;
};

const ACCEPT =
  ".docx,.pdf,.txt,application/pdf,text/plain," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function fileProblem(file: File): string | null {
  const name = file.name.toLowerCase();
  if (name.endsWith(".doc")) {
    return "That's an older Word file. Save it as .docx or PDF first, then try again.";
  }
  if (!/\.(docx|pdf|txt)$/.test(name)) return "Plytos can read Word (.docx), PDF and text files.";
  if (file.size > MAX_IMPORT_BYTES) return "Resumes over 5 MB aren't supported.";
  if (file.size === 0) return "The file is empty.";
  return null;
}

export function Start({ unfinished }: { unfinished: Unfinished | null }) {
  const [mode, setMode] = useState<"start" | "paste">("start");
  const [sending, setSending] = useState<Sending | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const input = useRef<HTMLInputElement>(null);

  async function send(data: Blob, name: string) {
    setProblem(null);
    setSending({ name, size: data.size, review: null, error: null });
    window.scrollTo({ top: 0 });
    let review: Review | null = null;
    let error: string | null = null;
    try {
      const response = await fetch("/import/upload", {
        method: "POST",
        body: data,
        headers: {
          "Content-Type": "application/octet-stream",
          [FILENAME_HEADER]: encodeURIComponent(name),
        },
      });
      const body = (await response.json().catch(() => null)) as
        | (Review & { error?: string })
        | null;
      if (response.ok && body) review = body;
      else error = body?.error ?? "Plytos couldn't read that just now. Try again in a moment.";
    } catch {
      error = "The connection dropped. Check you're online and try again.";
    }
    setSending({ name, size: data.size, review, error });
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const issue = fileProblem(file);
    if (issue) {
      setProblem(issue);
      return;
    }
    void send(file, file.name);
  }

  if (sending) {
    return (
      <Reading
        name={sending.name}
        size={sending.size}
        review={sending.review}
        error={sending.error}
        onRetry={() => {
          setSending(null);
          setMode("start");
        }}
      />
    );
  }

  if (mode === "paste") {
    const tooLong = pasted.length > MAX_PASTE_CHARS;
    return (
      <main className="page">
        <PageHead back={{ onClick: () => setMode("start"), label: "Back" }} step={1} />
        <div className="stack tight">
          <h1 className="title">Paste your resume</h1>
          <p className="lede">
            Copy it from a document or your LinkedIn profile and paste it here. Plain text is fine.
          </p>
        </div>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (!pasted.trim() || tooLong) return;
            void send(new Blob([pasted], { type: "text/plain" }), "Pasted text.txt");
          }}
        >
          <label className="visually-hidden" htmlFor="paste">
            Your resume text
          </label>
          <textarea
            id="paste"
            className="paste-box"
            value={pasted}
            onChange={(event) => setPasted(event.target.value)}
            placeholder="Paste your resume here"
            rows={14}
            autoFocus
          />
          <p className={tooLong ? "note attention" : "note"} aria-live="polite">
            {tooLong
              ? `That's longer than Plytos can read at once. Trim it under ${MAX_PASTE_CHARS.toLocaleString()} characters.`
              : "Only you can see this. Nothing becomes a card until you say yes."}
          </p>
          <div className="dock">
            <button className="button primary" type="submit" disabled={!pasted.trim() || tooLong}>
              Read this
              <Icon icon={faArrowRight} size={16} />
            </button>
          </div>
        </form>
      </main>
    );
  }

  return (
    <main className="page">
      <PageHead back={{ href: "/cards", label: "Back to your cards" }} step={1} />
      <div className="stack tight">
        <h1 className="title">Let&apos;s start with what you already have.</h1>
        <p className="lede">
          You don&apos;t have to write anything from scratch. Give us an old resume and we&apos;ll
          turn it into cards for you to check.
        </p>
      </div>

      {unfinished && (
        <Link className="surface top-bar resume-banner" href={`/import/${unfinished.id}`}>
          <span className="resume-banner-text">
            <span className="label">Pick up where you left off</span>
            <span className="resume-banner-title">
              {plural(unfinished.left, "card")} waiting from {unfinished.name}
            </span>
          </span>
          <Icon icon={faArrowRight} size={16} className="teal" />
        </Link>
      )}

      <div className="start-art" aria-hidden="true">
        <div className="start-art-cards">
          <SketchCard kind="role" label="Role" className="ghost g1" />
          <SketchCard
            kind="result"
            label="Result"
            className="ghost g2"
            badge={
              <span className="sketch-check">
                <Icon icon={faCheck} size={8} />
              </span>
            }
          />
          <SketchCard kind="skill" label="Skill" className="ghost g3" />
          <SketchCard kind="people" label="People" className="ghost g4" />
        </div>
        <p className="start-art-caption">
          <span className="plus-dot">
            <Icon icon={faPlus} size={10} />
          </span>
          <span className="label medium">Your cards will appear here</span>
        </p>
      </div>

      <section className="stack" aria-labelledby="ways">
        <h2 className="label" id="ways">
          Pick one way to begin
        </h2>
        {problem && (
          <p className="alert" role="alert">
            {problem}
          </p>
        )}
        <input
          ref={input}
          className="visually-hidden"
          type="file"
          accept={ACCEPT}
          onChange={onFile}
          tabIndex={-1}
          aria-hidden="true"
        />
        <Way
          icon={faPaperclip}
          title="Upload a resume"
          detail="Word or PDF, up to 5 MB."
          badge={
            <span className="pill small outline-teal">
              <Icon icon={faCheck} size={8} />
              Fastest
            </span>
          }
          first
          onClick={() => input.current?.click()}
        />
        <Way
          icon={faNoteSticky}
          title="Paste text"
          detail="Copy it from a document or your LinkedIn profile."
          onClick={() => setMode("paste")}
        />
        <Way icon={faCamera} title="Take a photo" detail="Of a printed resume." soon />
        <Way icon={faMicrophone} title="Talk it through" detail="Tell us about your work." soon />
      </section>

      <section className="sand-panel stack" aria-labelledby="your-file">
        <div className="row start">
          <span className="circle-icon">
            <Icon icon={faLock} size={12} />
          </span>
          <h2 className="panel-title" id="your-file">
            What happens to your file
          </h2>
        </div>
        <ul className="promise-list">
          <li>
            <Icon icon={faCircleCheck} size={16} className="teal" />
            Only you can see it. Not shared, not public.
          </li>
          <li>
            <Icon icon={faCircleCheck} size={16} className="teal" />
            We keep the original, untouched and encrypted, until you delete it.
          </li>
          <li>
            <Icon icon={faCircleCheck} size={16} className="teal" />
            Nothing becomes a card until you say yes.
          </li>
        </ul>
      </section>

      <div className="stack tight center">
        <Link className="text-button" href="/cards">
          I&apos;m not ready. Skip for now
        </Link>
        <p className="note">
          <Icon icon={faHouse} size={11} />
          You can come back to this from your cards any time.
        </p>
      </div>
    </main>
  );
}

function Way({
  icon,
  title,
  detail,
  badge,
  first = false,
  soon = false,
  onClick,
}: {
  icon: IconDefinition;
  title: string;
  detail: string;
  badge?: ReactNode;
  first?: boolean;
  soon?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      className={`surface top-bar way${first ? " first" : ""}`}
      onClick={onClick}
      disabled={soon}
    >
      <span className="icon-tile">
        <Icon icon={icon} size={18} />
      </span>
      <span className="way-text">
        <span className="way-title">
          {title}
          {badge}
          {soon && <span className="pill small sand">Coming soon</span>}
        </span>
        <span className="way-detail">{detail}</span>
      </span>
      {!soon && <Icon icon={faArrowRight} size={16} className="teal" />}
    </button>
  );
}
