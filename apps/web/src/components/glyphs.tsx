import type { ReactNode, SVGProps } from "react";

import { cn } from "@/lib/utils";

/* Plytos's own glyphs, drawn for the field notebook: soft corners, round
   ends, and one stroke of Plytos's blue pen where it means something. They
   inherit the text color; the pen stroke uses --pen. */

type GlyphProps = Omit<SVGProps<SVGSVGElement>, "children"> & {
  // Names the glyph for a screen reader when it stands alone; otherwise hidden.
  title?: string;
};

// The places in the tab bar fill in when chosen.
type PlaceGlyphProps = GlyphProps & { filled?: boolean };

function Glyph({ title, className, children, ...props }: GlyphProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      className={cn("size-6 shrink-0", className)}
      {...props}
    >
      {children}
    </svg>
  );
}

const PEN = "var(--pen)";

/** Talk: a speech bubble with Plytos's pen squiggle in it. */
export function TalkGlyph({ filled, ...props }: PlaceGlyphProps) {
  return (
    <Glyph {...props}>
      <path
        d="M5 4.5h14A2.5 2.5 0 0 1 21.5 7v7a2.5 2.5 0 0 1-2.5 2.5h-8l-4.5 3.5v-3.5H5A2.5 2.5 0 0 1 2.5 14V7A2.5 2.5 0 0 1 5 4.5z"
        fill={filled ? "var(--kraft-soft)" : "none"}
      />
      <path d="M7 10.8c1.5-1.6 2.5 1.6 4 0s2.5 1.6 4 0" stroke={PEN} />
    </Glyph>
  );
}

/** Cards: a pocket notebook, its elastic band in blue. */
export function CardsGlyph({ filled, ...props }: PlaceGlyphProps) {
  return (
    <Glyph {...props}>
      <rect x="5" y="3" width="14" height="18" rx="2.5" fill={filled ? "var(--kraft)" : "none"} />
      <path d="M15.5 3v18" stroke={PEN} />
    </Glyph>
  );
}

/** Resumes: a page, checked off. */
export function ResumesGlyph({ filled, ...props }: PlaceGlyphProps) {
  return (
    <Glyph {...props}>
      <path
        d="M7 2.5h7L18.5 7v12a2.5 2.5 0 0 1-2.5 2.5H7A2.5 2.5 0 0 1 4.5 19V5A2.5 2.5 0 0 1 7 2.5z"
        fill={filled ? "var(--kraft-soft)" : "none"}
      />
      <path d="M8 8h4" />
      <path d="m8 14.5 2 2 4.5-4.5" stroke={PEN} />
    </Glyph>
  );
}

/** A new card. */
export function NewCardGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <rect x="3.5" y="4" width="17" height="16" rx="3" />
      <path d="M12 8.5v7M8.5 12h7" />
    </Glyph>
  );
}

/** Proof: a paper clip, for files and links. */
export function ProofGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <path d="M16.5 7.5V16a4.5 4.5 0 0 1-9 0V6.5a3 3 0 0 1 6 0V15a1.5 1.5 0 0 1-3 0V7.5" />
    </Glyph>
  );
}

/** Plytos wrote this: a pencil with a blue tip. */
export function PlytosWroteGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <path d="M8 18.5 18.5 8a2.1 2.1 0 0 0-3-3L5 15.5" />
      <path d="M5 15.5 4 20l4-1.5z" fill={PEN} stroke={PEN} />
    </Glyph>
  );
}

/** Needs a look: something circled in blue pen. */
export function NeedsLookGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <path
        d="M13 4.6c4.2.4 6.6 3.4 6.6 7.3 0 4.3-3.4 7.6-7.6 7.6S4.4 16.3 4.4 12c0-4.4 3.6-7.6 8.4-7.6"
        stroke={PEN}
      />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </Glyph>
  );
}

/** Highlights: a star, underlined. */
export function HighlightsGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <path d="m12 3.5 2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.8l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z" />
      <path d="M7.5 22h9" stroke={PEN} />
    </Glyph>
  );
}

/** Versions: the clock, turned back. */
export function VersionsGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" stroke={PEN} />
      <path d="M3.5 4v4h4" stroke={PEN} />
      <path d="M12 8v4l2.5 2" />
    </Glyph>
  );
}

/** Search. */
export function SearchGlyph(props: GlyphProps) {
  return (
    <Glyph {...props}>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m15.5 15.5 5 5" />
    </Glyph>
  );
}

/** The Plytos mark: a pocket notebook with a strength checked off in blue. */
export function PlytosMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      className={cn("size-6 shrink-0", className)}
    >
      <rect x="3.5" y="4" width="17" height="16" rx="3" stroke="currentColor" strokeWidth={1.9} />
      <path d="M16.5 4v16" stroke="currentColor" strokeWidth={1.9} />
      <path d="m6.8 12.2 2.2 2.2 3.8-4.2" stroke={PEN} strokeWidth={2.2} />
    </svg>
  );
}
