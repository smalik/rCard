import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ApiError, getThread } from "../../lib/api";
import { currentSession } from "../../lib/session";
import { NO_CHECK_INS, type Thread } from "../../lib/talk";
import { Talk } from "./talk";

import "./talk.css";

export const metadata: Metadata = { title: "Talk" };
export const dynamic = "force-dynamic";

export default async function TalkPage() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let thread: Thread = { messages: [], resumes: [], check_ins: NO_CHECK_INS };
  let failed = false;
  try {
    thread = await getThread(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }
  return <Talk initial={thread} failed={failed} />;
}
