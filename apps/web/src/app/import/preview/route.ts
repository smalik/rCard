import { ApiError, previewImport } from "../../../lib/api";
import { MAX_IMPORT_BYTES, FILENAME_HEADER, toPreview } from "../../../lib/import-review";
import { isSameOrigin } from "../../../lib/same-origin";
import { currentSession } from "../../../lib/session";

export const dynamic = "force-dynamic";

const TOO_LARGE = "Resumes over 5 MB aren't supported.";

function problem(status: number, message: string): Response {
  return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}

// Reads the request body, giving up as soon as it passes the size limit.
async function readCapped(request: Request, max: number): Promise<Uint8Array | null> {
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}

// The browser sends the resume here; this server passes it to the private
// API and returns the review. Nothing is stored, and nothing about the file
// is logged.
export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return problem(403, "This request has to come from Plytos.");
  const session = await currentSession();
  if (!session) return problem(401, "Sign in to import a resume.");

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_IMPORT_BYTES) return problem(413, TOO_LARGE);
  const data = await readCapped(request, MAX_IMPORT_BYTES);
  if (data === null) return problem(413, TOO_LARGE);
  if (data.byteLength === 0) return problem(422, "The file is empty.");

  const filename = (request.headers.get(FILENAME_HEADER) ?? "").slice(0, 600) || "resume";
  try {
    const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    const result = await previewImport(session, buffer as ArrayBuffer, filename);
    return Response.json(toPreview(result), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if ((error.status === 413 || error.status === 422) && error.detail) {
      return problem(error.status, error.detail);
    }
    return problem(502, "Plytos couldn't read that file just now. Try again in a moment.");
  }
}
