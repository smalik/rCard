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
import { type Attachment, type LibraryCard, type LibraryContent, relativeTime } from "@/lib/library";
import { cn } from "@/lib/utils";

export type Field = {
  key: string;
  label: string;
  placeholder?: string;
  // A list fact, edited one item per line, since items such as "1,200" can
  // hold commas.
  list?: boolean;
  // Half width on wider cards, for dates and short values.
  half?: boolean;
};

function asText(value: FactValue | undefined, list?: boolean): string {
  if (value === undefined) return "";
  if (Array.isArray(value)) return value.join(list ? "\n" : " ");
  return String(value);
}

function fromText(text: string, list?: boolean): FactValue | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  if (!list) return trimmed;
  return trimmed
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

type Draft = {
  facts: Record<string, string>;
  headline: string;
  body: string;
  attachments: Attachment[];
};

function draftOf(card: LibraryCard, fields: Field[]): Draft {
  const content = card.content;
  return {
    facts: Object.fromEntries(fields.map((f) => [f.key, asText(content?.facts[f.key], f.list)])),
    headline: content?.framing.headline ?? "",
    body: content?.framing.body ?? "",
    attachments: content?.attachments ?? [],
  };
}

/** The content a draft would save over `base`. A fact whose text wasn't
 * touched keeps its value exactly as stored. */
function contentOf(
  draft: Draft,
  base: LibraryCard,
  fields: Field[],
  headlineFrom: string | undefined,
  standIn: string | undefined,
): LibraryContent | null {
  const content = base.content;
  if (!content) return null;
  const facts: Record<string, FactValue> = { ...content.facts };
  for (const f of fields) {
    const text = draft.facts[f.key] ?? "";
    if (text === asText(content.facts[f.key], f.list)) continue;
    const value = fromText(text, f.list);
    if (value === undefined) delete facts[f.key];
    else facts[f.key] = value;
  }
  const followed = headlineFrom ? facts[headlineFrom] : undefined;
  let headline = typeof followed === "string" && followed ? followed : draft.headline.trim();
  if (standIn) {
    // A headline that only repeats the fact follows it when the fact changes.
    const was = content.facts[standIn];
    const now = facts[standIn];
    const standing =
      typeof was === "string" && content.framing.headline.trim().toLowerCase() === was.trim().toLowerCase();
    if (standing && typeof now === "string" && now) headline = now;
  }
  return {
    ...content,
    facts,
    framing: {
      ...content.framing,
      headline,
      body: draft.body.trim(),
    },
    attachments: draft.attachments,
  };
}

// JSON with object keys sorted, so the same facts compare equal in any order.
function stable(value: unknown): string {
  return JSON.stringify(value, (_, v: unknown) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([x], [y]) => x.localeCompare(y)))
      : v,
  );
}

function sameContent(a: LibraryContent | null, b: LibraryContent | null): boolean {
  if (!a || !b) return a === b;
  return (
    stable(a.facts) === stable(b.facts) &&
    a.framing.headline === b.framing.headline &&
    a.framing.body === b.framing.body &&
    stable(a.attachments) === stable(b.attachments)
  );
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
  standIn,
  story = { label: "Detail", placeholder: "How you did it, and what changed because of it." },
}: {
  card: LibraryCard;
  fields: Field[];
  // Shows the headline and story fields.
  wording?: boolean;
  headlineLabel?: string;
  // A fact the headline follows, such as the employer's name, when the card's
  // front shows that fact instead. The headline field is then left out.
  headlineFrom?: string;
  // A fact the headline stands in with until someone writes one, such as a
  // job's employer before its headline sums it up. The headline is edited on
  // the front, so its field is left out here; a stand-in follows the fact.
  standIn?: string;
  story?: { label: string; placeholder: string };
}) {
  const { save, history, now } = useCardActions();
  // The version the edits started from. Saving names it, so a change made
  // meanwhile elsewhere (another tab, an import) is refused, not overwritten.
  const [base, setBase] = useState(card);
  const [draft, setDraft] = useState(() => draftOf(card, fields));
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

  const next = contentOf(draft, base, fields, headlineFrom, standIn);
  const dirty = !sameContent(next, base.content);

  // When the card moves on, follow it unless there are edits to keep. Our own
  // save comes back as the very content we sent, so that is followed too.
  if (card.version_id !== base.version_id && (!dirty || sameContent(next, card.content))) {
    setBase(card);
    setDraft(draftOf(card, fields));
  }
  const movedOn = card.version_id !== base.version_id;

  const content = base.content;
  if (!content || !next) {
    return <p className="text-[14px] text-muted-foreground">This card&apos;s text was removed.</p>;
  }
  const nextHeadline = next.framing.headline;

  function edit(change: Partial<Draft>) {
    setState("idle");
    setDraft({ ...draft, ...change });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!next || !dirty || !nextHeadline) return;
    setState("saving");
    setError(null);
    try {
      await save(base, next);
      setState("saved");
    } catch (e) {
      setState("idle");
      setError(e instanceof Error ? e.message : "That didn't save. Try again.");
    }
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={submit}>
      {movedOn && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-live-soft px-3 py-2 text-[13px]"
        >
          <span>This card changed somewhere else while you were editing it.</span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setBase(card);
              setDraft(draftOf(card, fields));
              setState("idle");
              setError(null);
            }}
          >
            Load the latest
          </Button>
        </div>
      )}
      {fields.length > 0 && (
        <fieldset className="grid grid-cols-2 gap-x-3 gap-y-3">
          <legend className="sr-only">Facts</legend>
          {fields.map((f) => (
            <div key={f.key} className={cn("grid gap-1.5", f.half ? "col-span-1" : "col-span-2")}>
              <Label htmlFor={`${card.id}-${f.key}`}>
                {f.label}
                {f.list && <span className="font-normal text-muted-foreground">, one per line</span>}
              </Label>
              {f.list ? (
                <Textarea
                  id={`${card.id}-${f.key}`}
                  value={draft.facts[f.key] ?? ""}
                  placeholder={f.placeholder?.split(", ").join("\n")}
                  rows={2}
                  className="min-h-0"
                  onChange={(e) => edit({ facts: { ...draft.facts, [f.key]: e.target.value } })}
                />
              ) : (
                <Input
                  id={`${card.id}-${f.key}`}
                  value={draft.facts[f.key] ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) => edit({ facts: { ...draft.facts, [f.key]: e.target.value } })}
                />
              )}
            </div>
          ))}
        </fieldset>
      )}

      {wording && (
        <fieldset className="grid gap-3">
          <legend className="sr-only">Wording</legend>
          <div className={cn("grid gap-1.5", (headlineFrom || standIn) && "hidden")}>
            <Label htmlFor={`${card.id}-headline`}>{headlineLabel}</Label>
            {/* One line of text that wraps as it grows; Return saves. */}
            <Textarea
              id={`${card.id}-headline`}
              value={draft.headline}
              maxLength={200}
              rows={1}
              className="min-h-0 font-medium"
              aria-invalid={!draft.headline.trim()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              onChange={(e) => edit({ headline: e.target.value.replace(/\s*\n\s*/g, " ") })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${card.id}-body`}>{story.label}</Label>
            <Textarea
              id={`${card.id}-body`}
              value={draft.body}
              maxLength={5000}
              placeholder={story.placeholder}
              onChange={(e) => edit({ body: e.target.value })}
            />
          </div>
        </fieldset>
      )}

      <AttachmentEditor
        attachments={draft.attachments}
        onChange={(attachments) => edit({ attachments })}
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
