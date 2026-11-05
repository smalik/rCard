import { saveCardVersion } from "@/lib/api";
import { cleanContent } from "@/lib/library";
import { apiProblem, guard, isId, ok, problem, readJson } from "@/lib/routes";

export const dynamic = "force-dynamic";

// Saves the person's edit as the card's next version. Card text is never logged.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request, "Sign in to change your cards.");
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isId(id)) return problem(404, "That card isn't here.");
  const body = (await readJson(request, 256 * 1024)) as
    | { base_version_id?: unknown; content?: unknown }
    | undefined;
  const base = body?.base_version_id;
  const content = cleanContent(body?.content);
  if (typeof base !== "string" || !isId(base) || content === null) {
    return problem(422, "That change can't be saved. Check the card and try again.");
  }
  try {
    await saveCardVersion(session, id, base, content);
    return ok({ ok: true }, 201);
  } catch (error) {
    return apiProblem(error, "That card isn't here any more.");
  }
}
