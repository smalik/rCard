import { getLibrary } from "@/lib/api";
import { apiProblem, guard, ok } from "@/lib/routes";

export const dynamic = "force-dynamic";

const SIGNED_OUT = "Sign in to see your cards.";

// The whole library, for the cards on screen to stay live.
export async function GET(request: Request): Promise<Response> {
  const session = await guard(request, SIGNED_OUT);
  if (session instanceof Response) return session;
  try {
    return ok(await getLibrary(session));
  } catch (error) {
    return apiProblem(error, "Your cards aren't here.");
  }
}
