import { setCheckIns } from "../../../lib/api";
import { apiProblem, guard, ok, problem, readJson } from "../../../lib/routes";
import { cleanPlan } from "../../../lib/talk";

export const dynamic = "force-dynamic";

// Sets when Plytos checks in once a month, or turns check-ins off.
export async function POST(request: Request): Promise<Response> {
  const session = await guard(request, "Sign in to talk to Plytos.");
  if (session instanceof Response) return session;
  const plan = cleanPlan(await readJson(request, 1024));
  if (plan === null) return problem(422, "Pick a week, a day and a time.");
  try {
    return ok(await setCheckIns(session, plan));
  } catch (error) {
    return apiProblem(error, "The conversation isn't here.");
  }
}
