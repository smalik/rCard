import { ChevronRight, CornerDownRight, FileText, Upload } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, getResume, listResumes } from "@/lib/api";
import { relativeTime } from "@/lib/library";
import { changesLabel, type Resumes, resumeFor, type ResumeSummary } from "@/lib/resumes";
import { currentSession, type Session } from "@/lib/session";
import { MakeResume } from "./make-resume";

export const metadata: Metadata = { title: "Resumes" };
export const dynamic = "force-dynamic";

// How many changes each resume made from another hasn't taken yet. Only the
// first few are looked up; the rest show theirs on their own page.
async function changesToTake(session: Session, resumes: ResumeSummary[]): Promise<Map<string, number>> {
  const made = resumes.filter((r) => r.parent_id !== null).slice(0, 12);
  const counts = await Promise.all(
    made.map((r) =>
      getResume(session, r.id).then(
        ({ resume }) => [r.id, resume.parent_changes] as const,
        () => [r.id, 0] as const,
      ),
    ),
  );
  return new Map(counts);
}

// Resumes with the ones made from each, newest change first at every level.
function family(resumes: ResumeSummary[]): { resume: ResumeSummary; depth: number }[] {
  const ids = new Set(resumes.map((r) => r.id));
  const kids = new Map<string | null, ResumeSummary[]>();
  for (const r of resumes) {
    const parent = r.parent_id && ids.has(r.parent_id) ? r.parent_id : null;
    kids.set(parent, [...(kids.get(parent) ?? []), r]);
  }
  for (const list of kids.values()) list.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const out: { resume: ResumeSummary; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const r of kids.get(parent) ?? []) {
      out.push({ resume: r, depth });
      walk(r.id, Math.min(depth + 1, 3));
    }
  };
  walk(null, 0);
  return out;
}

function Thumb() {
  return (
    <span
      aria-hidden
      className="flex h-14 w-11 shrink-0 flex-col gap-[3px] rounded-[4px] border border-black/[0.06] bg-paper p-1.5 shadow-sheet"
    >
      <span className="h-[3px] w-6 rounded-full bg-paper-ink/70" />
      <span className="h-[2px] w-5 rounded-full bg-paper-soft/50" />
      <span className="mt-1 h-[2px] w-full rounded-full bg-paper-soft/35" />
      <span className="h-[2px] w-full rounded-full bg-paper-soft/35" />
      <span className="h-[2px] w-4/5 rounded-full bg-paper-soft/35" />
      <span className="mt-0.5 h-[2px] w-full rounded-full bg-paper-soft/35" />
    </span>
  );
}

function ResumeRow({ resume, changes, now }: { resume: ResumeSummary; changes: number; now: Date }) {
  return (
    <Link
      href={`/resumes/${encodeURIComponent(resume.id)}`}
      className="group flex items-center gap-4 rounded-card border bg-card p-3.5 shadow-card transition-shadow hover:shadow-lift focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none sm:p-4"
    >
      <Thumb />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[17px] font-semibold tracking-[-0.01em]">{resume.name}</p>
        <p className="truncate text-[14px] text-muted-foreground">{resumeFor(resume)}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12.5px] text-muted-foreground">
          <span className="font-mono text-[11.5px] text-foreground/70">v{resume.head_number}</span>
          <span aria-hidden>·</span>
          <span>edited {relativeTime(resume.updated_at, now)}</span>
          {changes > 0 && (
            <Badge variant="live" className="ml-1">
              {changesLabel(changes)} to take
            </Badge>
          )}
        </p>
      </div>
      <ChevronRight className="size-5 shrink-0 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

export default async function ResumesPage() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let data: Resumes | null = null;
  let changes = new Map<string, number>();
  try {
    data = await listResumes(session);
    changes = await changesToTake(session, data.resumes);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }
  const now = new Date();
  const rows = data ? family(data.resumes) : [];

  return (
    <AppShell current="/resumes">
      <main className="mx-auto w-full max-w-3xl px-4 pt-6 sm:px-6 md:pt-10">
        <div className="flex items-end justify-between gap-3">
          <h1 className="text-[32px] leading-none font-bold tracking-[-0.025em] md:text-[38px]">Resumes</h1>
          <Button asChild size="sm" variant="outline">
            <Link href="/import">
              <Upload /> Bring in a resume
            </Link>
          </Button>
        </div>
        <p className="mt-2 text-[15px] text-muted-foreground">
          Each resume is a selection of your cards. Every version is kept, and a resume made for a
          role stays tied to the one it came from.
        </p>

        {data === null && (
          <p role="alert" className="mt-6 rounded-card border bg-card p-5 text-[15px] shadow-card">
            Plytos couldn&apos;t load your resumes just now. Try again in a moment.
          </p>
        )}

        {data?.ready.map((file) => (
          <section
            key={file.id}
            className="mt-6 flex flex-col gap-3 rounded-card border border-primary/25 bg-accent/60 p-5 shadow-card sm:flex-row sm:items-center"
          >
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
              <FileText className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-[17px] font-semibold">Your resume is ready to set up</h2>
              <p className="text-[14px] text-muted-foreground">
                From {file.file.name}: the {file.approved} {file.approved === 1 ? "card" : "cards"}{" "}
                you kept, in your own words and the file&apos;s order.
              </p>
            </div>
            <MakeResume importId={file.id} />
          </section>
        ))}

        {data && data.resumes.length === 0 && data.ready.length === 0 && (
          <section className="mt-8 rounded-card border bg-card p-6 shadow-card">
            <h2 className="text-[20px] font-semibold tracking-[-0.015em]">No resumes yet</h2>
            <p className="mt-2 text-[15px] text-muted-foreground">
              Bring in your resume and keep its cards. Plytos sets it up as you wrote it, then
              makes versions of it for the roles you go after.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button asChild>
                <Link href="/import">Bring in a resume</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/talk">Go to Talk</Link>
              </Button>
            </div>
          </section>
        )}

        {rows.length > 0 && (
          <ul className="mt-6 flex flex-col gap-3" aria-label="Your resumes">
            {rows.map(({ resume, depth }) => (
              <li
                key={resume.id}
                className="flex items-center gap-2"
                style={{ paddingLeft: depth ? `${Math.min(depth, 3) * 1.25}rem` : undefined }}
              >
                {depth > 0 && (
                  <CornerDownRight aria-hidden className="size-4 shrink-0 text-muted-foreground/70" />
                )}
                <div className="min-w-0 flex-1">
                  {depth > 0 && <span className="sr-only">Made from the one above: </span>}
                  <ResumeRow resume={resume} changes={changes.get(resume.id) ?? 0} now={now} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    </AppShell>
  );
}
