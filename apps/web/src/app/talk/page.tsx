import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { TalkScreen } from "@/components/talk/talk-screen";
import { ApiError, getThread, listResumes } from "@/lib/api";
import { isImportId } from "@/lib/routes";
import { currentSession } from "@/lib/session";
import { NO_CHECK_INS, type Thread } from "@/lib/talk";

export const metadata: Metadata = { title: "Talk" };
export const dynamic = "force-dynamic";

// The resume made from each file, by import id. Helps the page but isn't
// needed to show it.
async function madeFrom(session: NonNullable<Awaited<ReturnType<typeof currentSession>>>) {
  try {
    const { resumes } = await listResumes(session);
    return Object.fromEntries(
      resumes.flatMap((r) => (r.import_id && r.parent_id === null ? [[r.import_id, r.id]] : [])),
    );
  } catch (error) {
    if (error instanceof ApiError) return {};
    throw error;
  }
}

export default async function TalkPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  const query = await searchParams;
  const review = Array.isArray(query.review) ? query.review[0] : query.review;

  const [loaded, made] = await Promise.all([
    getThread(session).catch((error: unknown) => {
      if (error instanceof ApiError) return null;
      throw error;
    }),
    madeFrom(session),
  ]);
  const thread: Thread = loaded ?? { messages: [], resumes: [], check_ins: NO_CHECK_INS };
  return (
    <AppShell current="/talk">
      <TalkScreen
        initial={thread}
        failed={loaded === null}
        asked={review && isImportId(review) ? review : null}
        madeFrom={made}
      />
    </AppShell>
  );
}
