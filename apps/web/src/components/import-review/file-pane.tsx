"use client";

// The person's own file, beside what Plytos rebuilt from it. A PDF shows as
// pictures of its pages, each line lit up where it sits; anything else shows
// line by line, in the order the file has them. Tapping a line finds where it
// went.

import type { CSSProperties } from "react";

import { type Box, type FileLine, type ResumeFile, showsPages } from "@/lib/rebuilt";
import { cn } from "@/lib/utils";

export type FileMarks = {
  // Lines lit up as the partners of what's selected.
  lit: ReadonlySet<number>;
  // Lines Plytos couldn't place, marked so they're seen.
  loose: ReadonlySet<number>;
  // Lines on no card: headings, contact details, ones left off on purpose.
  quiet: ReadonlySet<number>;
  headings: ReadonlySet<number>;
};

export function lineId(block: number): string {
  return `file-line-${block}`;
}

// A box with a little room around the words, so the light doesn't clip them.
function around(box: Box): CSSProperties {
  const [left, top, right, bottom] = box;
  const x = 0.006;
  const y = 0.003;
  return {
    left: `${Math.max(0, left - x) * 100}%`,
    top: `${Math.max(0, top - y) * 100}%`,
    width: `${(Math.min(1, right + x) - Math.max(0, left - x)) * 100}%`,
    height: `${(Math.min(1, bottom + y) - Math.max(0, top - y)) * 100}%`,
  };
}

function Pages({
  importId,
  file,
  marks,
  onPick,
}: {
  importId: string;
  file: ResumeFile;
  marks: FileMarks;
  onPick: (block: number) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      {file.pages.map((page) => {
        const lines = file.lines.filter((l) => l.page === page.number);
        // A scanned page has no places for its lines; the whole page lights up.
        const scanLit = lines.some((l) => l.box === null && marks.lit.has(l.block));
        return (
          <figure
            key={page.number}
            className={cn(
              "relative overflow-hidden rounded-card border border-border bg-white shadow-sheet",
              scanLit && "ring-2 ring-primary",
            )}
            style={{ aspectRatio: `${page.width} / ${page.height}` }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- drawn for the person each time, never cached */}
            <img
              src={`/import/${encodeURIComponent(importId)}/pages/${page.number}`}
              alt={`Page ${page.number} of your resume`}
              loading={page.number === 1 ? "eager" : "lazy"}
              className="absolute inset-0 size-full select-none"
              draggable={false}
            />
            {lines.map((line) =>
              line.box ? (
                <button
                  key={line.block}
                  id={lineId(line.block)}
                  type="button"
                  aria-label={line.text}
                  aria-pressed={marks.lit.has(line.block)}
                  onClick={() => onPick(line.block)}
                  className={cn(
                    "absolute scroll-my-24 rounded-[2px] transition-colors hover:bg-primary/[0.08] focus-visible:outline-2 focus-visible:outline-primary",
                    marks.lit.has(line.block) && "bg-primary/15 outline-2 outline-primary hover:bg-primary/15",
                    marks.loose.has(line.block) &&
                      !marks.lit.has(line.block) &&
                      "border-b-2 border-dashed border-live",
                  )}
                  style={around(line.box)}
                />
              ) : (
                <span key={line.block} id={lineId(line.block)} className="sr-only">
                  {line.text}
                </span>
              ),
            )}
            <figcaption className="sr-only">Page {page.number}</figcaption>
          </figure>
        );
      })}
    </div>
  );
}

function Lines({
  file,
  marks,
  onPick,
}: {
  file: ResumeFile;
  marks: FileMarks;
  onPick: (block: number) => void;
}) {
  return (
    <div className="rounded-card border border-black/[0.06] bg-paper px-3 py-4 text-[13px] leading-[1.45] text-paper-ink shadow-sheet sm:px-5 sm:py-6">
      <ol className="flex flex-col">
        {file.lines.map((line: FileLine, i) => {
          const before = file.lines[i - 1]?.page ?? null;
          const newPage = line.page !== null && before !== null && line.page !== before;
          const heading = marks.headings.has(line.block);
          const lit = marks.lit.has(line.block);
          return (
            <li key={line.block} className={cn(heading && "mt-3 first:mt-0")}>
              {newPage && (
                <p
                  aria-hidden
                  className="my-3 flex items-center gap-2 text-[10.5px] font-medium tracking-[0.12em] text-paper-soft uppercase before:h-px before:flex-1 before:bg-paper-rule after:h-px after:flex-1 after:bg-paper-rule"
                >
                  Page {line.page}
                </p>
              )}
              <button
                id={lineId(line.block)}
                type="button"
                aria-pressed={lit}
                onClick={() => onPick(line.block)}
                className={cn(
                  "flex w-full scroll-my-24 items-start gap-2 rounded-[3px] px-1.5 py-[3px] text-left transition-colors hover:bg-paper-accent/[0.07] focus-visible:outline-2 focus-visible:outline-paper-accent",
                  heading && "text-[11px] font-semibold tracking-[0.12em] text-paper-soft uppercase",
                  line.bold && !heading && "font-semibold",
                  marks.quiet.has(line.block) && !heading && "text-paper-soft",
                  lit && "bg-paper-accent/[0.14] outline-2 outline-paper-accent/70 hover:bg-paper-accent/[0.14]",
                  marks.loose.has(line.block) && !lit && "underline decoration-live decoration-dashed decoration-2 underline-offset-4",
                )}
              >
                {line.bullet && (
                  <span aria-hidden className="mt-[0.58em] size-[4px] shrink-0 rounded-full bg-paper-ink/55" />
                )}
                <span className={cn("min-w-0 flex-1 [overflow-wrap:anywhere]", line.bullet && "pl-0.5")}>
                  {line.text}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function FilePane({
  importId,
  file,
  marks,
  onPick,
}: {
  importId: string;
  file: ResumeFile;
  marks: FileMarks;
  onPick: (block: number) => void;
}) {
  return showsPages(file) ? (
    <Pages importId={importId} file={file} marks={marks} onPick={onPick} />
  ) : (
    <Lines file={file} marks={marks} onPick={onPick} />
  );
}
