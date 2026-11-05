import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

// A resume is gone through in the conversation now: the questions first, then
// each job. Old links land there.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/talk?review=${encodeURIComponent(id)}`);
}
