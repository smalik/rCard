"use client";

import { createContext, type ReactNode, useContext } from "react";

import type { LibraryCard, LibraryContent } from "@/lib/library";

// What Plytos wrote when asked to sum a job up again.
export type Rewritten = { headline: boolean; stories: number; dropped: number };

export type CardVersion = {
  id: string;
  number: number;
  author_kind: "person" | "ai" | "reviewer";
  created_at: string;
  redacted: boolean;
};

/** What the cards can do with the person's data. The library saves through
 * the API; the sample gallery keeps changes in memory. */
export type CardActions = {
  save(card: LibraryCard, content: LibraryContent): Promise<void>;
  reorder(parentId: string | null, ids: string[]): Promise<void>;
  history(cardId: string): Promise<CardVersion[]>;
  // Asks Plytos to sum a job up again now, from its accomplishments. Left out
  // where Plytos can't write, such as the sample gallery.
  rewrite?(jobId: string, replaceOwn: boolean): Promise<Rewritten>;
  // Cards that changed since the person last looked, to glow for a moment.
  fresh: ReadonlySet<string>;
  // The time the cards measure "2 h ago" against.
  now: Date;
};

const Actions = createContext<CardActions | null>(null);

export function CardActionsProvider({
  value,
  children,
}: {
  value: CardActions;
  children: ReactNode;
}) {
  return <Actions.Provider value={value}>{children}</Actions.Provider>;
}

export function useCardActions(): CardActions {
  const value = useContext(Actions);
  if (!value) throw new Error("Cards need a CardActionsProvider above them.");
  return value;
}
