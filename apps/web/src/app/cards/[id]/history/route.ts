import { cardHistory } from "@/lib/api";
import { apiProblem, guard, isId, ok, problem } from "@/lib/routes";

export const dynamic = "force-dynamic";

// A card's versions, newest last, for the back of the card.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request, "Sign in to see your cards.");
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isId(id)) return problem(404, "That card isn't here.");
  try {
    return ok(await cardHistory(session, id));
  } catch (error) {
    return apiProblem(error, "That card isn't here any more.");
  }
}
