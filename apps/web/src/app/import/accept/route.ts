import { ApiError, acceptImport } from "../../../lib/api";
import { CARD_KINDS, type CardKind } from "../../../lib/cards";
import { type AcceptBody, MAX_ACCEPT_CARDS, contentProblems } from "../../../lib/import-review";
import { isSameOrigin } from "../../../lib/same-origin";
import { currentSession } from "../../../lib/session";

export const dynamic = "force-dynamic";

function problem(status: number, message: string): Response {
  return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}

function isAcceptBody(value: unknown): value is AcceptBody {
  const cards = (value as { cards?: unknown } | null)?.cards;
  if (!Array.isArray(cards) || cards.length === 0 || cards.length > MAX_ACCEPT_CARDS) return false;
  return cards.every((card: unknown) => {
    const c = card as { kind?: unknown; content?: { facts?: unknown; framing?: unknown } };
    const framing = c.content?.framing as { headline?: unknown; body?: unknown } | undefined;
    return (
      CARD_KINDS.includes(c.kind as CardKind) &&
      typeof c.content?.facts === "object" &&
      c.content.facts !== null &&
      typeof framing?.headline === "string" &&
      typeof framing.body === "string" &&
      contentProblems(c.content as AcceptBody["cards"][number]["content"]).length === 0
    );
  });
}

// Saves the cards the person kept from an import, all or none.
export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return problem(403, "This request has to come from Plytos.");
  const session = await currentSession();
  if (!session) return problem(401, "Sign in to save cards.");

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return problem(400, "That request wasn't readable.");
  }
  if (!isAcceptBody(body)) return problem(422, "Some cards can't be saved as they are.");

  try {
    const saved = await acceptImport(session, body);
    return Response.json({ saved: saved.length }, { status: 201 });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 422) return problem(422, "Some cards can't be saved as they are.");
    return problem(502, "Plytos couldn't save your cards just now. Nothing was saved. Try again.");
  }
}
