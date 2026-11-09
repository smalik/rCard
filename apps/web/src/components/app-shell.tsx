import Link from "next/link";
import type { ReactNode } from "react";

import { CardsGlyph, PlytosMark, ResumesGlyph, TalkGlyph } from "@/components/glyphs";
import { cn } from "@/lib/utils";

const PLACES = [
  { href: "/talk", label: "Talk", glyph: TalkGlyph },
  { href: "/cards", label: "Cards", glyph: CardsGlyph },
  { href: "/resumes", label: "Resumes", glyph: ResumesGlyph },
] as const;

type Place = (typeof PLACES)[number]["href"];

/** The frame for rebuilt screens: a glass bar along the top on wider
 * screens, and a floating glass tab bar on a phone, as on iOS. */
export function AppShell({ current, children }: { current: Place; children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background font-sans text-foreground antialiased print:min-h-0 print:bg-white">
      <header className="sticky top-0 z-40 hidden border-b border-border/60 bg-background/75 backdrop-blur-xl backdrop-saturate-150 md:block print:hidden">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
          <Link href="/talk" className="flex items-center gap-2 text-[17px] font-extrabold tracking-[-0.015em]">
            <PlytosMark className="size-[22px]" />
            Plytos
          </Link>
          <nav aria-label="Plytos" className="flex items-center gap-1">
            {PLACES.map(({ href, label, glyph: Glyph }) => (
              <Link
                key={href}
                href={href}
                aria-current={href === current ? "page" : undefined}
                className={cn(
                  "flex h-8 items-center gap-1.5 rounded-full px-3 text-[14px] font-bold text-muted-foreground transition-colors hover:text-foreground",
                  href === current && "bg-card text-foreground shadow-sheet",
                )}
              >
                <Glyph className="size-[18px]" filled={href === current} />
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <div className="pb-[calc(6.5rem+env(safe-area-inset-bottom))] md:pb-16 print:p-0">{children}</div>
      {/* Glass floats over the cards; the cards scroll under it. The fade sits
          under anything a screen docks above the tab bar. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[15] h-28 bg-linear-to-b from-transparent to-background/90 md:hidden print:hidden"
      />
      <nav
        aria-label="Plytos"
        className="glass fixed inset-x-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 mx-auto flex h-[62px] max-w-md items-center justify-around rounded-full px-1.5 md:hidden print:hidden"
      >
        {PLACES.map(({ href, label, glyph: Glyph }) => (
          <Link
            key={href}
            href={href}
            aria-current={href === current ? "page" : undefined}
            className={cn(
              "flex min-w-[76px] flex-col items-center gap-0.5 rounded-full px-4 py-1.5 text-[10.5px] font-bold text-muted-foreground",
              href === current && "bg-foreground/[0.07] text-foreground",
            )}
          >
            <Glyph className="size-6" filled={href === current} />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
