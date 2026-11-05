import { reorderCards } from "@/lib/api";
import { apiProblem, guard, isId, ok, problem, readJson } from "@/lib/routes";

export const dynamic = "force-dynamic";

// Puts cards that share a parent in the order the person dragged them into.
export async function POST(request: Request): Promise<Response> {
  const session = await guard(request, "Sign in to arrange your cards.");
  if (session instanceof Response) return session;
  const body = (await readJson(request)) as { parent_id?: unknown; card_ids?: unknown } | undefined;
  const parent = body?.parent_id ?? null;
  const ids = body?.card_ids;
  if (
    (parent !== null && (typeof parent !== "string" || !isId(parent))) ||
    !Array.isArray(ids) ||
    ids.length === 0 ||
    ids.length > 500 ||
    !ids.every((id) => typeof id === "string" && isId(id))
  ) {
    return problem(422, "Those cards can't be arranged that way.");
  }
  try {
    await reorderCards(session, parent as string | null, ids as string[]);
    return ok({ ok: true });
  } catch (error) {
    return apiProblem(error, "Those cards aren't here any more.");
  }
}
