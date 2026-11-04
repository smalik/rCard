import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ApiError, getConversation } from "../../lib/api";
import { currentSession } from "../../lib/session";
import type { Message } from "../../lib/talk";
import { Talk } from "./talk";

import "./talk.css";

export const metadata: Metadata = { title: "Talk" };
export const dynamic = "force-dynamic";

export default async function TalkPage() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let thread: Message[] = [];
  let failed = false;
  try {
    thread = await getConversation(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }
  return <Talk initial={thread} failed={failed} />;
}
