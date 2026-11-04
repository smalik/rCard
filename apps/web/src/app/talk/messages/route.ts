import { getThread, say } from "../../../lib/api";
import { apiProblem, guard, ok, problem, readJson } from "../../../lib/routes";
import { cleanMessage, MAX_MESSAGE } from "../../../lib/talk";

export const dynamic = "force-dynamic";

const SIGNED_OUT = "Sign in to talk to Plytos.";

// The thread, for the browser to check for Plytos's replies and offers.
export async function GET(request: Request): Promise<Response> {
  const session = await guard(request, SIGNED_OUT);
  if (session instanceof Response) return session;
  try {
    return ok(await getThread(session));
  } catch (error) {
    return apiProblem(error, "The conversation isn't here.");
  }
}

// The person says something. What they wrote is never logged.
export async function POST(request: Request): Promise<Response> {
  const session = await guard(request, SIGNED_OUT);
  if (session instanceof Response) return session;
  const body = (await readJson(request, MAX_MESSAGE * 8)) as { text?: unknown } | undefined;
  const text = typeof body?.text === "string" ? cleanMessage(body.text) : null;
  if (text === null) {
    return problem(422, `Write something up to ${MAX_MESSAGE.toLocaleString("en-US")} characters.`);
  }
  try {
    return ok(await say(session, text), 201);
  } catch (error) {
    return apiProblem(error, "The conversation isn't here.");
  }
}
