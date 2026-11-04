import type { Metadata } from "next";

import { loadReview } from "../load";
import { SettleFlow } from "./settle-flow";

export const metadata: Metadata = { title: "Settle what doesn't line up" };
export const dynamic = "force-dynamic";

export default async function SettlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SettleFlow review={await loadReview(id)} />;
}
