import { makeAsWritten } from "../../../lib/api";
import { apiProblem, guard, isId, ok, problem, readJson } from "../../../lib/routes";

export const dynamic = "force-dynamic";

// Makes the person's resume as they wrote it, from the cards they kept from a file.
export async function POST(request: Request): Promise<Response> {
  const session = await guard(request, "Sign in to make your resume.");
  if (session instanceof Response) return session;
  const body = (await readJson(request)) as { import_id?: unknown } | undefined;
  const importId = body?.import_id;
  if (typeof importId !== "string" || !isId(importId)) {
    return problem(404, "That file isn't here any more.");
  }
  try {
    return ok(await makeAsWritten(session, importId), 201);
  } catch (error) {
    return apiProblem(error, "That file isn't here any more.");
  }
}
