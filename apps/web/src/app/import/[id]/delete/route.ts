import { deleteImport } from "../../../../lib/api";
import { apiProblem, guard, isImportId, ok, problem } from "../../../../lib/routes";

export const dynamic = "force-dynamic";

// Deletes the original file and everything read from it. Approved cards stay.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");
  try {
    await deleteImport(session, id);
    return ok({ deleted: true });
  } catch (error) {
    return apiProblem(error);
  }
}
