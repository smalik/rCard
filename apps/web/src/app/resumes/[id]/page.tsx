import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { type Compared, ResumeScreen } from "@/components/resume/resume-screen";
import { ApiError, getLibrary, getResume, getResumeVersion, listResumes } from "@/lib/api";
import type { LibraryCard } from "@/lib/library";
import type { ResumePage, ResumeSummary, ResumeVersionPage } from "@/lib/resumes";
import { isId } from "@/lib/routes";
import { currentSession, type Session } from "@/lib/session";

export const metadata: Metadata = { title: "Resume" };
export const dynamic = "force-dynamic";

function versionNumber(value: string | string[] | undefined): number | null {
  const n = Number(Array.isArray(value) ? value[0] : (value ?? ""));
  return Number.isInteger(n) && n >= 1 && n < 1_000_000 ? n : null;
}

// A version of the resume as it reads; the latest comes with the resume itself.
async function versionPage(
  session: Session,
  initial: ResumePage,
  number: number,
): Promise<ResumeVersionPage> {
  const { resume } = initial;
  if (number === resume.head.number) {
    return { version: resume.head, content: resume.content, page: initial.page };
  }
  return getResumeVersion(session, resume.id, number);
}

// Cards and the other resumes help the page but aren't needed to show it.
async function quietly<T>(work: Promise<T>, fallback: T): Promise<T> {
  try {
    return await work;
  } catch (error) {
    if (error instanceof ApiError) return fallback;
    throw error;
  }
}

export default async function ResumeRoute({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  const { id } = await params;
  if (!isId(id)) notFound();
  const query = await searchParams;
  const v = versionNumber(query.v);
  const from = versionNumber(query.from);
  const to = versionNumber(query.to);

  let initial: ResumePage;
  let viewing: ResumeVersionPage | null = null;
  let compared: Compared | null = null;
  let library: LibraryCard[] | null = null;
  let family: ResumeSummary[] = [];
  try {
    [initial, library, family] = await Promise.all([
      getResume(session, id),
      quietly<LibraryCard[] | null>(getLibrary(session), null),
      quietly(
        listResumes(session).then((r) => r.resumes),
        [] as ResumeSummary[],
      ),
    ]);
    const head = initial.resume.head.number;
    if (from !== null && from <= head && (to === null || to <= head)) {
      const [a, b] = await Promise.all([
        versionPage(session, initial, from),
        versionPage(session, initial, to ?? head),
      ]);
      compared = { from: a, to: b };
    } else if (v !== null && v !== head) {
      viewing = await getResumeVersion(session, id, v);
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  return (
    <AppShell current="/resumes">
      <ResumeScreen
        key={`${initial.resume.head.id}-${viewing?.version.id ?? ""}-${compared ? `${from}-${to}` : ""}`}
        initial={initial}
        library={library}
        family={family}
        viewing={viewing}
        compared={compared}
      />
    </AppShell>
  );
}
