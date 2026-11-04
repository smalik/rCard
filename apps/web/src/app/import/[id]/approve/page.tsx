import type { Metadata } from "next";

import { loadReview } from "../load";
import { ApproveFlow } from "./approve-flow";

export const metadata: Metadata = { title: "Review your cards" };
export const dynamic = "force-dynamic";

export default async function ApprovePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ApproveFlow review={await loadReview(id)} />;
}
