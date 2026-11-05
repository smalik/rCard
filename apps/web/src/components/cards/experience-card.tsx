"use client";

import {
  ArrowUpDown,
  Check,
  ChevronsDownUp,
  ChevronsUpDown,
  Ellipsis,
  MapPin,
  Pencil,
} from "lucide-react";
import { type ReactNode, useState } from "react";

import { AccomplishmentPeek, AccomplishmentRow } from "@/components/cards/accomplishment";
import { useCardActions } from "@/components/cards/actions";
import { AttachmentChips } from "@/components/cards/attachments";
import { CardBack } from "@/components/cards/card-back";
import { FIELDS } from "@/components/cards/fields";
import { SortableList } from "@/components/cards/sortable-list";
import { DisclosureTriangle, StrengthCard } from "@/components/cards/strength-card";
import { type RewriteTargets, RewriteButton, WrittenText } from "@/components/cards/written";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  bySortKey,
  cardDates,
  type EngagementView,
  type ExperienceView,
  fact,
  headline,
  type LibraryCard,
  type PositionView,
  tenure,
  writtenBy,
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
  // Titles and clients share one order, so a client can sit above a title.
  return [...view.positions.map(fromPosition), ...view.engagements.map(clientBlock)].sort((a, b) =>
    bySortKey(a.card, b.card),
  );
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

/** What a rewrite would touch: the headline, when there's anything to sum
 * up, and the story of each title with accomplishments; and how many of
 * those are the person's own words. */
function rewriteTargets(view: ExperienceView, blocks: Block[]): RewriteTargets {
  const titles = allBlocks(blocks).filter((b) => b.items.length > 0);
  const any = titles.length > 0 || view.items.length > 0;
  const headlineOwn = any && writtenBy(view.card, "headline") === "person" ? 1 : 0;
  return {
    parts: (any ? 1 : 0) + titles.length,
    own: headlineOwn + titles.filter((b) => writtenBy(b.card, "body") === "person").length,
  };
}

