"use client";

// One resume: the page as it reads, with each line opening the card behind
// it; editing what shows and in what order, with the cards on file beside
// it; every version kept, named, brought back or compared; the changes in
// the resume it was made from; and making a version for a role.

import {
  ArrowLeftRight,
  ChevronLeft,
  CornerDownRight,
  FileText,
  History,
  MoreHorizontal,
  Pencil,
  Plus,
  Printer,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { AccomplishmentSheet } from "@/components/cards/accomplishment";
import { type CardActions, CardActionsProvider, type CardVersion } from "@/components/cards/actions";
import { type Place, PlacePicker } from "@/components/cards/place-picker";
import { DiffPaper, Paper, type PaperEdits } from "@/components/resume/paper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { TooltipProvider } from "@/components/ui/tooltip";
import { type LibraryCard, type LibraryContent, relativeTime } from "@/lib/library";
import { changeCount, compareResumes, diffSummary } from "@/lib/resume-diff";
import {
  askText,
  bringBack,
  changesLabel,
  type Deleted,
  type DeletionPlan,
  feature,
  HIGHLIGHT_PARAGRAPH_MAX,
  HIGHLIGHT_STYLES,
  HIGHLIGHTS_MAX,
  keptVersions,
  leaveOut,
  move,
  moveContextLine,
  moveHighlight,
  moveLine,
  type ParentChanges as Changes,
  placeLine,
  type RenderedItem,
  type RenderedResume,
  type ResumeContent,
  type ResumeDetail,
  type ResumeHeader,
  type ResumeHighlights,
  resumeFor,
  type ResumePage,
  type ResumeSummary,
  type ResumeVersion,
  type ResumeVersionPage,
  sameContent,
  setFold,
  setHeader,
  setHighlightParagraph,
  setHighlightStyle,
  showHighlights,
  switchOff,
  switchOn,
  switchOnContext,
  TARGET_MAX,
  unfeature,
  versionAuthor,
  versionLabel,
} from "@/lib/resumes";
import { cn } from "@/lib/utils";

export type Compared = { from: ResumeVersionPage; to: ResumeVersionPage };

type Sent<T> = { ok: true; data: T } | { ok: false; error: string };

async function send<T>(url: string, body?: unknown): Promise<Sent<T>> {
  try {
    const response = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    const data = (await response.json().catch(() => null)) as (T & { error?: string }) | null;
    if (response.ok && data) return { ok: true, data };
    return { ok: false, error: data?.error ?? "That didn't go through. Try again in a moment." };
  } catch {
    return { ok: false, error: "The connection dropped. Check you're online and try again." };
  }
}

function When({ iso, now }: { iso: string; now: Date }) {
  return (
    <time dateTime={iso} suppressHydrationWarning>
      {relativeTime(iso, now)}
    </time>
  );
}

const OPENS = new Set(["accomplishment", "project"]);

export function ResumeScreen({
  initial,
  library: initialLibrary,
  family,
  viewing,
  compared,
}: {
  initial: ResumePage;
  library: LibraryCard[] | null;
  // Every resume the person has, for where this one came from and what was made from it.
  family: ResumeSummary[];
  viewing: ResumeVersionPage | null;
  compared: Compared | null;
}) {
  const router = useRouter();
  const [now] = useState(() => new Date());
  const [current, setCurrent] = useState(initial);
  const [library, setLibrary] = useState(initialLibrary ?? []);
  const [draft, setDraft] = useState<ResumeContent | null>(null);
  const [draftPage, setDraftPage] = useState<RenderedResume | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [editingTop, setEditingTop] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [openCard, setOpenCard] = useState<string | null>(null);
  // The version being deleted, and whether every one after it goes too.
  const [deleting, setDeleting] = useState<{ number: number; after: boolean; whole: boolean } | null>(
    null,
  );
  const resume = current.resume;
  const base = `/resumes/${encodeURIComponent(resume.id)}`;
  const byId = useMemo(() => new Map(library.map((c) => [c.id, c])), [library]);

  const act = useCallback(
    async <T,>(action: string, body: unknown): Promise<T | null> => {
      setBusy(true);
      setError(null);
      const result = await send<T>(`${base}/${action}`, body);
      setBusy(false);
      if (!result.ok) {
        setError(result.error);
        return null;
      }
      return result.data;
    },
    [base],
  );

  async function change(next: ResumeContent) {
    setDraft(next);
    const page = await act<RenderedResume>("preview", { content: next });
    if (page) setDraftPage(page);
  }

  function startEditing() {
    setDraft(structuredClone(resume.content));
    setDraftPage(current.page);
    setError(null);
  }

  function stopEditing() {
    setDraft(null);
    setDraftPage(null);
    setError(null);
  }

  async function save() {
    if (!draft) return;
    const saved = await act<ResumePage>("save", { content: draft, base_version_id: resume.head.id });
    if (saved) {
      setCurrent(saved);
      stopEditing();
    }
  }

  async function restore(number: number) {
    const restored = await act<ResumePage>("restore", { number, base_version_id: resume.head.id });
    if (restored) {
      setCurrent(restored);
      setVersionsOpen(false);
      if (viewing || compared) router.replace(base);
    }
  }

  // After a deletion: the resume as it is now, or the list when it's gone.
  function deleted(result: Deleted) {
    setDeleting(null);
    setVersionsOpen(false);
    if (!result.resume) {
      router.push("/resumes");
      return;
    }
    setCurrent(result.resume);
    if (viewing || compared) router.replace(base);
  }

  // A line that waits outside any job goes under one: the card moves there in
  // the library, and on this resume it shows under that job.
  async function place(card: string, to: Place) {
    if (!draft) return;
    const lib = byId.get(card);
    if (!lib?.content) return;
    setBusy(true);
    setError(null);
    const moved = await send<{ ok: true }>(`/cards/${encodeURIComponent(card)}`, {
      base_version_id: lib.version_id,
      content: { ...lib.content, parent: to.card },
    });
    setBusy(false);
    if (!moved.ok) return setError(moved.error);
    const fresh = await send<LibraryCard[]>("/cards/library");
    if (fresh.ok) setLibrary(fresh.data);
    await change(placeLine(draft, card, to.employment));
  }

  // The employment a card already sits under, however deep.
  const employmentOf = (card: string): string | null => {
    let current = byId.get(card);
    const seen = new Set<string>();
    while (current?.parent_id && !seen.has(current.parent_id)) {
      seen.add(current.parent_id);
      const parent = byId.get(current.parent_id);
      if (!parent) return null;
      if (parent.kind === "employment" || parent.kind === "role") return parent.id;
      current = parent;
    }
    return null;
  };

  // The cards behind the lines: opening one shows it as on the cards screen.
  const saveCard = useCallback(
    async (card: LibraryCard, content: LibraryContent) => {
      const response = await fetch(`/cards/${card.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_version_id: card.version_id, content }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? "That didn't work. Try again in a moment.");
      }
      const fresh = await send<LibraryCard[]>("/cards/library");
      if (fresh.ok) setLibrary(fresh.data);
      // The page reads the card as it is now.
      const page = await send<RenderedResume>(`${base}/preview`, { content: resume.content });
      if (page.ok) setCurrent((c) => ({ ...c, page: page.data }));
    },
    [base, resume.content],
  );
  const history = useCallback(async (id: string) => {
    const result = await send<CardVersion[]>(`/cards/${id}/history`);
    if (!result.ok) throw new Error(result.error);
    return result.data;
  }, []);
  const actions: CardActions = useMemo(
    () => ({ save: saveCard, reorder: async () => {}, history, fresh: new Set<string>(), now }),
    [saveCard, history, now],
  );

  const edits: PaperEdits | undefined = draft
    ? {
        busy,
        switchOff: (card) => change(switchOff(draft, card)),
        switchOn: (entry, card) => change(switchOn(draft, entry, card)),
        leaveOut: (entry) => change(leaveOut(draft, entry)),
        setFold: (entry, fold) => change(setFold(draft, entry, fold)),
        moveEntry: (entry, by) => change(move(draft, entry, by)),
        moveLine: (entry, group, card, by) => change(moveLine(draft, entry, group, card, by)),
        moveContext: (group, card, by) => change(moveContextLine(draft, group, card, by)),
        unfeature: (card) => change(unfeature(draft, card)),
        moveHighlight: (card, by) => change(moveHighlight(draft, card, by)),
        editHeader: () => setEditingTop(true),
      }
    : undefined;

  const kept = keptVersions(resume.versions);
  const parent = family.find((r) => r.id === resume.parent_id) ?? null;
  const children = family.filter((r) => r.parent_id === resume.id);
  const page = draftPage ?? current.page;
  const drafted = draft !== null && draftPage !== null ? compareResumes(current.page, draftPage) : null;
  const changed = draft !== null && !sameContent(draft, resume.content);

  const canOpen = (card: string) => OPENS.has(byId.get(card)?.kind ?? "");

  let body: ReactNode;
  if (compared) {
    body = <CompareView compared={compared} resume={resume} base={base} now={now} />;
  } else if (viewing) {
    body = (
      <>
        <Notice tone="quiet">
          <p>
            <b className="font-semibold">{versionLabel(viewing.version)}</b>, made{" "}
            <When iso={viewing.version.created_at} now={now} /> by{" "}
            {versionAuthor(viewing.version).toLowerCase() === "you"
              ? "you"
              : versionAuthor(viewing.version)}
            . Your resume is at version {resume.head.number}.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={() => restore(viewing.version.number)}>
              Bring this version back
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link href={`${base}?from=${viewing.version.number}`}>
                <ArrowLeftRight /> Compare with now
              </Link>
            </Button>
            <Button size="sm" variant="ghost" asChild>
              <Link href={base}>Back to the latest</Link>
            </Button>
          </div>
        </Notice>
        <div className="mx-auto mt-6 max-w-[860px]">
          <Paper page={viewing.page} />
        </div>
      </>
    );
  } else {
    body = (
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-8 print:mt-0 print:block">
        <Paper
          page={page}
          edit={edits}
          onOpen={draft ? undefined : setOpenCard}
          canOpen={canOpen}
        />
        <aside className="flex min-w-0 flex-col gap-4 print:hidden" aria-label={draft ? "On file" : "About this resume"}>
          {draft ? (
            <>
              <UnplacedRail
                page={page}
                library={library}
                busy={busy}
                employmentOf={employmentOf}
                onPlace={place}
                onShow={(card, employment) => change(placeLine(draft, card, employment))}
              />
              <HighlightsRail
                key={resume.head.id}
                content={draft}
                page={page}
                busy={busy}
                onChange={change}
              />
              <OnFileRail
                page={page}
                busy={busy}
                onJob={(card) => change(bringBack(draft, card))}
                onCard={(card) => change(switchOnContext(draft, card))}
              />
            </>
          ) : (
            <>
              <AboutRail
                resume={resume}
                parent={parent}
                madeFrom={children}
                now={now}
                onVersions={() => setVersionsOpen(true)}
              />
              <MakeVersion base={base} resumeName={resume.name} />
            </>
          )}
        </aside>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <CardActionsProvider value={actions}>
        <main className="mx-auto w-full max-w-6xl px-4 pt-4 sm:px-6 md:pt-8 print:max-w-none print:p-0">
          <Link
            href="/resumes"
            className="-ml-1.5 inline-flex items-center gap-0.5 rounded-full py-1 pr-2 text-[15px] font-medium text-primary print:hidden"
          >
            <ChevronLeft className="size-5" /> Resumes
          </Link>
          <div className="mt-1 flex flex-wrap items-end justify-between gap-x-4 gap-y-3 print:hidden">
            <div className="min-w-0">
              <h1 className="text-[30px] leading-tight font-bold tracking-[-0.025em] md:text-[36px]">
                {resume.name}
              </h1>
              <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[14px] text-muted-foreground">
                <span>{resumeFor(resume)}</span>
                {parent && (
                  <>
                    <span aria-hidden>·</span>
                    <span>
                      made from{" "}
                      <Link className="font-medium text-foreground/80 hover:underline" href={`/resumes/${parent.id}`}>
                        {parent.name}
                      </Link>
                    </span>
                  </>
                )}
                <span aria-hidden>·</span>
                <span className="font-mono text-[12.5px] text-foreground/70">v{resume.head.number}</span>
                <span aria-hidden>·</span>
                <span>
                  edited <When iso={resume.updated_at} now={now} />
                </span>
              </p>
            </div>
            {!draft && !compared && !viewing && (
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setVersionsOpen(true)}>
                  <History /> Versions
                  <span className="font-mono text-[11.5px] text-muted-foreground">{kept.length}</span>
                </Button>
                <Button variant="outline" size="sm" onClick={() => window.print()}>
                  <Printer /> <span className="max-sm:sr-only">Print or PDF</span>
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="icon-sm" aria-label="More for this resume">
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => setRenaming(true)}>
                      <Pencil /> Rename
                    </DropdownMenuItem>
                    {kept.length > 1 && (
                      <DropdownMenuItem asChild>
                        <Link href={`${base}?from=${kept[1]!.number}`}>
                          <ArrowLeftRight /> Compare with the version before
                        </Link>
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() =>
                        setDeleting({ number: kept.at(-1)!.number, after: true, whole: true })
                      }
                    >
                      <Trash2 /> Delete this resume…
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button size="sm" onClick={startEditing}>
                  <Pencil /> Edit
                </Button>
              </div>
            )}
          </div>

          {draft && (
            <div
              role="region"
              aria-label="Editing"
              className="sticky top-0 z-30 -mx-4 mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-b bg-background/85 px-4 py-2.5 backdrop-blur-xl sm:-mx-6 sm:px-6 md:top-14 print:hidden"
            >
              <p className="min-w-0 basis-full text-[14px] sm:flex-1 sm:basis-0" aria-live="polite">
                <b className="font-semibold">Editing</b>
                <span className="text-muted-foreground">
                  {" · "}
                  {busy
                    ? "Updating the page…"
                    : drafted && changeCount(drafted) > 0
                      ? diffSummary(drafted)
                      : "Leave lines out, bring cards in, or move them."}
                </span>
              </p>
              <div className="ml-auto flex items-center gap-2">
                <Button variant="ghost" size="sm" disabled={busy} onClick={stopEditing}>
                  Cancel
                </Button>
                <Button size="sm" disabled={busy || !changed} onClick={save}>
                  Save as version {resume.head.number + 1}
                </Button>
              </div>
            </div>
          )}

          {error && (
            <p role="alert" className="mt-4 rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-[14px] text-destructive">
              {error}
            </p>
          )}

          {resume.parent_changes > 0 && !draft && !compared && !viewing && (
            <ParentChanges
              key={resume.head.id}
              base={base}
              parentName={parent?.name ?? resume.parent_name ?? "The resume it was made from"}
              count={resume.parent_changes}
              headId={resume.head.id}
              onTaken={setCurrent}
            />
          )}

          {body}
        </main>

        <VersionsSheet
          open={versionsOpen}
          onOpenChange={setVersionsOpen}
          resume={resume}
          base={base}
          busy={busy}
          now={now}
          onRestore={restore}
          onDelete={(number) => setDeleting({ number, after: false, whole: false })}
          onNamed={(detail) => setCurrent((c) => ({ ...c, resume: detail }))}
          act={act}
        />
        <DeleteDialog
          key={deleting ? `${deleting.number}-${deleting.whole}` : "closed"}
          request={deleting}
          resume={resume}
          base={base}
          onClose={() => setDeleting(null)}
          onDeleted={deleted}
        />
        {draft && (
          <TopDialog
            open={editingTop}
            header={draft.header}
            onClose={() => setEditingTop(false)}
            onSave={(header) => {
              setEditingTop(false);
              void change(setHeader(draft, header));
            }}
          />
        )}
        <RenameDialog
          open={renaming}
          name={resume.name}
          busy={busy}
          onClose={() => setRenaming(false)}
          onSave={async (name) => {
            const detail = await act<ResumeDetail>("rename", { name });
            if (detail) {
              setCurrent((c) => ({ ...c, resume: detail }));
              setRenaming(false);
            }
          }}
        />
        <AccomplishmentSheet
          card={openCard ? (byId.get(openCard) ?? null) : null}
          onClose={() => setOpenCard(null)}
        />
      </CardActionsProvider>
    </TooltipProvider>
  );
}

// -- around the page -------------------------------------------------------------

function Notice({ tone, children }: { tone: "quiet" | "live"; children: ReactNode }) {
  return (
    <section
      className={cn(
        "mt-5 rounded-card border px-4 py-3.5 text-[14.5px] shadow-sheet sm:px-5 print:hidden",
        tone === "live" ? "border-live/30 bg-live-soft" : "bg-card",
      )}
    >
      {children}
    </section>
  );
}

function RailCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-card border bg-card p-4 shadow-card">
      <h2 className="text-[12px] font-semibold tracking-[0.04em] text-muted-foreground uppercase">
        {title}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function AboutRail({
  resume,
  parent,
  madeFrom: children,
  now,
  onVersions,
}: {
  resume: ResumeDetail;
  parent: ResumeSummary | null;
  // Resumes made from this one.
  madeFrom: ResumeSummary[];
  now: Date;
  onVersions: () => void;
}) {
  const kept = keptVersions(resume.versions);
  const latest = kept.slice(0, 3);
  return (
    <RailCard title="Versions">
      <ol className="flex flex-col">
        {latest.map((v, i) => (
          <li key={v.id} className="relative flex gap-3 pb-3 last:pb-0">
            <span
              aria-hidden
              className={cn(
                "relative z-10 mt-1.5 size-2.5 shrink-0 rounded-full border-2",
                i === 0 ? "border-primary bg-primary" : "border-muted-foreground/40 bg-card",
              )}
            />
            {i < latest.length - 1 && (
              <span aria-hidden className="absolute top-3 bottom-0 left-[4px] w-px bg-border" />
            )}
            <div className="min-w-0 text-[14px]">
              <p className="font-medium">
                {versionLabel(v)}
                {i === 0 && <Badge variant="accent" className="ml-1.5 align-[1px]">Now</Badge>}
              </p>
              <p className="text-[12.5px] text-muted-foreground">
                {versionAuthor(v)} · <When iso={v.created_at} now={now} />
                {v.note && ` · ${v.note}`}
              </p>
            </div>
          </li>
        ))}
      </ol>
      <Button variant="outline" size="sm" className="mt-3 w-full" onClick={onVersions}>
        <History /> All {kept.length} {kept.length === 1 ? "version" : "versions"} and compare
      </Button>
      {(parent || children.length > 0) && (
        <div className="mt-4 border-t pt-3">
          {parent && (
            <p className="text-[13px] text-muted-foreground">
              Made from{" "}
              <Link href={`/resumes/${parent.id}`} className="font-medium text-foreground hover:underline">
                {parent.name}
              </Link>
            </p>
          )}
          {children.length > 0 && (
            <>
              <p className="mt-1 text-[13px] text-muted-foreground">Made from this one:</p>
              <ul className="mt-1 flex flex-col gap-1">
                {children.map((c) => (
                  <li key={c.id}>
                    <Link
                      href={`/resumes/${c.id}`}
                      className="flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-[14px] font-medium hover:bg-accent"
                    >
                      <CornerDownRight className="size-3.5 text-muted-foreground" />
                      <span className="truncate">{c.name}</span>
                      <span className="ml-auto font-mono text-[11.5px] text-muted-foreground">v{c.head_number}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </RailCard>
  );
}

const SECTION_NAMES: Record<string, string> = {
  skill: "Skills",
  education: "Education",
  credential: "Certifications",
  activity: "Activities",
  accomplishment: "Highlights and awards",
  project: "Projects",
  story: "Stories",
};

function OnFileRail({
  page,
  busy,
  onJob,
  onCard,
}: {
  page: RenderedResume;
  busy: boolean;
  onJob: (card: string) => void;
  onCard: (card: string) => void;
}) {
  const cards = page.left_out_context ?? [];
  const groups = new Map<string, RenderedItem[]>();
  for (const c of cards) groups.set(c.kind, [...(groups.get(c.kind) ?? []), c]);
  const nothing = page.left_out.length === 0 && cards.length === 0;
  return (
    <RailCard title="On file, not on this resume">
      {nothing ? (
        <p className="text-[14px] text-muted-foreground">
          Every job and card you have is on this resume. Lines under a job you&apos;ve left out
          show under that job on the page.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {page.left_out.length > 0 && (
            <div>
              <h3 className="text-[13px] font-semibold">Jobs</h3>
              <ul className="mt-1 flex flex-col">
                {page.left_out.map((job) => (
                  <AddRow
                    key={job.card}
                    label={job.employer}
                    detail={job.dates}
                    busy={busy}
                    onAdd={() => onJob(job.card)}
                  />
                ))}
              </ul>
            </div>
          )}
          {[...groups.entries()].map(([kind, items]) => (
            <div key={kind}>
              <h3 className="text-[13px] font-semibold">{SECTION_NAMES[kind] ?? "More"}</h3>
              <ul className="mt-1 flex flex-col">
                {items.map((item) => (
                  <AddRow
                    key={item.card}
                    label={item.text}
                    detail={item.detail}
                    busy={busy}
                    onAdd={() => onCard(item.card)}
                  />
                ))}
              </ul>
            </div>
          ))}
          <p className="text-[12.5px] text-muted-foreground">
            A job comes in with no lines under it; open &ldquo;more lines on file&rdquo; under it
            to pick them.
          </p>
        </div>
      )}
    </RailCard>
  );
}

function AddRow({
  label,
  detail,
  busy,
  onAdd,
}: {
  label: string;
  detail: string;
  busy: boolean;
  onAdd: () => void;
}) {
  return (
    <li className="flex items-start gap-2 border-b py-2 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-[14px] leading-snug">{label}</p>
        {detail && <p className="line-clamp-1 text-[12.5px] text-muted-foreground">{detail}</p>}
      </div>
      <Button
        variant="outline"
        size="icon-sm"
        className="size-7"
        disabled={busy}
        aria-label={`Add ${label}`}
        onClick={onAdd}
      >
        <Plus />
      </Button>
    </li>
  );
}

/** Lines on this resume that sit outside any job on it. They don't show on
 * the page until they're under one: an accomplishment means most under the
 * job it's from. */
function UnplacedRail({
  page,
  library,
  busy,
  employmentOf,
  onPlace,
  onShow,
}: {
  page: RenderedResume;
  library: LibraryCard[];
  busy: boolean;
  employmentOf: (card: string) => string | null;
  onPlace: (card: string, to: Place) => void;
  onShow: (card: string, employment: string) => void;
}) {
  const lines = page.unplaced ?? [];
  if (lines.length === 0) return null;
  return (
    <RailCard title="Not under a job yet">
      <p className="text-[13px] text-muted-foreground">
        {lines.length === 1 ? "This line doesn't" : `These ${lines.length} lines don't`} show on
        the page until {lines.length === 1 ? "it sits" : "each sits"} under the job it&apos;s from.
        Then you can feature {lines.length === 1 ? "it" : "them"} in Highlights too.
      </p>
      <ul className="mt-2 flex flex-col">
        {lines.map((item) => {
          const employment = item.where ? employmentOf(item.card) : null;
          return (
            <li key={item.card} className="flex flex-col gap-1.5 border-b py-2.5 last:border-b-0">
              <p className="text-[14px] leading-snug">{item.text}</p>
              {employment ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 self-start px-2.5 text-[12.5px]"
                  disabled={busy}
                  onClick={() => onShow(item.card, employment)}
                >
                  <CornerDownRight /> Show under {item.where}
                </Button>
              ) : (
                <div className="self-start">
                  <PlacePicker
                    cards={library}
                    line={item.text}
                    busy={busy}
                    size="xs"
                    onPlace={(to) => onPlace(item.card, to)}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </RailCard>
  );
}

/** The highlights section: on or off, its style, the paragraph in the
 * person's own words, and the lines from their jobs to feature. */
function HighlightsRail({
  content,
  page,
  busy,
  onChange,
}: {
  content: ResumeContent;
  page: RenderedResume;
  busy: boolean;
  onChange: (next: ResumeContent) => void;
}) {
  const highlights = content.highlights ?? null;
  if (!highlights) {
    return (
      <RailCard title="Highlights">
        <p className="text-[13.5px] text-muted-foreground">
          Feature your strongest lines again near the top: as bullets, as a paragraph in your own
          words, or both.
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3 w-full"
          disabled={busy}
          onClick={() => onChange(showHighlights(content, true))}
        >
          <Sparkles /> Add highlights
        </Button>
      </RailCard>
    );
  }
  // Removing the section unmounts its editor, so adding it again starts clean.
  return (
    <HighlightsEditor content={content} highlights={highlights} page={page} busy={busy} onChange={onChange} />
  );
}

function HighlightsEditor({
  content,
  highlights,
  page,
  busy,
  onChange,
}: {
  content: ResumeContent;
  highlights: ResumeHighlights;
  page: RenderedResume;
  busy: boolean;
  onChange: (next: ResumeContent) => void;
}) {
  const [paragraph, setParagraph] = useState(highlights.paragraph);
  const featured = new Set(highlights.items.map((i) => i.card));
  const full = highlights.items.length >= HIGHLIGHTS_MAX;
  const bullets = highlights.style !== "paragraph";
  const candidates = page.entries
    .map((entry) => ({
      employer: entry.employer,
      lines: entry.roles.flatMap((r) => r.items).filter((i) => !featured.has(i.card)),
    }))
    .filter((g) => g.lines.length > 0);
  const saveParagraph = () => {
    if (paragraph !== highlights.paragraph) onChange(setHighlightParagraph(content, paragraph));
  };
  return (
    <RailCard title="Highlights">
      <div role="radiogroup" aria-label="Highlights style" className="grid grid-cols-3 gap-1 rounded-inset bg-muted p-0.5">
        {HIGHLIGHT_STYLES.map((style) => (
          <button
            key={style.value}
            type="button"
            role="radio"
            aria-checked={highlights.style === style.value}
            disabled={busy}
            onClick={() => {
              saveParagraph();
              onChange(setHighlightStyle(content, style.value));
            }}
            className={cn(
              "h-7 rounded-[3px] text-[12.5px] font-medium text-muted-foreground transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none",
              highlights.style === style.value && "bg-card text-foreground shadow-sm",
            )}
          >
            {style.label}
          </button>
        ))}
      </div>
      {highlights.style !== "bullets" && (
        <div className="mt-3 grid gap-1.5">
          <Label htmlFor="highlights-paragraph" className="text-[13px]">
            Your paragraph
          </Label>
          <Textarea
            id="highlights-paragraph"
            value={paragraph}
            maxLength={HIGHLIGHT_PARAGRAPH_MAX}
            rows={4}
            placeholder="A few sentences on what you do best, in your own words."
            onChange={(e) => setParagraph(e.target.value)}
            onBlur={saveParagraph}
          />
        </div>
      )}
      {bullets && (
        <div className="mt-3">
          <h3 className="text-[13px] font-semibold">
            Feature a line{" "}
            <span className="font-normal text-muted-foreground tabular-nums">
              {highlights.items.length} of {HIGHLIGHTS_MAX}
            </span>
          </h3>
          {candidates.length === 0 ? (
            <p className="mt-1 text-[13px] text-muted-foreground">
              Lines under the jobs on this resume show here to feature.
            </p>
          ) : (
            <div className="mt-1 flex max-h-72 flex-col gap-2 overflow-y-auto">
              {candidates.map((group) => (
                <div key={group.employer}>
                  <p className="text-[12px] font-medium text-muted-foreground">{group.employer}</p>
                  <ul className="flex flex-col">
                    {group.lines.map((item) => (
                      <AddRow
                        key={item.card}
                        label={item.text}
                        detail=""
                        busy={busy || full}
                        onAdd={() => onChange(feature(content, item.card))}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="mt-2 -ml-2 text-muted-foreground"
        disabled={busy}
        onClick={() => onChange(showHighlights(content, false))}
      >
        Remove the highlights section
      </Button>
    </RailCard>
  );
}

// -- deleting versions ------------------------------------------------------------

function DeleteDialog({
  request,
  resume,
  base,
  onClose,
  onDeleted,
}: {
  request: { number: number; after: boolean; whole: boolean } | null;
  resume: ResumeDetail;
  base: string;
  onClose: () => void;
  onDeleted: (result: Deleted) => void;
}) {
  const [after, setAfter] = useState(request?.after ?? false);
  const [fetched, setFetched] = useState<{ key: string; plan: DeletionPlan } | null>(null);
  const [also, setAlso] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const number = request?.number ?? 0;
  const later = keptVersions(resume.versions).filter((v) => v.number > number).length;

  // What deleting reaches, for what's chosen now.
  const key = request ? `${number}-${after}-${resume.head.id}` : null;
  const plan = fetched && fetched.key === key ? fetched.plan : null;
  useEffect(() => {
    if (!key) return;
    let live = true;
    void send<DeletionPlan>(`${base}/deletion`, { number, after }).then((result) => {
      if (!live) return;
      if (result.ok) setFetched({ key, plan: result.data });
      else setError(result.error);
    });
    return () => {
      live = false;
    };
  }, [key, base, number, after]);

  async function confirm() {
    if (!plan) return;
    setBusy(true);
    setError(null);
    const result = await send<Deleted>(`${base}/delete`, {
      number,
      after,
      base_version_id: resume.head.id,
      with_branches: [...also],
    });
    setBusy(false);
    if (!result.ok) return setError(result.error);
    onDeleted(result.data);
  }

  const span = plan ? numbersText(plan.numbers) : "";
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {request?.whole ? `Delete ${resume.name}?` : `Delete version ${number}?`}
          </DialogTitle>
          <DialogDescription>
            Its content and names are erased for good. This can&apos;t be undone.
          </DialogDescription>
        </DialogHeader>

        {!request?.whole && later > 0 && (
          <fieldset className="flex flex-col gap-2 text-[14px]">
            <legend className="sr-only">What to delete</legend>
            <label className="flex items-start gap-2.5">
              <input
                type="radio"
                name="delete-after"
                className="mt-0.5 size-4 accent-[var(--destructive)]"
                checked={!after}
                onChange={() => setAfter(false)}
              />
              <span>
                Only version {number}
                <span className="block text-[12.5px] text-muted-foreground">
                  The {later === 1 ? "version" : `${later} versions`} after it stay as they are;
                  each holds its whole page.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-2.5">
              <input
                type="radio"
                name="delete-after"
                className="mt-0.5 size-4 accent-[var(--destructive)]"
                checked={after}
                onChange={() => setAfter(true)}
              />
              <span>Version {number} and every one after it</span>
            </label>
          </fieldset>
        )}

        {plan === null ? (
          <p className="text-[14px] text-muted-foreground" role="status">
            {error ?? "Checking what this reaches…"}
          </p>
        ) : (
          <div className="flex flex-col gap-3 text-[14px]">
            <p>
              {plan.deletes_resume ? (
                <>
                  That&apos;s every version, so this deletes the resume.
                  {resume.import_id && " You can make it again from the file it came from."}
                </>
              ) : (
                <>
                  Deletes {span}.
                  {plan.back_to !== null &&
                    ` Your resume goes back to version ${plan.back_to}, saved as version ${resume.head.number + 1}.`}
                </>
              )}
            </p>
            {plan.branches.length > 0 && (
              <div className="rounded-inset border p-3">
                <p className="text-[13px] font-semibold">Made from this resume</p>
                <ul className="mt-1.5 flex flex-col gap-2">
                  {plan.branches.map((b) => (
                    <li key={b.id}>
                      <label className="flex items-start gap-2.5">
                        <input
                          type="checkbox"
                          className="mt-0.5 size-4 accent-[var(--destructive)]"
                          checked={also.has(b.id)}
                          onChange={(e) => {
                            const next = new Set(also);
                            if (e.target.checked) next.add(b.id);
                            else next.delete(b.id);
                            setAlso(next);
                          }}
                        />
                        <span>
                          Delete <b className="font-semibold">{b.name}</b> too
                          <span className="block text-[12.5px] text-muted-foreground">
                            {also.has(b.id)
                              ? "Every version of it goes. Resumes made from it stay, on their own."
                              : b.recenters_on === null
                                ? "Otherwise it stays, on its own, with every version it has."
                                : `Otherwise it stays, and takes changes from version ${b.recenters_on} on.`}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {error && (
              <p role="alert" className="text-[13.5px] text-destructive">
                {error}
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" disabled={busy} onClick={onClose}>
            Keep it
          </Button>
          <Button variant="destructive" disabled={busy || plan === null} onClick={confirm}>
            <Trash2 />
            {plan?.deletes_resume
              ? "Delete the resume"
              : plan && plan.numbers.length > 1
                ? `Delete ${plan.numbers.length} versions`
                : `Delete version ${number}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// "version 3", "versions 3–5", or "versions 2, 4".
function numbersText(numbers: number[]): string {
  if (numbers.length === 1) return `version ${numbers[0]}`;
  const run = numbers.every((n, i) => i === 0 || n === numbers[i - 1]! + 1);
  return run
    ? `versions ${numbers[0]}–${numbers.at(-1)}`
    : `versions ${numbers.join(", ")}`;
}

// -- the resume it was made from ------------------------------------------------

function ParentChanges({
  base,
  parentName,
  count,
  headId,
  onTaken,
}: {
  base: string;
  parentName: string;
  count: number;
  headId: string;
  onTaken: (page: ResumePage) => void;
}) {
  const [reviewed, setReviewed] = useState<Changes | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changes = reviewed?.changes ?? null;

  async function review() {
    setBusy(true);
    setError(null);
    const result = await send<Changes>(`${base}/parent-changes`);
    setBusy(false);
    if (!result.ok) return setError(result.error);
    setReviewed(result.data);
    setChosen(new Set(result.data.changes.map((c) => c.change.key)));
  }

  async function take(keys: string[]) {
    setBusy(true);
    setError(null);
    const result = await send<ResumePage>(`${base}/take`, {
      keys,
      base_version_id: headId,
      parent_version_id: reviewed?.parent_version_id ?? null,
    });
    setBusy(false);
    if (!result.ok) return setError(result.error);
    onTaken(result.data);
  }

  return (
    <Notice tone="live">
      <p>
        <b className="font-semibold">{parentName}</b> has {changesLabel(count)} since this one was
        made from it. Take the ones you want; this resume keeps its own order.
      </p>
      {error && (
        <p role="alert" className="mt-2 text-[13.5px] text-destructive">
          {error}
        </p>
      )}
      {changes === null ? (
        <Button size="sm" variant="outline" className="mt-3" disabled={busy} onClick={review}>
          See what changed
        </Button>
      ) : (
        <>
          <ul className="mt-3 flex flex-col gap-1.5">
            {changes.map(({ change, label }) => (
              <li key={change.key}>
                <label className="flex items-start gap-2.5 text-[14px]">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4 accent-[var(--primary)]"
                    checked={chosen.has(change.key)}
                    onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(change.key);
                      else next.delete(change.key);
                      setChosen(next);
                    }}
                  />
                  <span>{label}</span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" disabled={busy || chosen.size === 0} onClick={() => take([...chosen])}>
              Take {chosen.size === changes.length ? "them" : changesLabel(chosen.size)}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => take([])}>
              Not these
            </Button>
          </div>
        </>
      )}
    </Notice>
  );
}

// -- versions ---------------------------------------------------------------------

function VersionsSheet({
  open,
  onOpenChange,
  resume,
  base,
  busy,
  now,
  onRestore,
  onDelete,
  onNamed,
  act,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  resume: ResumeDetail;
  base: string;
  busy: boolean;
  now: Date;
  onRestore: (number: number) => void;
  onDelete: (number: number) => void;
  onNamed: (detail: ResumeDetail) => void;
  act: <T>(action: string, body: unknown) => Promise<T | null>;
}) {
  const versions = [...resume.versions].reverse();
  const kept = keptVersions(resume.versions);
  const head = resume.head.number;
  const [naming, setNaming] = useState<number | null>(null);
  const [name, setName] = useState("");

  async function saveName(event: FormEvent) {
    event.preventDefault();
    if (naming === null || !name.trim()) return;
    const detail = await act<ResumeDetail>("name", { number: naming, name: name.trim() });
    if (detail) {
      onNamed(detail);
      setNaming(null);
      setName("");
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Versions</SheetTitle>
          <SheetDescription>
            Every change is kept until you delete it. Name the ones you send, compare any two, or
            bring one back.
          </SheetDescription>
        </SheetHeader>

        {kept.length > 1 && (
          <ComparePicker versions={kept} base={base} onGo={() => onOpenChange(false)} />
        )}

        <ol className="flex flex-col overflow-y-auto px-5 pb-6">
          {versions.map((v, i) =>
            v.redacted ? (
              <li key={v.id} className="relative flex gap-3 pt-3">
                <span
                  aria-hidden
                  className="relative z-10 mt-1.5 size-2.5 shrink-0 rounded-full border-2 border-dashed border-muted-foreground/40 bg-popover"
                />
                {i < versions.length - 1 && (
                  <span aria-hidden className="absolute top-6 -bottom-3 left-[4px] w-px bg-border" />
                )}
                <p className="min-w-0 flex-1 border-b pb-3 text-[13px] text-muted-foreground">
                  Version {v.number} · deleted
                </p>
              </li>
            ) : (
            <li key={v.id} className="relative flex gap-3 pt-3">
              <span
                aria-hidden
                className={cn(
                  "relative z-10 mt-1.5 size-2.5 shrink-0 rounded-full border-2",
                  v.number === head ? "border-primary bg-primary" : "border-muted-foreground/40 bg-popover",
                )}
              />
              {i < versions.length - 1 && (
                <span aria-hidden className="absolute top-6 -bottom-3 left-[4px] w-px bg-border" />
              )}
              <div className="min-w-0 flex-1 border-b pb-3">
                <p className="text-[15px] font-medium">
                  {versionLabel(v)}
                  {v.number === head && <Badge variant="accent" className="ml-1.5 align-[1px]">Now</Badge>}
                </p>
                <p className="text-[13px] text-muted-foreground">
                  {versionAuthor(v)} · <When iso={v.created_at} now={now} />
                  {v.note && ` · ${v.note}`}
                </p>
                <div className="mt-1.5 -ml-2.5 flex flex-wrap gap-0.5">
                  {v.number !== head && !v.redacted && (
                    <>
                      <Button variant="ghost" size="sm" asChild>
                        <Link href={`${base}?v=${v.number}`} onClick={() => onOpenChange(false)}>
                          See it
                        </Link>
                      </Button>
                      <Button variant="ghost" size="sm" asChild>
                        <Link href={`${base}?from=${v.number}`} onClick={() => onOpenChange(false)}>
                          Compare with now
                        </Link>
                      </Button>
                      <Button variant="ghost" size="sm" disabled={busy} onClick={() => onRestore(v.number)}>
                        Bring back
                      </Button>
                    </>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      setNaming(v.number);
                      setName(v.names[0] ?? "");
                    }}
                  >
                    {v.names.length ? "Rename" : "Name it"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    disabled={busy}
                    onClick={() => onDelete(v.number)}
                  >
                    Delete…
                  </Button>
                </div>
                {naming === v.number && (
                  <form className="mt-2 flex gap-2" onSubmit={saveName}>
                    <Label htmlFor={`name-${v.number}`} className="sr-only">
                      Name for version {v.number}
                    </Label>
                    <Input
                      id={`name-${v.number}`}
                      autoFocus
                      value={name}
                      maxLength={120}
                      placeholder="Sent to Contoso"
                      onChange={(e) => setName(e.target.value)}
                    />
                    <Button size="sm" type="submit" className="h-9" disabled={busy || !name.trim()}>
                      Save
                    </Button>
                  </form>
                )}
              </div>
            </li>
            ),
          )}
        </ol>
      </SheetContent>
    </Sheet>
  );
}

// Mounts each time the sheet opens, so it starts from the latest two versions.
function ComparePicker({
  versions,
  base,
  onGo,
}: {
  versions: ResumeVersion[];
  base: string;
  onGo: () => void;
}) {
  const router = useRouter();
  const [from, setFrom] = useState(String(versions[1]!.number));
  const [to, setTo] = useState(String(versions[0]!.number));
  return (
    <form
      className="mx-5 flex flex-wrap items-end gap-2 rounded-2xl border bg-card p-3"
      onSubmit={(e) => {
        e.preventDefault();
        onGo();
        router.push(`${base}?from=${from}&to=${to}`);
      }}
    >
      <VersionPick label="Compare" value={from} onChange={setFrom} versions={versions} />
      <VersionPick label="with" value={to} onChange={setTo} versions={versions} />
      <Button size="sm" type="submit" disabled={from === to}>
        <ArrowLeftRight /> Compare
      </Button>
    </form>
  );
}

function VersionPick({
  label,
  value,
  onChange,
  versions,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  versions: ResumeVersion[];
}) {
  return (
    <label className="flex min-w-0 flex-1 basis-[140px] flex-col gap-1 text-[12px] font-medium text-muted-foreground sm:max-w-[280px]">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-xl border bg-background px-2.5 text-[14px] text-foreground"
      >
        {versions.map((v) => (
          <option key={v.id} value={v.number}>
            {versionLabel(v)}
          </option>
        ))}
      </select>
    </label>
  );
}

function CompareView({
  compared,
  resume,
  base,
  now,
}: {
  compared: Compared;
  resume: ResumeDetail;
  base: string;
  now: Date;
}) {
  const router = useRouter();
  const diff = useMemo(() => compareResumes(compared.from.page, compared.to.page), [compared]);
  const summary = diffSummary(diff);
  const versions = keptVersions(resume.versions);
  const go = (from: number, to: number) => router.push(`${base}?from=${from}&to=${to}`);
  return (
    <>
      <Notice tone="quiet">
        <div className="flex flex-wrap items-end gap-2">
          <VersionPick
            label="Comparing"
            value={String(compared.from.version.number)}
            onChange={(v) => go(Number(v), compared.to.version.number)}
            versions={versions}
          />
          <VersionPick
            label="with"
            value={String(compared.to.version.number)}
            onChange={(v) => go(compared.from.version.number, Number(v))}
            versions={versions}
          />
          <Button size="sm" variant="ghost" asChild>
            <Link href={base}>Done</Link>
          </Button>
        </div>
        <p className="mt-3 text-[14px]" role="status">
          <b className="font-semibold">{summary ?? "These two read the same."}</b>{" "}
          <span className="text-muted-foreground">
            From version {compared.from.version.number} (<When iso={compared.from.version.created_at} now={now} />) to
            version {compared.to.version.number} (<When iso={compared.to.version.created_at} now={now} />).
            Both read your cards as they are now.
          </span>
        </p>
        <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-muted-foreground" aria-hidden>
          <span className="rounded-[4px] bg-paper-added px-1.5 text-paper-ink">Added</span>
          <span className="rounded-[4px] bg-paper-removed/[0.08] px-1.5 text-paper-removed line-through">
            Left out
          </span>
          <span>Reworded lines show what they read before</span>
        </p>
      </Notice>
      <div className="mx-auto mt-6 max-w-[860px]">
        <DiffPaper diff={diff} header={compared.to.page.header} />
      </div>
    </>
  );
}

// -- making a version for a role ----------------------------------------------------

function MakeVersion({ base, resumeName }: { base: string; resumeName: string }) {
  const router = useRouter();
  const [forWhom, setForWhom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = forWhom.trim().length > 0;

  async function ask(event?: FormEvent) {
    event?.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    const result = await send(`${base}/ask`, { text: askText(resumeName, forWhom) });
    if (!result.ok) {
      setBusy(false);
      return setError(result.error);
    }
    router.push("/talk");
  }

  async function copy() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    const result = await send<ResumePage>(`${base}/copy`, { target: forWhom });
    if (!result.ok) {
      setBusy(false);
      return setError(result.error);
    }
    router.push(`/resumes/${encodeURIComponent(result.data.resume.id)}`);
  }

  return (
    <RailCard title="Make a version for a role">
      <form onSubmit={ask} className="flex flex-col gap-2.5">
        <p className="text-[13.5px] text-muted-foreground">
          Plytos picks the jobs and lines that fit and words them for it. This resume stays as it
          is.
        </p>
        <Label htmlFor="for-whom" className="mt-1 text-[13px]">
          Who is it for?
        </Label>
        <Input
          id="for-whom"
          value={forWhom}
          maxLength={TARGET_MAX}
          placeholder="Operations roles at fintech companies"
          onChange={(e) => setForWhom(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-[13px] text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy || !ready}>
          <Sparkles /> Ask Plytos
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={busy || !ready} onClick={copy}>
          <FileText /> Copy it and change it myself
        </Button>
      </form>
    </RailCard>
  );
}

// -- dialogs -----------------------------------------------------------------------

function TopDialog({
  open,
  header,
  onClose,
  onSave,
}: {
  open: boolean;
  header: ResumeHeader;
  onClose: () => void;
  onSave: (header: ResumeHeader) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        {open && <TopForm header={header} onClose={onClose} onSave={onSave} />}
      </DialogContent>
    </Dialog>
  );
}

const TOP_FIELDS: { key: Exclude<keyof ResumeHeader, "links" | "summary">; label: string; max: number }[] = [
  { key: "name", label: "Name", max: 120 },
  { key: "headline", label: "Headline", max: 200 },
  { key: "email", label: "Email", max: 200 },
  { key: "phone", label: "Phone", max: 60 },
  { key: "location", label: "Location", max: 120 },
];

function TopForm({
  header,
  onClose,
  onSave,
}: {
  header: ResumeHeader;
  onClose: () => void;
  onSave: (header: ResumeHeader) => void;
}) {
  const [value, setValue] = useState(header);
  const [links, setLinks] = useState(header.links.join("\n"));
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          ...value,
          links: links
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean)
            .slice(0, 5),
        });
      }}
    >
      <DialogHeader>
        <DialogTitle>The top of the page</DialogTitle>
        <DialogDescription>
          Changes show on the page now and are kept when you save the version.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        {TOP_FIELDS.map((f) => (
          <div key={f.key} className={cn("grid gap-1.5", f.key === "headline" && "sm:col-span-2")}>
            <Label htmlFor={`top-${f.key}`}>{f.label}</Label>
            <Input
              id={`top-${f.key}`}
              value={value[f.key]}
              maxLength={f.max}
              onChange={(e) => setValue({ ...value, [f.key]: e.target.value })}
            />
          </div>
        ))}
        <div className="grid gap-1.5 sm:col-span-2">
          <Label htmlFor="top-links">Links, one per line</Label>
          <Textarea id="top-links" rows={2} value={links} onChange={(e) => setLinks(e.target.value)} />
        </div>
        <div className="grid gap-1.5 sm:col-span-2">
          <Label htmlFor="top-summary">Summary</Label>
          <Textarea
            id="top-summary"
            rows={4}
            maxLength={1500}
            value={value.summary}
            onChange={(e) => setValue({ ...value, summary: e.target.value })}
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit">Use these</Button>
      </DialogFooter>
    </form>
  );
}

function RenameDialog({
  open,
  name,
  busy,
  onClose,
  onSave,
}: {
  open: boolean;
  name: string;
  busy: boolean;
  onClose: () => void;
  onSave: (name: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        {/* Mounts each time the dialog opens, so it starts from the current name. */}
        {open && <RenameForm name={name} busy={busy} onClose={onClose} onSave={onSave} />}
      </DialogContent>
    </Dialog>
  );
}

function RenameForm({
  name,
  busy,
  onClose,
  onSave,
}: {
  name: string;
  busy: boolean;
  onClose: () => void;
  onSave: (name: string) => void;
}) {
  const [value, setValue] = useState(name);
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) onSave(value.trim());
      }}
    >
      <DialogHeader>
        <DialogTitle>Rename this resume</DialogTitle>
        <DialogDescription>Only you see its name.</DialogDescription>
      </DialogHeader>
      <Input
        aria-label="Name"
        autoFocus
        value={value}
        maxLength={120}
        onChange={(e) => setValue(e.target.value)}
      />
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy || !value.trim()}>
          Rename
        </Button>
      </DialogFooter>
    </form>
  );
}
