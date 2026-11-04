import { createImport } from "../../../lib/api";
import { FILENAME_HEADER, MAX_IMPORT_BYTES, toReview } from "../../../lib/imports";
import { apiProblem, guard, ok, problem, readCapped } from "../../../lib/routes";

export const dynamic = "force-dynamic";

const TOO_LARGE = "Resumes over 5 MB aren't supported.";

// The browser sends the resume (a file, or pasted text) here; this server
// passes it to the private API, which keeps the original encrypted with the
// person's own key. Nothing about the file is logged.
export async function POST(request: Request): Promise<Response> {
  const session = await guard(request);
  if (session instanceof Response) return session;

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_IMPORT_BYTES) return problem(413, TOO_LARGE);
  const data = await readCapped(request, MAX_IMPORT_BYTES);
  if (data === null) return problem(413, TOO_LARGE);
  if (data.byteLength === 0) return problem(422, "The file is empty.");

  const filename = (request.headers.get(FILENAME_HEADER) ?? "").slice(0, 600) || "resume";
  try {
    const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    const view = await createImport(session, buffer as ArrayBuffer, filename);
    return ok(toReview(view), 201);
  } catch (error) {
    return apiProblem(error);
  }
}
