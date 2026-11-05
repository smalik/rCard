import { keepGroup } from "../../../../lib/api";
import type { CardContent } from "../../../../lib/cards";
import {
  cleanContent,
  contentProblems,
  type MatchChoice,
  toReview,
} from "../../../../lib/imports";
import {
  apiProblem,
  guard,
  isCardRef,
  isImportId,
  ok,
  problem,
  readJson,
} from "../../../../lib/routes";

export const dynamic = "force-dynamic";

const CHOICES: MatchChoice[] = ["update", "keep", "separate"];
const MOST = 500;

function isContent(value: unknown): value is CardContent {
  const c = value as { facts?: unknown; framing?: { headline?: unknown; body?: unknown } } | null;
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

function refs(value: unknown): string[] | null {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > MOST) return null;
  return value.every((r) => typeof r === "string" && isCardRef(r)) ? (value as string[]) : null;
}

type Kept = { ref: string; content: CardContent | null; choice: MatchChoice | null };

function kept(value: unknown): Kept[] | string | null {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > MOST) return null;
  const out: Kept[] = [];
  for (const item of value as { ref?: unknown; content?: unknown; choice?: unknown }[]) {
    if (typeof item !== "object" || item === null) return null;
    if (typeof item.ref !== "string" || !isCardRef(item.ref)) return null;
    const content = item.content ?? null;
    if (content !== null) {
      if (!isContent(content)) return null;
      const problems = contentProblems(content);
      if (problems.length > 0) return problems.join(" ");
    }
    const choice = item.choice ?? null;
    if (choice !== null && !CHOICES.includes(choice as MatchChoice)) return null;
    out.push({ ref: item.ref, content: content && cleanContent(content), choice: choice as MatchChoice | null });
  }
  return out;
}

// Keeps a job and what's under it in one go, as the person goes through their
// resume in the conversation: some kept (in their words where they changed
// them), some left out, some set aside. Answers with the new progress and which
// of the person's cards the rest now stand for.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");

  const body = (await readJson(request, 256 * 1024)) as
    | { keep?: unknown; leave_out?: unknown; later?: unknown }
    | undefined;
  const keep = kept(body?.keep);
  if (typeof keep === "string") return problem(422, keep);
  const leaveOut = refs(body?.leave_out);
  const later = refs(body?.later);
  if (keep === null || leaveOut === null || later === null) {
    return problem(400, "That didn't come through. Try again.");
  }
  if (keep.length + leaveOut.length + later.length === 0) {
    return problem(400, "Nothing to keep there.");
  }
  try {
    const review = toReview(await keepGroup(session, id, { keep, leave_out: leaveOut, later }));
    return ok({ progress: review.progress, matches: review.matches });
  } catch (error) {
    return apiProblem(error);
  }
}
