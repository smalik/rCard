import {
  askForVersion,
  copyResume,
  nameResumeVersion,
  parentChanges,
  previewResume,
  renameResume,
  restoreResume,
  saveResume,
  takeChanges,
} from "../../../../lib/api";
import { apiProblem, guard, isId, ok, problem, readJson } from "../../../../lib/routes";
import { cleanContent, cleanLine, RESUME_NAME_MAX, TARGET_MAX } from "../../../../lib/resumes";
import { MAX_MESSAGE } from "../../../../lib/talk";

export const dynamic = "force-dynamic";

const GONE = "That resume isn't here any more.";

type Params = { params: Promise<{ id: string; action: string }> };

function versionNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 && value < 1_000_000
    ? value
    : null;
}

function baseId(value: unknown): string | null {
  return typeof value === "string" && isId(value) ? value : null;
}

// The changes the person still has to decide on, from the resume this one
// was made from.
export async function GET(request: Request, { params }: Params): Promise<Response> {
  const session = await guard(request, "Sign in to see your resumes.");
  if (session instanceof Response) return session;
  const { id, action } = await params;
  if (!isId(id) || action !== "parent-changes") return problem(404, GONE);
  try {
    return ok(await parentChanges(session, id));
  } catch (error) {
    return apiProblem(error, GONE);
  }
}

// Changes to a resume: preview, save, restore, name, rename, take changes,
// copy, or ask Plytos for a version.
export async function POST(request: Request, { params }: Params): Promise<Response> {
  const session = await guard(request, "Sign in to change your resumes.");
  if (session instanceof Response) return session;
  const { id, action } = await params;
  if (!isId(id)) return problem(404, GONE);
  const body = (await readJson(request, 512 * 1024)) as Record<string, unknown> | undefined;
  if (!body || typeof body !== "object") return problem(422, "That request couldn't be read.");
  try {
    switch (action) {
      case "preview": {
        const content = cleanContent(body.content);
        if (!content) return problem(422, "That resume couldn't be read.");
        return ok(await previewResume(session, id, content));
      }
      case "save": {
        const content = cleanContent(body.content);
        const base = baseId(body.base_version_id);
        if (!content || !base) return problem(422, "That resume couldn't be read.");
        return ok(await saveResume(session, id, base, content), 201);
      }
      case "restore": {
        const number = versionNumber(body.number);
        const base = baseId(body.base_version_id);
        if (!number || !base) return problem(422, "Pick a version to bring back.");
        return ok(await restoreResume(session, id, number, base), 201);
      }
      case "name": {
        const number = versionNumber(body.number);
        const name = cleanLine(body.name, RESUME_NAME_MAX);
        if (!number || !name) return problem(422, "Give the version a short name.");
        return ok(await nameResumeVersion(session, id, number, name));
      }
      case "rename": {
        const name = cleanLine(body.name, RESUME_NAME_MAX);
        if (!name) return problem(422, "Give the resume a short name.");
        return ok(await renameResume(session, id, name));
      }
      case "take": {
        const base = baseId(body.base_version_id);
        const keys = body.keys;
        if (
          !base ||
          !Array.isArray(keys) ||
          keys.length > 1000 ||
          !keys.every((k) => typeof k === "string" && k.length <= 120)
        ) {
          return problem(422, "Pick the changes to take.");
        }
        const parent = body.parent_version_id;
        const parentVersion = parent === undefined || parent === null ? null : baseId(parent);
        if (parent != null && !parentVersion) return problem(422, "Pick the changes to take.");
        return ok(await takeChanges(session, id, keys as string[], base, parentVersion), 201);
      }
      case "copy": {
        const target = cleanLine(body.target, TARGET_MAX);
        if (!target) return problem(422, "Say who this version is for.");
        return ok(await copyResume(session, id, target.slice(0, RESUME_NAME_MAX), target), 201);
      }
      case "ask": {
        const text = cleanLine(body.text, MAX_MESSAGE);
        if (!text) return problem(422, "Say who this version is for.");
        return ok(await askForVersion(session, id, text), 201);
      }
      default:
        return problem(404, GONE);
    }
  } catch (error) {
    return apiProblem(error, GONE);
  }
}
