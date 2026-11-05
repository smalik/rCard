"use client";

import { Paperclip } from "lucide-react";

import { useCardActions } from "@/components/cards/actions";
import { AttachmentChips } from "@/components/cards/attachments";
import { CardBack } from "@/components/cards/card-back";
import { FIELDS } from "@/components/cards/fields";
import { type Purpose, StrengthCard } from "@/components/cards/strength-card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  cardDates,
  evidence,
  fact,
  headline,
  type LibraryCard,
  listFact,
} from "@/lib/library";
import { cn } from "@/lib/utils";

/** Three small pips: numbers, something to show, and a story. Filled ones
 * are there; the label says which. */
export function EvidencePips({ card, className }: { card: LibraryCard; className?: string }) {
  const e = evidence(card);
  const parts = [
    e.figures > 0 ? `${e.figures} ${e.figures === 1 ? "figure" : "figures"}` : "no figures",
    e.attachments > 0 ? `${e.attachments} attached` : "nothing attached",
  ];
  return (
    <span
      role="img"
      aria-label={`Evidence: ${parts.join(", ")}`}
      title={parts.join(" · ")}
      className={cn("inline-flex items-center gap-[3px]", className)}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            "size-[5px] rounded-full",
            i < e.level ? "bg-primary" : "bg-foreground/15",
          )}
        />
      ))}
    </span>
  );
}

function Figures({ card, className }: { card: LibraryCard; className?: string }) {
  const figures = listFact(card, "figures");
  if (figures.length === 0) return null;
  return (
    <ul className={cn("flex flex-wrap gap-1", className)} aria-label="Figures">
      {figures.map((f) => (
        <li
          key={f}
          className="rounded-md bg-accent px-1.5 py-px text-[12px] font-semibold text-accent-foreground tabular-nums"
        >
          {f}
        </li>
      ))}
    </ul>
  );
}

/** One accomplishment as a line on its job: the headline, its numbers, and
 * how well it is backed. Tapping it opens the card itself. */
export function AccomplishmentRow({
  card,
  onOpen,
  fresh,
  compact,
}: {
  card: LibraryCard;
  onOpen: (card: LibraryCard) => void;
  fresh?: boolean;
  // Two lines at most and no evidence, as while arranging.
  compact?: boolean;
}) {
  const attached = card.content?.attachments.length ?? 0;
  return (
    <button
      type="button"
      onClick={() => onOpen(card)}
      className={cn(
        "group flex w-full items-start gap-2.5 rounded-lg px-2 text-left transition-colors hover:bg-accent/60 focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none",
        compact ? "py-1.5" : "py-2",
        fresh && "animate-live-glow",
      )}
    >
      <span aria-hidden className="mt-[9px] size-[5px] shrink-0 rounded-full bg-foreground/45" />
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "block text-[14.5px] leading-[1.45] text-foreground/90",
            compact && "line-clamp-2",
          )}
        >
          {headline(card)}
        </span>
        <span className={cn("mt-1 flex flex-wrap items-center gap-2", compact && "hidden")}>
          <Figures card={card} />
          {attached > 0 && (
            <span className="inline-flex items-center gap-0.5 text-[12px] text-muted-foreground">
              <Paperclip className="size-3" aria-hidden />
              {attached}
              <span className="sr-only"> attached</span>
            </span>
          )}
        </span>
      </span>
      {!compact && <EvidencePips card={card} className="mt-2 opacity-70 group-hover:opacity-100" />}
    </button>
  );
}

/** A title's accomplishments while folded: a small stack of cards, the top
 * one readable, the rest peeking out below it. */
export function AccomplishmentPeek({
  items,
  onExpand,
}: {
  items: LibraryCard[];
  onExpand: () => void;
}) {
  const [top] = items;
  if (!top) return null;
  const more = items.length - 1;
  return (
    <button
      type="button"
      onClick={onExpand}
      className="group relative mb-2 block w-full text-left focus-visible:outline-none"
      aria-label={`Show ${items.length} ${items.length === 1 ? "accomplishment" : "accomplishments"}`}
    >
      {more > 1 && (
        <span
          aria-hidden
          className="absolute inset-x-4 top-2 -bottom-2 rounded-xl border bg-card/60 shadow-sheet"
        />
      )}
      {more > 0 && (
        <span
          aria-hidden
          className="absolute inset-x-2 top-1 -bottom-1 rounded-xl border bg-card/85 shadow-sheet"
        />
      )}
      <span className="relative flex items-center gap-2 rounded-xl border bg-card px-3 py-2.5 shadow-sheet transition-transform group-hover:-translate-y-px group-focus-visible:ring-[3px] group-focus-visible:ring-ring/40">
        <span className="line-clamp-1 flex-1 text-[13.5px] text-foreground/80">{headline(top)}</span>
        {more > 0 && (
          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground tabular-nums">
            +{more}
          </span>
        )}
      </span>
    </button>
  );
}

function purposeOf(card: LibraryCard): Purpose {
  if (card.kind === "project") return "project";
  if (fact(card, "award")) return "award";
  return "highlight";
}

/** An accomplishment as a whole card: the story on the front, its facts,
 * evidence and versions on the back. */
export function AccomplishmentCard({ card, className }: { card: LibraryCard; className?: string }) {
  const { now, fresh } = useCardActions();
  const purpose = purposeOf(card);
  const dates = cardDates(card);
  const fields = purpose === "award" ? FIELDS.award : card.kind === "project" ? FIELDS.project : FIELDS.accomplishment;
  return (
    <StrengthCard
      purpose={purpose}
      title={purpose === "highlight" ? "Accomplishment" : undefined}
      label={`Accomplishment: ${headline(card)}`}
      live={{
        version: card.version,
        updatedAt: card.updated_at,
        author: card.version_author,
        variantsBehind: card.variants_behind,
      }}
      now={now}
      fresh={fresh.has(card.id)}
      className={className}
      front={
        <div className="flex flex-col gap-3">
          <h3 className="text-[19px] leading-snug font-semibold tracking-[-0.015em] text-balance">
            {headline(card)}
          </h3>
          {card.content?.framing.body && (
            <p className="text-[15px] leading-relaxed whitespace-pre-line text-foreground/80">
              {card.content.framing.body}
            </p>
          )}
          <Figures card={card} />
          <AttachmentChips attachments={card.content?.attachments ?? []} />
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <EvidencePips card={card} />
            <span>{dates || "No date yet"}</span>
          </div>
        </div>
      }
      back={() => <CardBack card={card} fields={fields} />}
    />
  );
}

/** The accomplishment card, lifted out of its list like a card from a hand. */
export function AccomplishmentSheet({
  card,
  onClose,
}: {
  card: LibraryCard | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={card !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="border-0 bg-transparent p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-none sm:max-w-lg sm:p-0 [&>button:last-child]:hidden">
        <DialogTitle className="sr-only">{card ? headline(card) : "Accomplishment"}</DialogTitle>
        <DialogDescription className="sr-only">
          Turn the card over for its facts, evidence and versions.
        </DialogDescription>
        {card && <AccomplishmentCard card={card} className="shadow-lift" />}
      </DialogContent>
    </Dialog>
  );
}
