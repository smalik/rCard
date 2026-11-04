import { readAgain } from "../../../../lib/api";
import { toStatus } from "../../../../lib/imports";
import { apiProblem, guard, isImportId, ok, problem } from "../../../../lib/routes";

export const dynamic = "force-dynamic";

// Tries a reading that failed once more. The Reading screen then follows it.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");
  try {
    return ok(toStatus(await readAgain(session, id)));
  } catch (error) {
    return apiProblem(error);
  }
}
