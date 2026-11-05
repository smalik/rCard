import { getResume, saveResume } from "@/lib/api";
import type { ResumeHeader } from "@/lib/resumes";
import { apiProblem, guard, isId, ok, problem, readJson } from "@/lib/routes";

export const dynamic = "force-dynamic";

const LIMITS: Record<Exclude<keyof ResumeHeader, "links">, number> = {
  name: 120,
  headline: 200,
  email: 200,
  phone: 60,
  location: 120,
  summary: 1500,
};

function cleanHeader(raw: unknown): ResumeHeader | null {
  if (typeof raw !== "object" || raw === null) return null;
  const h = raw as Record<string, unknown>;
  const out: Partial<ResumeHeader> = {};
  for (const [key, max] of Object.entries(LIMITS) as [keyof typeof LIMITS, number][]) {
    const value = h[key] ?? "";
    if (typeof value !== "string" || value.length > max) return null;
    out[key] = value.trim();
  }
  const links = h.links ?? [];
  if (!Array.isArray(links) || links.length > 5) return null;
  if (!links.every((l) => typeof l === "string" && l.length <= 300)) return null;
  return { ...(out as Omit<ResumeHeader, "links">), links: (links as string[]).map((l) => l.trim()) };
}

// Saves the contact card: the top of one resume, as that resume's next version.
export async function POST(request: Request): Promise<Response> {
  const session = await guard(request, "Sign in to change your cards.");
  if (session instanceof Response) return session;
  const body = (await readJson(request)) as
    | { resume_id?: unknown; base_version_id?: unknown; header?: unknown }
    | undefined;
  const id = body?.resume_id;
  const base = body?.base_version_id;
  const header = cleanHeader(body?.header);
  if (typeof id !== "string" || !isId(id) || typeof base !== "string" || !isId(base) || !header) {
    return problem(422, "That contact card can't be saved. Check it and try again.");
  }
  try {
    const { resume } = await getResume(session, id);
    const saved = await saveResume(session, id, base, {
      ...resume.content,
      header,
      note: null,
    });
    return ok({ base_version_id: saved.resume.head.id }, 201);
  } catch (error) {
    return apiProblem(error, "That resume isn't here any more.");
  }
}
