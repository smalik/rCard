import { settleQuestion } from "../../../../lib/api";
import type { Answer } from "../../../../lib/imports";
import { apiProblem, guard, isImportId, ok, problem, readJson } from "../../../../lib/routes";

export const dynamic = "force-dynamic";

const ANSWERS: Answer[] = ["chosen", "as_is", "on_card", "later"];

// Records the person's answer to one question, such as which of two numbers is right.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;
  const { id } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");

  const body = (await readJson(request)) as
    | { finding?: unknown; answer?: unknown; value?: unknown }
    | undefined;
  const finding = body?.finding;
  const answer = body?.answer;
  const value = body?.value ?? null;
  if (
    typeof finding !== "number" ||
    !Number.isInteger(finding) ||
    finding < 0 ||
    !ANSWERS.includes(answer as Answer) ||
    (value !== null && (typeof value !== "string" || value.length > 40))
  ) {
    return problem(400, "That answer didn't come through. Try again.");
  }
  try {
    return ok(
      await settleQuestion(session, id, {
        finding,
        answer: answer as Answer,
        value,
      }),
    );
  } catch (error) {
    return apiProblem(error);
  }
}
