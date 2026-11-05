"use client";

import { ArrowUpDown, Check, ChevronsDownUp, ChevronsUpDown, Ellipsis, MapPin } from "lucide-react";
import { type ReactNode, useState } from "react";

import {
  AccomplishmentPeek,
  AccomplishmentRow,
} from "@/components/cards/accomplishment";
import { useCardActions } from "@/components/cards/actions";
import { AttachmentChips } from "@/components/cards/attachments";
import { CardBack } from "@/components/cards/card-back";
import { FIELDS } from "@/components/cards/fields";
import { SortableList } from "@/components/cards/sortable-list";
import { DisclosureTriangle, StrengthCard } from "@/components/cards/strength-card";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  cardDates,
  type EngagementView,
  type ExperienceView,
  fact,
  headline,
  type LibraryCard,
  type PositionView,
  tenure,
} from "@/lib/library";
import { cn } from "@/lib/utils";

// A title or a client, with what was done there and any client work under it.
type Block = { card: LibraryCard; items: LibraryCard[]; client?: boolean; within: Block[] };

const clientBlock = (e: EngagementView): Block => ({
  card: e.card,
  items: e.items,
  client: true,
  within: [],
});

/** The employer's own titles and clients, in the person's order. */
function blocksOf(view: ExperienceView): Block[] {
  const fromPosition = (p: PositionView): Block => ({
    card: p.card,
    items: p.items,
    within: p.engagements.map(clientBlock),
  });
  return [...view.positions.map(fromPosition), ...view.engagements.map(clientBlock)];
}

function allBlocks(blocks: Block[]): Block[] {
  return blocks.flatMap((b) => [b, ...allBlocks(b.within)]);
}

function blockTitle(block: Block): string {
  if (block.client) {
    const client = fact(block.card, "client");
    const title = fact(block.card, "title");
    return client && title ? `${client} · ${title}` : client || title || headline(block.card);
  }
  return fact(block.card, "title") || headline(block.card);
}

/** One title at the employer, or one client: a disclosure row with its
 * accomplishments under it, folded into a small stack until opened. */
function RoleBlock({
  block,
  opened,
  onToggle,
  arranging,
  onOpen,
  controls,
}: {
  block: Block;
  opened: ReadonlySet<string>;
  onToggle: (id: string) => void;
  arranging: boolean;
  onOpen: (card: LibraryCard) => void;
  // The handle and arrows that move this title, while arranging.
  controls?: ReactNode;
}) {
  const { reorder, fresh } = useCardActions();
  const open = opened.has(block.card.id);
  const plain = fact(block.card, "plain_title");
  const dates = cardDates(block.card);
  const regionId = `role-${block.card.id}`;
  return (
    <div className={cn("relative pl-5", fresh.has(block.card.id) && "animate-live-glow rounded-lg")}>
      {/* A node on the employer's timeline. */}
      <span
        aria-hidden
        className="absolute top-[13px] left-[3px] size-[9px] rounded-full border-2 border-card bg-kind-position ring-1 ring-kind-position/40"
      />
      <div className="flex items-start gap-1">
        <button
          type="button"
          onClick={() => onToggle(block.card.id)}
          aria-expanded={open}
          aria-controls={regionId}
          className="grid min-w-0 flex-1 grid-cols-[12px_minmax(0,1fr)] items-start gap-x-2 rounded-lg py-1.5 pr-1 text-left focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none sm:grid-cols-[12px_minmax(0,1fr)_auto] sm:gap-x-3"
        >
          <DisclosureTriangle open={open} className="mt-[5px]" />
          <span className="min-w-0">
            <span className="text-[15.5px] leading-[22px] font-semibold tracking-[-0.01em]">
              {blockTitle(block)}
            </span>
            {block.client && (
              <span className="ml-2 rounded-full bg-muted px-1.5 py-px align-[1px] text-[11px] font-medium text-muted-foreground">
                Client
              </span>
            )}
            {plain && <span className="block text-[13px] text-muted-foreground">{plain}</span>}
            {dates && (
              <span className="block text-[13px] text-muted-foreground tabular-nums sm:hidden">
                {dates}
              </span>
            )}
          </span>
          {dates && (
            <span className="hidden pt-px text-[13px] leading-[22px] text-muted-foreground tabular-nums sm:block">
              {dates}
            </span>
          )}
        </button>
        {controls}
      </div>
      <div id={regionId}>
        {open ? (
          block.items.length > 0 ? (
            <div className="mt-1 mb-2 rounded-xl bg-muted/55 p-1 dark:bg-muted/40">
              <SortableList
                items={block.items}
                id={(c) => c.id}
                name={headline}
                arranging={arranging}
                label={`Accomplishments as ${blockTitle(block)}`}
                onReorder={(next) => void reorder(block.card.id, next.map((c) => c.id))}
                className="flex flex-col"
                render={(card) => (
                  <AccomplishmentRow
                    card={card}
                    onOpen={onOpen}
                    fresh={fresh.has(card.id)}
                    compact={arranging}
                  />
                )}
              />
            </div>
          ) : (
            <p className="mb-2 pl-5 text-[13px] text-muted-foreground">
              No accomplishments here yet.
            </p>
          )
        ) : (
          <div className="mt-1 pl-0.5">
            <AccomplishmentPeek items={block.items} onExpand={() => onToggle(block.card.id)} />
          </div>
        )}
        {open && block.within.length > 0 && (
          <SortableList
            items={block.within}
            id={(b) => b.card.id}
            name={blockTitle}
            arranging={arranging}
            label={`Client work as ${blockTitle(block)}`}
            onReorder={(next) => void reorder(block.card.id, next.map((b) => b.card.id))}
            className="flex flex-col gap-0.5"
            controls="inline"
            render={(inner, _, handles) => (
              <RoleBlock
                controls={handles}
                block={inner}
                opened={opened}
                onToggle={onToggle}
                arranging={arranging}
                onOpen={onOpen}
              />
            )}
          />
        )}
      </div>
    </div>
  );
}

