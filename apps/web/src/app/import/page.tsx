import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ApiError, listImports } from "../../lib/api";
import { currentSession } from "../../lib/session";
import { Start, type Unfinished } from "./start";

export const metadata: Metadata = { title: "Bring in your resume" };
export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  // The newest import that still has cards waiting, so the person can pick up
  // where they left off.
  let unfinished: Unfinished | null = null;
  try {
    const imports = await listImports(session);
    const open = imports
      .map((i) => ({ ...i, left: i.cards - i.approved - i.dropped }))
      .filter((i) => i.left > 0)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
    if (open) unfinished = { id: open.id, name: open.file.name, left: open.left };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }

  return <Start unfinished={unfinished} />;
}
