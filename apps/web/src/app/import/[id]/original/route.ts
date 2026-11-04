import { getOriginal } from "../../../../lib/api";
import { currentSession } from "../../../../lib/session";
import { apiProblem, isImportId, problem } from "../../../../lib/routes";

export const dynamic = "force-dynamic";

// Shows the person their original file. A PDF or text file opens in the
// browser; a Word file downloads, since browsers can't show one.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await currentSession();
  if (!session) return problem(401, "Sign in to see your file.");
  const { id } = await params;
  if (!isImportId(id)) return problem(404, "That import isn't here any more.");
  try {
    const original = await getOriginal(session, id);
    const inline = !original.type.includes("wordprocessingml");
    const ascii = original.name.replace(/[^\x20-\x7e]|["\\]/g, "_");
    return new Response(original.data, {
      headers: {
        "Content-Type": original.type,
        "Content-Disposition": `${inline ? "inline" : "attachment"}; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(original.name)}`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return apiProblem(error);
  }
}
