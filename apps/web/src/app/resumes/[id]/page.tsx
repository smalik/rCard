import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { ApiError, getResume, getResumeVersion } from "../../../lib/api";
import { isId } from "../../../lib/routes";
import type { ResumePage, ResumeVersionPage } from "../../../lib/resumes";
import { currentSession } from "../../../lib/session";
import { ResumeScreen } from "./resume-screen";

import "../resumes.css";

export const metadata: Metadata = { title: "Resume" };
export const dynamic = "force-dynamic";

export default async function ResumeRoute({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  const { id } = await params;
  if (!isId(id)) notFound();
  const v = Number((await searchParams).v ?? "");

  let initial: ResumePage;
  let viewing: ResumeVersionPage | null = null;
  try {
    initial = await getResume(session, id);
    if (Number.isInteger(v) && v >= 1 && v !== initial.resume.head.number) {
      viewing = await getResumeVersion(session, id, v);
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  return <ResumeScreen key={viewing?.version.id ?? "head"} initial={initial} viewing={viewing} />;
}
