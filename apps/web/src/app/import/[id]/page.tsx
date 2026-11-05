// An imported resume. While it's read, where the reading is; once it's read,
// the resume rebuilt from what Plytos read, beside the person's own file, to
// check at a glance and keep.

import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { ReviewScreen } from "@/components/import-review/review-screen";

import { Reading } from "../reading";
import { loadImport } from "./load";

export const metadata: Metadata = { title: "Your resume, rebuilt" };
export const dynamic = "force-dynamic";

export default async function ImportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const loaded = await loadImport(id);
  // Still being read, or the reading failed: show where it is. It's safe to
  // leave and come back.
  if (loaded.review === null) return <Reading key={loaded.status.id} status={loaded.status} />;
  return (
    <AppShell current="/talk">
      <ReviewScreen key={loaded.review.id} initial={loaded.review} file={loaded.file} />
    </AppShell>
  );
}
