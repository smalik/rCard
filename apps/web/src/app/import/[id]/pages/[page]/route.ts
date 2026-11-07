import { getPage } from "../../../../../lib/api";
import { currentSession } from "../../../../../lib/session";
import { apiProblem, isImportId, problem } from "../../../../../lib/routes";

export const dynamic = "force-dynamic";

// A page of the person's resume as a picture, shown beside the cards read from
// it so they can check the wording. Drawn for them each time and never cached.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string; page: string }> },
): Promise<Response> {
  const session = await currentSession();
  if (!session) return problem(401, "Sign in to see your file.");
  const { id, page } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");
  const number = Number(page);
  if (!/^[1-9][0-9]{0,2}$/.test(page) || !Number.isInteger(number)) {
    return problem(404, "That page isn't in this file.");
  }
  try {
    const picture = await getPage(session, id, number);
    return new Response(picture.data, {
      headers: { "Content-Type": picture.type, "Cache-Control": "no-store" },
    });
  } catch (error) {
    return apiProblem(error);
  }
}
