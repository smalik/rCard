"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { changedSince, type LibraryCard } from "@/lib/library";

export type Sync = "live" | "syncing" | "offline";

const EVERY_MS = 20_000;
const GLOW_MS = 2_600;

/** Keeps the library in step with the server: it checks every 20 seconds
 * while the page is in view, and at once when the person comes back to it.
 * Cards that changed glow for a moment. */
export function useLiveLibrary(initial: LibraryCard[]) {
  const [cards, setCards] = useState(initial);
  const [fresh, setFresh] = useState<ReadonlySet<string>>(new Set());
  const [sync, setSync] = useState<Sync>("live");
  const [syncedAt, setSyncedAt] = useState(() => new Date());
  const latest = useRef(initial);
  const busy = useRef(false);

  const refresh = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setSync("syncing");
    try {
      const response = await fetch("/cards/library", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      const next = (await response.json()) as LibraryCard[];
      const changed = changedSince(latest.current, next);
      latest.current = next;
      setCards(next);
      setSyncedAt(new Date());
      setSync("live");
      if (changed.size > 0) {
        setFresh(changed);
        window.setTimeout(() => setFresh(new Set()), GLOW_MS);
      }
    } catch {
      setSync("offline");
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    const tick = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, EVERY_MS);
    const back = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", back);
    window.addEventListener("focus", back);
    return () => {
      window.clearInterval(tick);
      document.removeEventListener("visibilitychange", back);
      window.removeEventListener("focus", back);
    };
  }, [refresh]);

  // An arrangement the person just made shows at once, before the server answers.
  const arrange = useCallback((change: (cards: LibraryCard[]) => LibraryCard[]) => {
    const next = change(latest.current);
    latest.current = next;
    setCards(next);
  }, []);

  return { cards, fresh, sync, syncedAt, refresh, arrange };
}
