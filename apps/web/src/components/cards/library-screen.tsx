"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useMemo, useState } from "react";

import { AccomplishmentCard, AccomplishmentSheet } from "@/components/cards/accomplishment";
import { type CardActions, CardActionsProvider, type CardVersion } from "@/components/cards/actions";
import { ExperienceCard } from "@/components/cards/experience-card";
import {
  ActivityCard,
  AwardCard,
  ContactCard,
  CredentialCard,
  EducationCard,
  ProjectCard,
  SkillsCard,
} from "@/components/cards/section-cards";
import { KindTile, type Purpose } from "@/components/cards/strength-card";
import { type Sync, useLiveLibrary } from "@/components/cards/use-live-library";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  buildLibrary,
  type LibraryCard,
  type LibraryContent,
  listFact,
  relativeTime,
  withOrder,
} from "@/lib/library";
import type { ResumeHeader } from "@/lib/resumes";
import { cn } from "@/lib/utils";

export type Contact = {
  resumeId: string;
  resumeName: string;
  baseVersionId: string;
  header: ResumeHeader;
};

async function failure(response: Response): Promise<Error> {
  try {
    const body = (await response.json()) as { error?: string };
    return new Error(body.error ?? "That didn't work. Try again in a moment.");
  } catch {
    return new Error("That didn't work. Try again in a moment.");
  }
}

function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function LiveStatus({ sync, syncedAt, now }: { sync: Sync; syncedAt: Date; now: Date }) {
  return (
    <span
      role="status"
      className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-[12.5px] text-muted-foreground shadow-sheet"
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          sync === "offline" ? "bg-muted-foreground/50" : "animate-live-dot bg-primary",
        )}
      />
      {sync === "offline"
        ? "Offline · showing what was here"
        : sync === "syncing"
          ? "Live · checking"
          : `Live · checked ${relativeTime(syncedAt.toISOString(), now)}`}
    </span>
  );
}

