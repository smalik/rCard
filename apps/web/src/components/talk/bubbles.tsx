import { FileText } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Plytos's mark beside what it says, as a contact's picture in Messages. */
export function PlytosMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-7 shrink-0 place-items-center rounded-full bg-primary text-[12px] font-bold text-primary-foreground",
        className,
      )}
    >
      P
    </span>
  );
}

/** Something Plytos says: its words in a bubble, and anything it hands over
 * (a draft, a question's answers) under them. */
export function PlytosSays({
  children,
  attached,
  label,
}: {
  children?: ReactNode;
  attached?: ReactNode;
  label?: string;
}) {
  return (
    <div className="flex items-start gap-2" aria-label={label}>
      <PlytosMark className="mt-0.5" />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-2">
        {children && (
          <div className="max-w-[92%] rounded-[20px] rounded-tl-md bg-card px-4 py-2.5 text-[15px] leading-[1.45] shadow-sheet sm:max-w-[85%]">
            {children}
          </div>
        )}
        {attached}
      </div>
    </div>
  );
}

/** What the person said, on the right, as in Messages. */
export function PersonSays({
  children,
  file,
  pending,
}: {
  children?: ReactNode;
  file?: string;
  pending?: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-end gap-1", pending && "opacity-60")}>
      {children && (
        <div className="max-w-[85%] rounded-[20px] rounded-br-md bg-primary px-4 py-2.5 text-[15px] leading-[1.45] whitespace-pre-wrap text-primary-foreground sm:max-w-[75%]">
          {children}
        </div>
      )}
      {file && (
        <p className="flex max-w-[85%] items-center gap-1.5 rounded-2xl border bg-card px-3 py-2 text-[13px] font-medium shadow-sheet">
          <FileText className="size-4 shrink-0 text-primary" />
          <span className="truncate">{file}</span>
        </p>
      )}
    </div>
  );
}

/** Answers the person can give in one tap, under what Plytos asked. */
export function Replies({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {children}
    </div>
  );
}

export function Reply({ className, quiet, ...props }: ComponentProps<"button"> & { quiet?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex min-h-9 items-center rounded-full border bg-card px-3.5 py-1.5 text-left text-[14px] font-medium text-primary shadow-sheet transition-colors outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50",
        quiet && "border-transparent bg-transparent text-muted-foreground shadow-none hover:bg-secondary",
        className,
      )}
      {...props}
    />
  );
}

/** Plytos is working on an answer. */
export function Thinking() {
  return (
    <div className="flex items-center gap-2" aria-hidden>
      <PlytosMark />
      <span className="flex h-9 items-center gap-1 rounded-[20px] rounded-tl-md bg-card px-4 shadow-sheet">
        {[0, 1, 2].map((i) => (
          <i
            key={i}
            className="size-1.5 animate-pulse rounded-full bg-muted-foreground/60 motion-reduce:animate-none"
            style={{ animationDelay: `${i * 160}ms` }}
          />
        ))}
      </span>
    </div>
  );
}

export function DayLabel({ children }: { children: ReactNode }) {
  return (
    <p className="py-1 text-center text-[12px] font-medium text-muted-foreground">{children}</p>
  );
}

/** Lines a question is about, quoted from the person's resume. */
export function Quote({ children, where }: { children: ReactNode; where?: string | null }) {
  return (
    <figure className="max-w-[92%] rounded-2xl border bg-card px-4 py-3 shadow-sheet sm:max-w-[85%]">
      {where && (
        <figcaption className="mb-1 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
          {where}
        </figcaption>
      )}
      <blockquote className="border-l-2 border-primary/40 pl-3 text-[14px] leading-[1.45] text-foreground/90">
        {children}
      </blockquote>
    </figure>
  );
}
