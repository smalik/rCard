import "server-only";

import { notFound, redirect } from "next/navigation";

import { ApiError, getImport } from "../../../lib/api";
import { type Review, toReview } from "../../../lib/imports";
import { isImportId } from "../../../lib/routes";
import { currentSession } from "../../../lib/session";

// The import a page is about, read for the signed-in person. Someone else's
// import, or one that was deleted, is simply not found.
export async function loadReview(id: string): Promise<Review> {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  if (!isImportId(id)) notFound();
  try {
    return toReview(await getImport(session, id));
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
}