function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "text-[11.5px] font-semibold tracking-[0.04em] text-muted-foreground uppercase",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A title's facts and story on their own, to change its dates or wording. */
function TitleEditor({
  block,
  open,
  onOpenChange,
}: {
  block: Block;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{blockTitle(block)}</DialogTitle>
          <DialogDescription>
            Its dates, team and story. Saving keeps every earlier version.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <CardBack
            card={block.card}
            fields={block.client ? FIELDS.engagement : FIELDS.position}
            headlineFrom={block.client ? "client" : "title"}
            story={{
              label: "The story",
              placeholder: "Leave it empty and Plytos writes it from the accomplishments.",
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** One title at the employer, or one client: a section that opens to its
 * story and accomplishments, and folds into a small stack. */
function RoleBlock({
  block,
  opened,
  onToggle,
  arranging,
  writing,
  onOpen,
  controls,
}: {
  block: Block;
  opened: ReadonlySet<string>;
  onToggle: (id: string) => void;
  arranging: boolean;
  // Plytos is summing the job up now.
  writing: boolean;
  onOpen: (card: LibraryCard) => void;
  // The handle and arrows that move this title, while arranging.
  controls?: ReactNode;
}) {
  const { reorder, fresh } = useCardActions();
  const [editing, setEditing] = useState(false);
  const open = opened.has(block.card.id);
  const plain = fact(block.card, "plain_title");
  const dates = cardDates(block.card);
  const story = block.card.content?.framing.body.trim() ?? "";
  const regionId = `role-${block.card.id}`;
  const title = blockTitle(block);
  return (
    <div className={cn("relative pl-5", fresh.has(block.card.id) && "animate-live-glow rounded-inset")}>
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
          className="grid min-w-0 flex-1 grid-cols-[12px_minmax(0,1fr)] items-start gap-x-2 rounded-inset py-1.5 pr-1 text-left focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none sm:grid-cols-[12px_minmax(0,1fr)_auto] sm:gap-x-3"
        >
          <DisclosureTriangle open={open} className="mt-[5px]" />
          <span className="min-w-0">
            <span className="text-[15.5px] leading-[22px] font-semibold tracking-[-0.01em]">
              {title}
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
        {open && !arranging && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            aria-label={`Edit ${title}: dates, team and story`}
            className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
          >
            <Pencil className="size-3.5" />
          </button>
        )}
        {controls}
      </div>
      <TitleEditor block={block} open={editing} onOpenChange={setEditing} />
      <div id={regionId}>
        {open ? (
          <div className="mt-1 mb-3 flex flex-col gap-2.5">
            {!arranging && (
              <div className="flex flex-col gap-1 pl-5">
                <SectionLabel>The story</SectionLabel>
                <WrittenText
                  card={block.card}
                  part="body"
                  label={`The story as ${title}`}
                  writing={writing}
                  ready={block.items.length > 0}
                  empty={
                    block.items.length > 0
                      ? "No story yet. Plytos writes one from the accomplishments below."
                      : "Add accomplishments and Plytos tells the story of this title here."
                  }
                  textClassName="text-[14.5px] leading-relaxed text-foreground/85"
                />
              </div>
            )}
            {block.items.length > 0 ? (
              <div className="rounded-inset bg-muted/55 p-1 dark:bg-muted/40">
                <SortableList
                  items={block.items}
                  id={(c) => c.id}
                  name={headline}
                  arranging={arranging}
                  label={`Accomplishments as ${title}`}
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
              <p className="pl-5 text-[13px] text-muted-foreground">No accomplishments here yet.</p>
            )}
          </div>
        ) : (
          <div className="mt-0.5 pl-0.5">
            {story && (
              <p className="mb-2 line-clamp-2 pl-[18px] text-[13.5px] leading-snug text-muted-foreground">
                {story}
              </p>
            )}
            <AccomplishmentPeek items={block.items} onExpand={() => onToggle(block.card.id)} />
          </div>
        )}
        {open && block.within.length > 0 && (
          <SortableList
            items={block.within}
            id={(b) => b.card.id}
            name={blockTitle}
            arranging={arranging}
            label={`Client work as ${title}`}
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
                writing={writing}
                onOpen={onOpen}
              />
            )}
          />
        )}
      </div>
    </div>
  );
}

/** Work experience: one employer as one card in sections. On top, the
 * employer and the headline that sums up the whole stint; then a section per
 * title, on a timeline, with its story and accomplishments; then the wins
 * that span titles. The card folds to its top, and each section folds too. */
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
  const [folded, setFolded] = useState(false);
  const [acrossOpen, setAcrossOpen] = useState(true);
  const [arranging, setArranging] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const card = view.card;
  const employer = fact(card, "employer") || headline(card);
  const former = fact(card, "former_employer");
  const where = [fact(card, "location"), fact(card, "employment_type")].filter(Boolean).join(" · ");
  const start = fact(card, "start");
  const end = fact(card, "end");
  const span = cardDates(card);
  const length = tenure(start, end, now);
  const allOpen = every.every((id) => open.has(id));
  const writing = Boolean(card.writing) || rewriting;
  const targets = rewriteTargets(view, blocks);
  const things = allBlocks(blocks).reduce((n, b) => n + b.items.length, 0) + view.items.length;
  const titleCount = allBlocks(blocks).length;
  const sectionsId = `job-${card.id}`;

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
            if (!arranging) {
              setFolded(false);
              setOpen(new Set(every));
            }
          }}
        >
          <ArrowUpDown /> {arranging ? "Done arranging" : "Arrange titles and accomplishments"}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            setFolded(false);
            setOpen(allOpen ? new Set() : new Set(every));
          }}
        >
          {allOpen ? <ChevronsDownUp /> : <ChevronsUpDown />}
          {allOpen ? "Fold every title" : "Open every title"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  const summary = [
    titleCount > 0 ? `${titleCount} ${titleCount === 1 ? "title" : "titles"}` : "",
    things > 0 ? `${things} ${things === 1 ? "accomplishment" : "accomplishments"}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

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
          {/* The employer, and the headline that sums up every title there. */}
          <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2">
              <button
                type="button"
                onClick={() => setFolded(!folded)}
                aria-expanded={!folded}
                aria-controls={sectionsId}
                aria-label={folded ? `Open ${employer}` : `Fold ${employer}`}
                className="-ml-1 mt-[7px] grid size-6 shrink-0 place-items-center rounded-md focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
              >
                <DisclosureTriangle open={!folded} />
              </button>
              <div className="flex min-w-0 flex-1 flex-wrap items-end justify-between gap-x-4 gap-y-1">
                <div className="min-w-0">
                  <h3 className="text-[23px] leading-tight font-semibold tracking-[-0.02em]">
                    {employer}
                  </h3>
                  {former && (
                    <p className="text-[13px] text-muted-foreground">formerly {former}</p>
                  )}
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
            </div>

            <div className="flex flex-col gap-1.5 pl-6">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
                <SectionLabel>Headline</SectionLabel>
                <RewriteButton
                  jobId={card.id}
                  employer={employer}
                  targets={targets}
                  onBusy={setRewriting}
                />
              </div>
              <WrittenText
                card={card}
                part="headline"
                label={`Headline for ${employer}`}
                writing={writing}
                ready={targets.parts > 0}
                empty={
                  targets.parts > 0
                    ? "No headline yet. Plytos sums up the whole job from its accomplishments."
                    : "Add accomplishments and Plytos sums up the whole job here."
                }
                textClassName="text-[17px] leading-snug font-medium tracking-[-0.01em] text-foreground/90"
              />
            </div>
            <AttachmentChips attachments={card.content?.attachments ?? []} />
          </div>

          {folded ? (
            summary && (
              <button
                type="button"
                onClick={() => setFolded(false)}
                className="-mt-1 self-start rounded-full border bg-muted/50 px-3 py-1 text-[12.5px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
              >
                Show {summary}
              </button>
            )
          ) : (
            <div id={sectionsId} className="flex flex-col gap-4">
              {arranging && (
                <div className="flex items-center justify-between rounded-inset bg-accent px-3 py-2 text-[13px] text-accent-foreground">
                  <span>Drag the handles, or use the arrows, to put these in order.</span>
                  <Button size="sm" variant="ghost" onClick={() => setArranging(false)}>
                    <Check /> Done
                  </Button>
                </div>
              )}

              {blocks.length > 0 && (
                <div className="relative border-t pt-3">
                  {/* The employer's timeline, joining its titles in order. */}
                  <span
                    aria-hidden
                    className="absolute top-7 bottom-4 left-[7px] w-px bg-border"
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
                        writing={writing}
                        onOpen={onOpen}
                      />
                    )}
                  />
                </div>
              )}

              {view.items.length > 0 && (
                <div className="border-t pt-3">
                  <button
                    type="button"
                    onClick={() => setAcrossOpen(!acrossOpen)}
                    aria-expanded={acrossOpen}
                    aria-controls={`${sectionsId}-across`}
                    className="mb-1.5 flex items-center gap-2 rounded-md text-left focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
                  >
                    <DisclosureTriangle open={acrossOpen} />
                    <SectionLabel>Across titles</SectionLabel>
                    <span className="text-[12px] text-muted-foreground tabular-nums">
                      {view.items.length}
                    </span>
                  </button>
                  <div id={`${sectionsId}-across`}>
                    {acrossOpen ? (
                      <div className="rounded-inset bg-muted/55 p-1 dark:bg-muted/40">
                        <SortableList
                          items={view.items}
                          id={(c) => c.id}
                          name={headline}
                          arranging={arranging}
                          label={`Accomplishments across titles at ${employer}`}
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
                    ) : (
                      <AccomplishmentPeek items={view.items} onExpand={() => setAcrossOpen(true)} />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      }
      back={() => (
        <CardBack
          card={card}
          fields={FIELDS.employment}
          standIn="employer"
          story={{
            label: "About the employer",
            placeholder: "What the company does. Plytos reads this when it sums up the job.",
          }}
        />
      )}
    />
  );
}
