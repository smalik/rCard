import { ApiError, rewriteSummaries } from "@/lib/api";
import { apiProblem, guard, isId, ok, problem, readJson } from "@/lib/routes";

export const dynamic = "force-dynamic";

// Asks Plytos to sum a job up again now: its headline and each title's story,
// from the accomplishments. The person's own words stay unless they say so.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request, "Sign in to change your cards.");
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isId(id)) return problem(404, "That card isn't here.");
  const body = (await readJson(request)) as { replace_own?: unknown } | undefined;
  const replaceOwn = body?.replace_own === true;
  try {
    return ok(await rewriteSummaries(session, id, replaceOwn));
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      return problem(503, "Plytos can't write right now: AI is turned off here.");
    }
    if (error instanceof ApiError && error.status === 502) {
      return problem(502, "Plytos couldn't write that just now. Try again in a moment.");
    }
    return apiProblem(error, "That job isn't here any more.");
  }
}