/** Work experience: one employer and everything done there, titles in
 * order on a timeline, each title's accomplishments stacked under it. */
export function ExperienceCard({
  view,
  onOpen,
  className,
}: {
  view: ExperienceView;
  onOpen: (card: LibraryCard) => void;
  className?: string;
}) {
  const { reorder, now, fresh } = useCardActions();
  const blocks = blocksOf(view);
  const every = allBlocks(blocks).map((b) => b.card.id);
  // The latest title starts open; the rest start folded into their stacks.
  const [open, setOpen] = useState<ReadonlySet<string>>(
    () => new Set(blocks.slice(0, 1).map((b) => b.card.id)),
  );
  const [arranging, setArranging] = useState(false);
  const card = view.card;
  const employer = fact(card, "employer") || headline(card);
  const former = fact(card, "former_employer");
  const where = [fact(card, "location"), fact(card, "employment_type")].filter(Boolean).join(" · ");
  const start = fact(card, "start");
  const end = fact(card, "end");
  const span = cardDates(card);
  const length = tenure(start, end, now);
  const allOpen = every.every((id) => open.has(id));

  const toggle = (id: string) => {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpen(next);
  };

  const menu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="More for this card"
          className="grid size-8 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
        >
          <Ellipsis className="size-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          onSelect={() => {
            setArranging(!arranging);
            if (!arranging) setOpen(new Set(every));
          }}
        >
          <ArrowUpDown /> {arranging ? "Done arranging" : "Arrange titles and accomplishments"}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => setOpen(allOpen ? new Set() : new Set(every))}
        >
          {allOpen ? <ChevronsDownUp /> : <ChevronsUpDown />}
          {allOpen ? "Fold every title" : "Open every title"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <StrengthCard
      purpose="experience"
      label={`Work experience: ${employer}`}
      live={{
        version: card.version,
        updatedAt: card.updated_at,
        author: card.version_author,
        variantsBehind: card.variants_behind,
      }}
      now={now}
      fresh={fresh.has(card.id)}
      menu={menu}
      className={className}
      front={
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
            <div className="min-w-0">
              <h3 className="text-[23px] leading-tight font-semibold tracking-[-0.02em]">
                {employer}
              </h3>
              {former && <p className="text-[13px] text-muted-foreground">formerly {former}</p>}
              {where && (
                <p className="mt-0.5 flex items-center gap-1 text-[13.5px] text-muted-foreground">
                  <MapPin className="size-3.5" aria-hidden />
                  {where}
                </p>
              )}
            </div>
            {span && (
              <p className="text-[13.5px] text-muted-foreground tabular-nums sm:text-right">
                <span className="font-medium text-foreground/80">{span}</span>
                {length && (
                  <span className="text-[12px] before:mx-1.5 before:content-['·'] sm:block sm:before:hidden">
                    {length}
                  </span>
                )}
              </p>
            )}
          </div>
          <AttachmentChips attachments={card.content?.attachments ?? []} />

          {arranging && (
            <div className="flex items-center justify-between rounded-xl bg-accent px-3 py-2 text-[13px] text-accent-foreground">
              <span>Drag the handles, or use the arrows, to put these in order.</span>
              <Button size="sm" variant="ghost" onClick={() => setArranging(false)}>
                <Check /> Done
              </Button>
            </div>
          )}

          {blocks.length > 0 && (
            <div className="relative">
              {/* The employer's timeline, joining its titles in order. */}
              <span
                aria-hidden
                className="absolute top-4 bottom-4 left-[7px] w-px bg-border"
              />
              <SortableList
                items={blocks}
                id={(b) => b.card.id}
                name={blockTitle}
                arranging={arranging}
                label={`Titles at ${employer}`}
                onReorder={(next) =>
                  void reorder(
                    card.id,
                    next.map((b) => b.card.id),
                  )
                }
                className="flex flex-col gap-0.5"
                controls="inline"
                render={(block, _, handles) => (
                  <RoleBlock
                    controls={handles}
                    block={block}
                    opened={open}
                    onToggle={toggle}
                    arranging={arranging}
                    onOpen={onOpen}
                  />
                )}
              />
            </div>
          )}

          {view.items.length > 0 && (
            <div>
              <h4 className="mb-1 text-[12px] font-semibold tracking-[0.02em] text-muted-foreground uppercase">
                Across roles
              </h4>
              <div className="rounded-xl bg-muted/55 p-1 dark:bg-muted/40">
                <SortableList
                  items={view.items}
                  id={(c) => c.id}
                  name={headline}
                  arranging={arranging}
                  label={`Accomplishments across roles at ${employer}`}
                  onReorder={(next) => void reorder(card.id, next.map((c) => c.id))}
                  className="flex flex-col"
                  render={(item) => (
                    <AccomplishmentRow
                      card={item}
                      onOpen={onOpen}
                      fresh={fresh.has(item.id)}
                      compact={arranging}
                    />
                  )}
                />
              </div>
            </div>
          )}
        </div>
      }
      back={() => (
        <CardBack
          card={card}
          fields={FIELDS.employment}
          headlineFrom="employer"
          story={{
            label: "About this job",
            placeholder: "What the company does, and what you were brought in to do.",
          }}
        />
      )}
    />
  );
}
