import "server-only";

import { notFound, redirect } from "next/navigation";

import { ApiError, getImport } from "../../../lib/api";
import { type ImportStatus, type Review, toReview, toStatus } from "../../../lib/imports";
import { isImportId } from "../../../lib/routes";
import { currentSession } from "../../../lib/session";

// The import a page is about, read for the signed-in person: what was read,
// or, while it's still being read or the reading failed, where it is. Someone
// else's import, or one that was deleted, is simply not found.
export async function loadImport(
  id: string,
): Promise<{ review: Review; status: null } | { review: null; status: ImportStatus }> {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  if (!isImportId(id)) notFound();
  let raw: unknown;
  try {
    raw = await getImport(session, id);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const status = toStatus(raw);
  return status.state === "read"
    ? { review: toReview(raw), status: null }
    : { review: null, status };
}

// What was read, for the pages that need it. Until then they send the person
// to the import's own page, which shows the reading.
export async function loadReview(id: string): Promise<Review> {
  const { review } = await loadImport(id);
  if (review === null) redirect(`/import/${id}`);
  return review;
}
