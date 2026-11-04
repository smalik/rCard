"use client";

// Editing a proposed card before approving it: the wording is the person's to
// change freely; facts change only on purpose, in their own section.

import { faLock, faXmark } from "@fortawesome/free-solid-svg-icons";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Icon } from "../../../../components/icon";
import type { CardContent, FactValue } from "../../../../lib/cards";
import {
  contentProblems,
  editableFacts,
  FACT_HINTS,
  factLabel,
  factToText,
  textToFact,
} from "../../../../lib/imports";

export function Editor({
  content,
  busy,
  error,
  onCancel,
  onSave,
  onLeaveOut,
}: {
  content: CardContent;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (content: CardContent) => void;
  onLeaveOut: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const editable = editableFacts(content);
  const [headline, setHeadline] = useState(content.framing.headline);
  const [body, setBody] = useState(content.framing.body);
  const [facts, setFacts] = useState<Record<string, string>>(() =>
    Object.fromEntries(editable.map(([key, value]) => [key, factToText(value)])),
  );
  const [problems, setProblems] = useState<string[]>([]);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => element?.close();
  }, []);

  function build(): CardContent {
    const out: Record<string, FactValue> = {};
    for (const [key, value] of Object.entries(content.facts)) {
      const edited = facts[key];
      if (edited === undefined) {
        out[key] = value;
        continue;
      }
      const fact = textToFact(edited, value);
      if (fact !== undefined) out[key] = fact;
    }
    return { facts: out, framing: { ...content.framing, headline, body } };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const edited = build();
    const found = contentProblems(edited);
    setProblems(found);
    if (found.length === 0) onSave(edited);
  }

  return (
    <dialog
      ref={dialog}
      className="sheet-dialog"
      aria-labelledby="edit-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form className="stack" onSubmit={submit} noValidate>
        <div className="row">
          <h2 className="section-title" id="edit-title">
            Edit this card
          </h2>
          <button type="button" className="round-button" aria-label="Close" onClick={onCancel}>
            <Icon icon={faXmark} size={14} />
          </button>
        </div>

        <p className="label small">Wording · yours to reword any time</p>
        <label className="field">
          <span className="field-label">Headline</span>
          <textarea rows={2} value={headline} onChange={(e) => setHeadline(e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">More detail</span>
          <textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
        </label>

        {editable.length > 0 && (
          <>
            <p className="label small">
              <Icon icon={faLock} size={10} />
              Facts · change only on purpose
            </p>
            {editable.map(([key]) => (
              <label key={key} className="field">
                <span className="field-label">{factLabel(key)}</span>
                <input
                  value={facts[key] ?? ""}
                  onChange={(e) => setFacts({ ...facts, [key]: e.target.value })}
                />
                {FACT_HINTS[key] && <span className="field-hint">{FACT_HINTS[key]}</span>}
              </label>
            ))}
          </>
        )}

        {(problems.length > 0 || error) && (
          <div className="alert" role="alert">
            {[...problems, ...(error ? [error] : [])].map((problem) => (
              <p key={problem}>{problem}</p>
            ))}
          </div>
        )}

        <button className="button primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save and approve"}
        </button>
        <button className="text-button danger" type="button" disabled={busy} onClick={onLeaveOut}>
          Leave this card out
        </button>
      </form>
    </dialog>
  );
}
