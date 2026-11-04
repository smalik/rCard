import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { currentSession } from "../../lib/session";
import { ImportFlow } from "./import-flow";

export const metadata: Metadata = { title: "Import your resume" };
export const dynamic = "force-dynamic";

export default async function ImportPage() {
  if (!(await currentSession())) redirect("/sign-in");
  return <ImportFlow />;
}
