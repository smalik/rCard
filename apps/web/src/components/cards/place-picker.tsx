"use client";

import { CornerDownRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { buildLibrary, fact, headline, type LibraryCard } from "@/lib/library";

/** Where an accomplishment can go: one place per title at each employer, and
 * the employer itself for work that spans its titles. */
export type Place = { card: string; employment: string; label: string };

export function placesFrom(cards: readonly LibraryCard[]): { employer: string; places: Place[] }[] {
  return buildLibrary(cards)
    .experience.filter((job) => job.card.kind === "employment")
    .map((job) => {
      const employer = fact(job.card, "employer") || headline(job.card);
      return {
        employer,
        places: [
          ...job.positions.map((p) => ({
            card: p.card.id,
            employment: job.card.id,
            label: fact(p.card, "title") || headline(p.card),
          })),
          { card: job.card.id, employment: job.card.id, label: "Across titles" },
        ],
      };
    });
}

/** "Place under…": a menu of the person's jobs and their titles. */
export function PlacePicker({
  cards,
  line,
  busy,
  onPlace,
  size = "sm",
}: {
  cards: readonly LibraryCard[];
  // The line being placed, for the button's accessible name.
  line: string;
  busy?: boolean;
  onPlace: (place: Place) => void;
  size?: "sm" | "xs";
}) {
  const jobs = placesFrom(cards);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={size === "xs" ? "h-7 px-2.5 text-[12.5px]" : undefined}
          disabled={busy || jobs.length === 0}
          aria-label={`Place under a job: ${line}`}
        >
          <CornerDownRight /> Place under…
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[60vh] w-64 overflow-y-auto">
        {jobs.map((job, i) => (
          <div key={job.places.at(-1)!.employment}>
            {i > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="truncate">{job.employer}</DropdownMenuLabel>
            {job.places.map((place) => (
              <DropdownMenuItem key={place.card} onSelect={() => onPlace(place)}>
                <span className="truncate">{place.label}</span>
              </DropdownMenuItem>
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
