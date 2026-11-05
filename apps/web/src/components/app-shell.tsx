import { Layers, FileText, MessageCircle } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const PLACES = [
  { href: "/talk", label: "Talk", icon: MessageCircle },
  { href: "/cards", label: "Cards", icon: Layers },
  { href: "/resumes", label: "Resumes", icon: FileText },
] as const;

type Place = (typeof PLACES)[number]["href"];

/** The frame for rebuilt screens: a translucent bar along the top on wider
 * screens, a tab bar along the bottom on a phone, as on iOS. */
export function AppShell({ current, children }: { current: Place; children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background font-sans text-foreground antialiased print:min-h-0 print:bg-white">
      <header className="sticky top-0 z-40 hidden border-b border-border/70 bg-background/80 backdrop-blur-xl backdrop-saturate-150 md:block print:hidden">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
          <Link href="/talk" className="flex items-center gap-2 text-[15px] font-semibold tracking-[-0.01em]">
            <span className="grid size-7 place-items-center rounded-[9px] bg-primary text-[13px] font-bold text-primary-foreground">
              P
            </span>
            Plytos
          </Link>
          <nav aria-label="Plytos" className="flex items-center gap-1">
            {PLACES.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                aria-current={href === current ? "page" : undefined}
                className={cn(
                  "flex h-8 items-center gap-1.5 rounded-full px-3 text-[14px] font-medium text-muted-foreground transition-colors hover:text-foreground",
                  href === current && "bg-card text-foreground shadow-sheet",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <div className="pb-[calc(4.5rem+env(safe-area-inset-bottom))] md:pb-16 print:p-0">{children}</div>
      <nav
        aria-label="Plytos"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-border/70 bg-background/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl backdrop-saturate-150 md:hidden print:hidden"
      >
        {PLACES.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={href === current ? "page" : undefined}
            className={cn(
              "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium text-muted-foreground",
              href === current && "text-primary",
            )}
          >
            <Icon className="size-[22px]" strokeWidth={href === current ? 2.3 : 1.9} />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
