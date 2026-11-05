"use client";

import {
  Award,
  BadgeCheck,
  BriefcaseBusiness,
  Contact,
  FolderGit2,
  GraduationCap,
  type LucideIcon,
  Presentation,
  RotateCcw,
  Star,
  Wrench,
} from "lucide-react";
import {
  type ReactNode,
  useCallback,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { relativeTime } from "@/lib/library";
import { cn } from "@/lib/utils";

export type Purpose =
  | "experience"
  | "contact"
  | "education"
  | "award"
  | "credential"
  | "skill"
  | "project"
  | "activity"
  | "highlight";

export const PURPOSES: Record<Purpose, { label: string; icon: LucideIcon; tile: string }> = {
  experience: { label: "Work experience", icon: BriefcaseBusiness, tile: "bg-kind-experience" },
  contact: { label: "Contact", icon: Contact, tile: "bg-kind-contact" },
  education: { label: "Education", icon: GraduationCap, tile: "bg-kind-education" },
  award: { label: "Award", icon: Award, tile: "bg-kind-award" },
  credential: { label: "Certification", icon: BadgeCheck, tile: "bg-kind-credential" },
  skill: { label: "Skills", icon: Wrench, tile: "bg-kind-skill" },
  project: { label: "Project", icon: FolderGit2, tile: "bg-kind-project" },
  activity: { label: "Activity", icon: Presentation, tile: "bg-kind-activity" },
  highlight: { label: "Highlight", icon: Star, tile: "bg-kind-position" },
};

/** The rounded, colored glyph that says what kind of card this is, as iOS
 * settings rows do. Always shown with its label. */
export function KindTile({ purpose, className }: { purpose: Purpose; className?: string }) {
  const { icon: Icon, tile } = PURPOSES[purpose];
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-7 shrink-0 place-items-center rounded-[9px] text-white shadow-[inset_0_-1px_0_rgba(0,0,0,0.12)] dark:text-black/80",
        tile,
        className,
      )}
    >
      <Icon className="size-4" strokeWidth={2.2} />
    </span>
  );
}

export type Live = {
  version: number;
  updatedAt: string;
  author: "person" | "ai" | "reviewer";
  variantsBehind?: number;
};

/** The card's freshness, read from its data: which version, when, and by whom. */
export function LiveMeta({ live, now }: { live: Live; now: Date }) {
  const by = live.author === "ai" ? "drafted by Plytos" : live.author === "reviewer" ? "reviewed" : "";
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground tabular-nums">
      <span className="font-mono text-[11px] font-medium text-foreground/70">v{live.version}</span>
      <span aria-hidden>·</span>
      {/* The server and the browser can read the clock a moment apart. */}
      <time dateTime={live.updatedAt} suppressHydrationWarning>
        {relativeTime(live.updatedAt, now)}
      </time>
      {by && (
        <>
          <span aria-hidden>·</span>
          <span>{by}</span>
        </>
      )}
      {(live.variantsBehind ?? 0) > 0 && (
        <span className="ml-1 rounded-full bg-live-soft px-1.5 py-px text-[11px] font-medium text-foreground">
          {live.variantsBehind} to refresh
        </span>
      )}
    </span>
  );
}

/** A solid disclosure triangle, as in Finder and iOS outlines. */
export function DisclosureTriangle({ open, className }: { open: boolean; className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className={cn(
        "size-3 shrink-0 text-muted-foreground transition-transform duration-200 ease-out motion-reduce:transition-none",
        open && "rotate-90",
        className,
      )}
    >
      <path d="M4 2.2 9.2 6 4 9.8Z" fill="currentColor" />
    </svg>
  );
}

function FlipButton({
  side,
  onFlip,
  controls,
  buttonRef,
  quietRef,
}: {
  side: "front" | "back";
  onFlip: (byPointer: boolean) => void;
  controls: string;
  buttonRef?: React.Ref<HTMLButtonElement>;
  // Set while focus lands here from a tap or click on the other side, so the
  // tip doesn't pop up under the pointer; a key press still shows it.
  quietRef: React.RefObject<boolean>;
}) {
  const label = side === "front" ? "Turn over: facts, evidence and history" : "Turn back to the front";
  const [tip, setTip] = useState(false);
  return (
    <Tooltip open={tip} onOpenChange={(open) => setTip(open && !quietRef.current)}>
      <TooltipTrigger asChild>
        <button
          ref={buttonRef}
          type="button"
          // A click from a key press has no click count.
          onClick={(e) => onFlip(e.detail > 0)}
          onPointerMove={() => {
            quietRef.current = false;
          }}
          onBlur={() => {
            quietRef.current = false;
          }}
          aria-controls={controls}
          aria-label={label}
          className="grid size-8 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
        >
          <RotateCcw className="size-[15px]" strokeWidth={2.2} />
        </button>
      </TooltipTrigger>
      <TooltipContent>{side === "front" ? "Turn over" : "Front"}</TooltipContent>
    </Tooltip>
  );
}

