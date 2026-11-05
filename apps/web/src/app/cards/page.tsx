import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { type Contact, LibraryScreen } from "@/components/cards/library-screen";
import { ApiError, getLibrary, getResume, listResumes } from "@/lib/api";
import type { LibraryCard } from "@/lib/library";
import type { Session } from "@/lib/session";
import { currentSession } from "@/lib/session";

export const metadata: Metadata = { title: "Your cards" };
export const dynamic = "force-dynamic";

// The contact card comes from the top of the resume changed most recently.
async function latestContact(session: Session): Promise<Contact | null> {
  const { resumes } = await listResumes(session);
  const latest = [...resumes].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
  if (!latest) return null;
  const { resume } = await getResume(session, latest.id);
  return {
    resumeId: resume.id,
    resumeName: resume.name,
    baseVersionId: resume.head.id,
    header: resume.content.header,
  };
}

export default async function Cards() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let cards: LibraryCard[] | null = null;
  let contact: Contact | null = null;
  try {
    [cards, contact] = await Promise.all([getLibrary(session), latestContact(session)]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }

  return (
    <AppShell current="/cards">
      {cards ? (
        <LibraryScreen initial={cards} contact={contact} />
      ) : (
        <main className="mx-auto max-w-xl px-4 pt-10">
          <p role="alert" className="rounded-2xl border bg-card p-5 text-[15px] shadow-card">
            Plytos couldn&apos;t load your cards just now. Try again in a moment.
          </p>
        </main>
      )}
    </AppShell>
  );
}
