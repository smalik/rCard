import { redirect } from "next/navigation";

import { currentSession } from "../lib/session";

export const dynamic = "force-dynamic";

export default async function Home() {
  redirect((await currentSession()) ? "/cards" : "/sign-in");
}
