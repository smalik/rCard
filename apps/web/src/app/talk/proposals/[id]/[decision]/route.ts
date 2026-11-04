import {
  dismissProposal,
  getProposedResume,
  keepProposal,
  keepResume,
} from "../../../../../lib/api";
import type { CardContent } from "../../../../../lib/cards";
import { apiProblem, guard, isId, ok, problem, readJson } from "../../../../../lib/routes";

export const dynamic = "force-dynamic";

const GONE = "That suggestion isn't here any more.";

function asContent(value: unknown): CardContent | null | undefined {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object" || Array.isArray(value)) return undefined;
  const content = value as Partial<CardContent>;
  if (typeof content.framing?.headline !== "string" || typeof content.facts !== "object") {
    return undefined;
  }
  return content as CardContent;
}

// A proposed resume as it would read, with the wording drafted for it.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; decision: string }> },
): Promise<Response> {
  const session = await guard(request, "Sign in to see suggestions.");
  if (session instanceof Response) return session;
  const { id, decision } = await params;
  if (!isId(id) || decision !== "resume") return problem(404, GONE);
  try {
    return ok(await getProposedResume(session, id));
  } catch (error) {
    return apiProblem(error, GONE);
  }
}

// Keeps a suggestion, as proposed or with the person's wording, or says no
// to it. A proposed resume is kept as proposed.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; decision: string }> },
): Promise<Response> {
  const session = await guard(request, "Sign in to keep cards.");
  if (session instanceof Response) return session;
  const { id, decision } = await params;
  if (!isId(id)) return problem(404, GONE);
  try {
    if (decision === "dismiss") return ok(await dismissProposal(session, id));
    if (decision === "keep-resume") return ok(await keepResume(session, id), 201);
    if (decision !== "keep") return problem(404, GONE);
    const body = (await readJson(request)) as { content?: unknown } | undefined;
    const content = asContent(body?.content);
    if (content === undefined) return problem(422, "That card couldn't be read.");
    return ok(await keepProposal(session, id, content), 201);
  } catch (error) {
    return apiProblem(error, GONE);
  }
}
