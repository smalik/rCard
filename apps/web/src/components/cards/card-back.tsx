"use client";

import { Bot, Check, History, User } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { AttachmentEditor } from "@/components/cards/attachments";
import { type CardVersion, useCardActions } from "@/components/cards/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { FactValue } from "@/lib/cards";
import { type Attachment, type LibraryCard, relativeTime } from "@/lib/library";
import { cn } from "@/lib/utils";

export type Field = {
  key: string;
  label: string;
  placeholder?: string;
  // A list fact, edited as comma-separated text.
  list?: boolean;
  // Half width on wider cards, for dates and short values.
  half?: boolean;
};

function asText(value: FactValue | undefined, list?: boolean): string {
  if (value === undefined) return "";
  if (Array.isArray(value)) return value.join(list ? ", " : " ");
  return String(value);
}

function fromText(text: string, list?: boolean): FactValue | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  if (!list) return trimmed;
  return trimmed
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

const AUTHORS = { person: "You", ai: "Plytos", reviewer: "A reviewer" } as const;

/** The back of a card: its facts, how it's worded, what's attached, and every
 * version kept. Saving makes the next version; nothing is overwritten. */
export function CardBack({
  card,
  fields,
  wording = true,
  headlineLabel = "Headline",
  headlineFrom,
  story = { label: "The story", placeholder: "What you did, how, and what changed because of it." },
}: {
  card: LibraryCard;
  fields: Field[];
  // Shows the headline and story fields.
  wording?: boolean;
  headlineLabel?: string;
  // A fact the headline follows, such as the employer's name, when the card's
  // front shows that fact instead. The headline field is then left out.
  headlineFrom?: string;
  story?: { label: string; placeholder: string };
}) {
  const { save, history, now } = useCardActions();
  const content = card.content;
  const [facts, setFacts] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.key, asText(content?.facts[f.key], f.list)])),
  );
  const [headline, setHeadline] = useState(content?.framing.headline ?? "");
  const [body, setBody] = useState(content?.framing.body ?? "");
  const [attachments, setAttachments] = useState<Attachment[]>(content?.attachments ?? []);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<CardVersion[] | null>(null);

  // The history again whenever the card moves on to a new version.
  const { id, version_id: head } = card;
  useEffect(() => {
    let live = true;
    history(id)
      .then((v) => live && setVersions(v))
      .catch(() => live && setVersions([]));
    return () => {
      live = false;
    };
  }, [id, head, history]);

  if (!content) {
    return <p className="text-[14px] text-muted-foreground">This card&apos;s text was removed.</p>;
  }

  const nextFacts: Record<string, FactValue> = { ...content.facts };
  for (const f of fields) {
    const value = fromText(facts[f.key] ?? "", f.list);
    if (value === undefined) delete nextFacts[f.key];
    else nextFacts[f.key] = value;
  }
  const followed = headlineFrom ? nextFacts[headlineFrom] : undefined;
  const nextHeadline =
    typeof followed === "string" && followed ? followed : headline.trim();
  const dirty =
    JSON.stringify(nextFacts) !== JSON.stringify(content.facts) ||
    nextHeadline !== content.framing.headline ||
    body.trim() !== content.framing.body ||
    JSON.stringify(attachments) !== JSON.stringify(content.attachments);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!content || !dirty || !nextHeadline) return;
    setState("saving");
    setError(null);
    try {
      await save(card, {
        ...content,
        facts: nextFacts,
        framing: { ...content.framing, headline: nextHeadline, body: body.trim() },
        attachments,
      });
      setState("saved");
    } catch (e) {
      setState("idle");
      setError(e instanceof Error ? e.message : "That didn't save. Try again.");
    }
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={submit}>
      {fields.length > 0 && (
        <fieldset className="grid grid-cols-2 gap-x-3 gap-y-3">
          <legend className="sr-only">Facts</legend>
          {fields.map((f) => (
            <div key={f.key} className={cn("grid gap-1.5", f.half ? "col-span-1" : "col-span-2")}>
              <Label htmlFor={`${card.id}-${f.key}`}>{f.label}</Label>
              <Input
                id={`${card.id}-${f.key}`}
                value={facts[f.key] ?? ""}
                placeholder={f.placeholder}
                onChange={(e) => {
                  setState("idle");
                  setFacts({ ...facts, [f.key]: e.target.value });
                }}
              />
            </div>
          ))}
        </fieldset>
      )}

      {wording && (
        <fieldset className="grid gap-3">
          <legend className="sr-only">Wording</legend>
          <div className={cn("grid gap-1.5", headlineFrom && "hidden")}>
            <Label htmlFor={`${card.id}-headline`}>{headlineLabel}</Label>
            {/* One line of text that wraps as it grows; Return saves. */}
            <Textarea
              id={`${card.id}-headline`}
              value={headline}
              maxLength={200}
              rows={1}
              className="min-h-0 font-medium"
              aria-invalid={!headline.trim()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              onChange={(e) => {
                setState("idle");
                setHeadline(e.target.value.replace(/\s*\n\s*/g, " "));
              }}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${card.id}-body`}>{story.label}</Label>
            <Textarea
              id={`${card.id}-body`}
              value={body}
              maxLength={5000}
              placeholder={story.placeholder}
              onChange={(e) => {
                setState("idle");
                setBody(e.target.value);
              }}
            />
          </div>
        </fieldset>
      )}

      <AttachmentEditor
        attachments={attachments}
        onChange={(next) => {
          setState("idle");
          setAttachments(next);
        }}
      />

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!dirty || !nextHeadline || state === "saving"}>
          {state === "saving" ? "Saving…" : "Save as next version"}
        </Button>
        {state === "saved" && !dirty && (
          <span role="status" className="flex items-center gap-1 text-[13px] text-primary">
            <Check className="size-4" /> Saved
          </span>
        )}
        {error && (
          <span role="alert" className="text-[13px] text-destructive">
            {error}
          </span>
        )}
      </div>

      <section className="flex flex-col gap-2" aria-label="Versions">
        <h4 className="flex items-center gap-1.5 text-[13px] font-semibold">
          <History className="size-3.5 text-muted-foreground" /> Every version, kept
        </h4>
        {versions === null ? (
          <p className="text-[13px] text-muted-foreground">Loading…</p>
        ) : (
          <ol className="flex flex-col gap-1">
            {[...versions].reverse().map((v) => (
              <li key={v.id} className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <span className="w-8 font-mono text-[11px] font-medium text-foreground/75">
                  v{v.number}
                </span>
                {v.author_kind === "ai" ? (
                  <Bot className="size-3.5" aria-hidden />
                ) : (
                  <User className="size-3.5" aria-hidden />
                )}
                <span>{AUTHORS[v.author_kind]}</span>
                <span aria-hidden>·</span>
                <time dateTime={v.created_at}>{relativeTime(v.created_at, now)}</time>
                {v.redacted && <span>· text removed</span>}
              </li>
            ))}
          </ol>
        )}
      </section>
    </form>
  );
}