type FaceProps = {
  purpose: Purpose;
  title?: string;
  live?: Live;
  now: Date;
  side: "front" | "back";
  onFlip: (byPointer: boolean) => void;
  controls: string;
  menu?: ReactNode;
  children: ReactNode;
  compact?: boolean;
  buttonRef?: React.Ref<HTMLButtonElement>;
  quietRef: React.RefObject<boolean>;
};

function Face({
  purpose,
  title,
  live,
  now,
  side,
  onFlip,
  controls,
  menu,
  children,
  compact,
  buttonRef,
  quietRef,
}: FaceProps) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-2xl border bg-card text-card-foreground shadow-card",
        compact ? "gap-2.5 p-3.5" : "gap-4 p-4 sm:p-5",
        side === "back" && "bg-[color-mix(in_oklab,var(--card),var(--muted)_45%)]",
      )}
    >
      <header className="-mt-1 -mr-1.5 flex min-h-8 items-center gap-2">
        <KindTile purpose={purpose} className="size-6 rounded-[7px] [&_svg]:size-3.5" />
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="truncate text-[12px] font-semibold tracking-[0.03em] text-muted-foreground uppercase">
            {side === "back" ? `${title ?? PURPOSES[purpose].label} · back` : (title ?? PURPOSES[purpose].label)}
          </span>
          {live && !compact && <LiveMeta live={live} now={now} />}
        </div>
        {menu}
        <FlipButton
          side={side}
          onFlip={onFlip}
          controls={controls}
          buttonRef={buttonRef}
          quietRef={quietRef}
        />
      </header>
      {children}
    </div>
  );
}

export type StrengthCardProps = {
  purpose: Purpose;
  // Overrides the purpose's label in the card's top line.
  title?: string;
  // What a screen reader calls the card, such as "Work experience: Contoso Bank".
  label: string;
  live?: Live;
  now: Date;
  // Glows for a moment: the card just changed.
  fresh?: boolean;
  front: ReactNode;
  // Rendered the first time the card is turned over.
  back: () => ReactNode;
  menu?: ReactNode;
  compact?: boolean;
  className?: string;
};

/** The card primitive: a front for how it's told, a back for its facts,
 * evidence and history. Both sides are interactive; the card turns over in
 * 3D, and its height follows the side in view. */
export function StrengthCard({
  purpose,
  title,
  label,
  live,
  now,
  fresh,
  front,
  back,
  menu,
  compact,
  className,
}: StrengthCardProps) {
  const [side, setSide] = useState<"front" | "back">("front");
  const [backShown, setBackShown] = useState(false);
  const [height, setHeight] = useState<number | undefined>(undefined);
  const frontRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLDivElement>(null);
  const frontButton = useRef<HTMLButtonElement>(null);
  const backButton = useRef<HTMLButtonElement>(null);
  const moved = useRef(false);
  const quietRef = useRef(false);
  const id = useId();

  useLayoutEffect(() => {
    const face = side === "front" ? frontRef.current : backRef.current;
    if (!face) return;
    const measure = () => setHeight(face.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(face);
    return () => observer.disconnect();
  }, [side, backShown]);

  useLayoutEffect(() => {
    if (!moved.current) return;
    (side === "front" ? frontButton : backButton).current?.focus({ preventScroll: true });
  }, [side]);

  const flip = useCallback((byPointer: boolean) => {
    moved.current = true;
    quietRef.current = byPointer;
    setBackShown(true);
    setSide((s) => (s === "front" ? "back" : "front"));
  }, []);

  return (
    <section
      aria-label={label}
      className={cn("flip-scene rounded-2xl", fresh && "animate-live-glow", className)}
    >
      <div
        className="flip-body grid grid-cols-[minmax(0,1fr)]"
        data-side={side}
        style={height === undefined ? undefined : { height }}
      >
        <div
          ref={frontRef}
          id={`${id}-front`}
          className="flip-face min-w-0 [grid-area:1/1] self-start"
          data-face="front"
          aria-hidden={side !== "front"}
          inert={side !== "front"}
        >
          <Face
            purpose={purpose}
            title={title}
            live={live}
            now={now}
            side="front"
            onFlip={flip}
            controls={`${id}-back`}
            menu={menu}
            compact={compact}
            buttonRef={frontButton}
            quietRef={quietRef}
          >
            {front}
          </Face>
        </div>
        {backShown && (
          <div
            ref={backRef}
            id={`${id}-back`}
            className="flip-face min-w-0 [grid-area:1/1] self-start"
            data-face="back"
            aria-hidden={side !== "back"}
            inert={side !== "back"}
          >
            <Face
              purpose={purpose}
              title={title}
              live={live}
              now={now}
              side="back"
              onFlip={flip}
              controls={`${id}-front`}
              compact={compact}
              buttonRef={backButton}
              quietRef={quietRef}
            >
              {back()}
            </Face>
          </div>
        )}
      </div>
    </section>
  );
}