function Section({
  id,
  purpose,
  title,
  count,
  children,
  className,
}: {
  id: string;
  purpose: Purpose;
  title: string;
  count?: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("scroll-mt-24", className)}>
      <h2
        id={`${id}-title`}
        className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-[0.03em] text-muted-foreground uppercase"
      >
        <KindTile purpose={purpose} className="size-5 rounded-[6px] [&_svg]:size-3" />
        {title}
        {count !== undefined && <span className="font-normal tabular-nums">{count}</span>}
      </h2>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

/** The person's cards, live: work experience as the hero column, and the
 * cards that give it context beside it on wider screens. */
export function LibraryScreen({
  initial,
  contact: initialContact,
}: {
  initial: LibraryCard[];
  contact: Contact | null;
}) {
  const { cards, fresh, sync, syncedAt, refresh, arrange } = useLiveLibrary(initial);
  const [contact, setContact] = useState(initialContact);
  const [openId, setOpenId] = useState<string | null>(null);
  const now = syncedAt;
  const view = useMemo(() => buildLibrary(cards), [cards]);
  const byId = useMemo(() => new Map(cards.map((c) => [c.id, c])), [cards]);

  // How many accomplishments show each skill, for the skills cards.
  const shownIn = useMemo(() => {
    const texts = cards
      .filter((c) => c.kind === "accomplishment" || c.kind === "project")
      .map((c) =>
        [c.content?.framing.headline, c.content?.framing.body, ...listFact(c, "skills")]
          .join(" ")
          .toLowerCase(),
      );
    return (skill: string) => {
      const needle = skill.toLowerCase();
      return texts.filter((t) => t.includes(needle)).length;
    };
  }, [cards]);

  const save = useCallback(
    async (card: LibraryCard, content: LibraryContent) => {
      const response = await post(`/cards/${card.id}`, {
        base_version_id: card.version_id,
        content,
      });
      if (!response.ok) throw await failure(response);
      await refresh();
    },
    [refresh],
  );

  const reorder = useCallback(
    async (parentId: string | null, ids: string[]) => {
      arrange((all) => withOrder(all, parentId, ids));
      const response = await post("/cards/reorder", { parent_id: parentId, card_ids: ids });
      if (!response.ok) await refresh();
    },
    [arrange, refresh],
  );

  const history = useCallback(async (id: string) => {
    const response = await fetch(`/cards/${id}/history`, { cache: "no-store" });
    if (!response.ok) throw await failure(response);
    return (await response.json()) as CardVersion[];
  }, []);

  const actions: CardActions = useMemo(
    () => ({ save, reorder, history, fresh, now }),
    [save, reorder, history, fresh, now],
  );

  async function saveContact(header: ResumeHeader) {
    if (!contact) return;
    const response = await post("/cards/contact", {
      resume_id: contact.resumeId,
      base_version_id: contact.baseVersionId,
      header,
    });
    if (!response.ok) throw await failure(response);
    const { base_version_id } = (await response.json()) as { base_version_id: string };
    setContact({ ...contact, header, baseVersionId: base_version_id });
  }

  const context = [
    { id: "education", purpose: "education" as const, title: "Education", cards: view.education },
    { id: "awards", purpose: "award" as const, title: "Awards and accolades", cards: view.awards },
    {
      id: "certifications",
      purpose: "credential" as const,
      title: "Certifications",
      cards: view.credentials,
    },
    { id: "skills", purpose: "skill" as const, title: "Skills", cards: view.skills },
    { id: "projects", purpose: "project" as const, title: "Projects", cards: view.projects },
    { id: "activities", purpose: "activity" as const, title: "Activities", cards: view.activities },
    { id: "highlights", purpose: "highlight" as const, title: "Highlights", cards: view.highlights },
  ].filter((s) => s.cards.length > 0);

  const card = (id: string, card: LibraryCard) => {
    switch (id) {
      case "education":
        return <EducationCard key={card.id} card={card} />;
      case "awards":
        return <AwardCard key={card.id} card={card} />;
      case "certifications":
        return <CredentialCard key={card.id} card={card} />;
      case "skills":
        return <SkillsCard key={card.id} card={card} shownIn={shownIn} />;
      case "projects":
        return <ProjectCard key={card.id} card={card} />;
      case "activities":
        return <ActivityCard key={card.id} card={card} />;
      default:
        return <AccomplishmentCard key={card.id} card={card} />;
    }
  };

  // The sections beside work experience, each with a rough height.
  const side = [
    ...(contact
      ? [
          {
            weight: 2.5,
            node: (
              <Section key="contact" id="contact" purpose="contact" title="Contact">
                <ContactCard header={contact.header} from={contact.resumeName} onSave={saveContact} />
              </Section>
            ),
          },
        ]
      : []),
    ...context.map((s) => ({
      weight: 0.5 + s.cards.length,
      node: (
        <Section key={s.id} id={s.id} purpose={s.purpose} title={s.title} count={s.cards.length}>
          {s.cards.map((c) => card(s.id, c))}
        </Section>
      ),
    })),
  ];
  // On a tablet they sit in two columns: the first sections on the left, the
  // rest on the right, split near half the height. The split comes from the
  // data, so turning a card over never moves a section to the other column;
  // a single column reads in the same order.
  const total = side.reduce((sum, s) => sum + s.weight, 0);
  let split = 0;
  for (let before = 0; split < side.length; split++) {
    const weight = side[split]!.weight;
    if (before + weight / 2 > total / 2) break;
    before += weight;
  }

  const jumps = [
    ...(view.experience.length ? [{ id: "experience", label: "Experience" }] : []),
    ...(contact ? [{ id: "contact", label: "Contact" }] : []),
    ...context.map((s) => ({ id: s.id, label: s.title.split(" ")[0]! })),
  ];
  const empty = cards.length === 0;

  return (
    <TooltipProvider>
      <CardActionsProvider value={actions}>
        <main className="mx-auto w-full max-w-6xl px-4 pt-6 sm:px-6 md:pt-10">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-[32px] leading-none font-bold tracking-[-0.025em] md:text-[38px]">
                Your cards
              </h1>
              <p className="mt-2 text-[15px] text-muted-foreground">
                Every card turns over: facts, evidence and every version are on the back.
              </p>
            </div>
            <LiveStatus sync={sync} syncedAt={syncedAt} now={now} />
          </div>

          {jumps.length > 1 && (
            <nav
              aria-label="Sections"
              className="sticky top-0 z-30 -mx-4 mt-5 flex gap-1.5 overflow-x-auto bg-background/80 px-4 py-2 backdrop-blur-xl [scrollbar-width:none] sm:-mx-6 sm:px-6 md:top-14"
            >
              {jumps.map((j) => (
                <a
                  key={j.id}
                  href={`#${j.id}`}
                  className="shrink-0 rounded-full border bg-card px-3 py-1 text-[13px] font-medium text-foreground/80 shadow-sheet transition-colors hover:text-foreground"
                >
                  {j.label}
                </a>
              ))}
            </nav>
          )}

          {empty ? (
            <section className="mt-10 max-w-xl rounded-2xl border bg-card p-6 shadow-card">
              <h2 className="text-[20px] font-semibold tracking-[-0.015em]">No cards yet</h2>
              <p className="mt-2 text-[15px] text-muted-foreground">
                Cards are the pieces every resume is built from: one employer, one title, one
                accomplishment at a time. Bring in your current resume to start them.
              </p>
              <Button asChild className="mt-4">
                <Link href="/import">Bring in a resume</Link>
              </Button>
            </section>
          ) : (
            <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,400px)] lg:gap-10">
              <div className="flex min-w-0 flex-col gap-8">
                {view.experience.length > 0 && (
                  <Section
                    id="experience"
                    purpose="experience"
                    title="Work experience"
                    count={view.experience.length}
                  >
                    {view.experience.map((x) => (
                      <ExperienceCard key={x.card.id} view={x} onOpen={(c) => setOpenId(c.id)} />
                    ))}
                  </Section>
                )}
              </div>
              <div className="grid min-w-0 gap-8 md:grid-cols-2 md:items-start md:gap-6 lg:grid-cols-1 lg:gap-8">
                <div className="flex min-w-0 flex-col gap-8">{side.slice(0, split).map((s) => s.node)}</div>
                <div className="flex min-w-0 flex-col gap-8">{side.slice(split).map((s) => s.node)}</div>
              </div>
            </div>
          )}
        </main>
        <AccomplishmentSheet
          card={openId ? (byId.get(openId) ?? null) : null}
          onClose={() => setOpenId(null)}
        />
      </CardActionsProvider>
    </TooltipProvider>
  );
}
