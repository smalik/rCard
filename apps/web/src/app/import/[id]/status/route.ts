import { getImport, getImportStatus } from "../../../../lib/api";
import { type ReadingStatus, toReview, toStatus } from "../../../../lib/imports";
import { apiProblem, guard, isImportId, ok, problem } from "../../../../lib/routes";

export const dynamic = "force-dynamic";

// Where the reading is, for the Reading screen to ask every second or two.
// Once it's read, what was found comes with it, so the screen can show it.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");
  try {
    const status = toStatus(await getImportStatus(session, id));
    const review = status.state === "read" ? toReview(await getImport(session, id)) : null;
    return ok({ ...status, review } satisfies ReadingStatus);
  } catch (error) {
    return apiProblem(error);
  }
}
