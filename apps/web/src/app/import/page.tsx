import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { BringIn } from "@/components/import-review/bring-in";
import { ApiError, listImports } from "@/lib/api";
import type { ImportSummary } from "@/lib/imports";
import { currentSession } from "@/lib/session";

export const metadata: Metadata = { title: "Bring in a resume" };
export const dynamic = "force-dynamic";

// Bringing a resume in, and every file brought in so far with its check and
// its audit.
export default async function ImportPage() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let files: ImportSummary[] = [];
  try {
    files = await listImports(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }

  return (
    <AppShell current="/resumes">
      <BringIn files={files} />
    </AppShell>
  );
}
