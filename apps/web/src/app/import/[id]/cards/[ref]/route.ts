import { approveCard, decideCard } from "../../../../../lib/api";
import type { CardContent } from "../../../../../lib/cards";
import { cleanContent, contentProblems } from "../../../../../lib/imports";
import {
  apiProblem,
  guard,
  isCardRef,
  isImportId,
  ok,
  problem,
  readJson,
} from "../../../../../lib/routes";

export const dynamic = "force-dynamic";

function isContent(value: unknown): value is CardContent {
  const c = value as {
    facts?: unknown;
    framing?: { headline?: unknown; body?: unknown };
  } | null;
  return (
    typeof c === "object" &&
    c !== null &&
    typeof c.facts === "object" &&
    c.facts !== null &&
    !Array.isArray(c.facts) &&
    typeof c.framing?.headline === "string" &&
    typeof c.framing.body === "string"
  );
}

// The person's decision on one proposed card: approve it (as it is, or in
// their edited words), set it aside for later, leave it out, or undo that.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; ref: string }> },
): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;
  const { id, ref } = await params;
  if (!isImportId(id) || !isCardRef(ref)) return problem(404, "That card isn't here any more.");

  const body = (await readJson(request)) as { action?: unknown; content?: unknown } | undefined;
  const action = body?.action;
  try {
    if (action === "approve") {
      const content = body?.content ?? null;
      if (content !== null) {
        if (!isContent(content)) return problem(400, "That card didn't come through. Try again.");
        const problems = contentProblems(content);
        if (problems.length > 0) return problem(422, problems.join(" "));
      }
      const result = await approveCard(session, id, ref, content && cleanContent(content));
      return ok(result.progress, 201);
    }
    if (action === "later" || action === "dropped" || action === "pending") {
      return ok(await decideCard(session, id, ref, action));
    }
    return problem(400, "That didn't come through. Try again.");
  } catch (error) {
    return apiProblem(error);
  }
}
