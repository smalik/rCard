"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  CHECK_IN_CHOICES,
  type CheckIns,
  type CheckInSlot,
  checkInTimes,
  timeLabel,
  USUAL_CHECK_IN,
  WEEKDAYS,
  WEEKS,
} from "@/lib/talk";

import { PlytosSays, Replies, Reply } from "./bubbles";

// Saves a check-in plan; returns what went wrong, or null.
export type Plan = (slot: CheckInSlot, state?: "on" | "off") => Promise<string | null>;

function Problem({ children }: { children: string | null }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-[13px] text-destructive">
      {children}
    </p>
  );
}

/** Asked once, after the person's first exchange: whether Plytos should check
 * in once a month, and when. */
export function CheckInOffer({ onPlan }: { onPlan: Plan }) {
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose(slot: CheckInSlot, state: "on" | "off" = "on") {
    setBusy(true);
    setError(null);
    const problem = await onPlan(slot, state);
    setBusy(false);
    setError(problem);
  }

  return (
    <PlytosSays
      attached={
        <>
          {picking ? (
            <div className="w-full max-w-md rounded-card border bg-card p-4 shadow-card">
              <CheckInPicker
                initial={USUAL_CHECK_IN}
                busy={busy}
                onSave={(slot) => void choose(slot)}
                onCancel={() => setPicking(false)}
              />
            </div>
          ) : (
            <Replies label="When to check in">
              {CHECK_IN_CHOICES.map((choice) => (
                <Reply key={choice.label} disabled={busy} onClick={() => void choose(choice.slot)}>
                  {choice.label}
                </Reply>
              ))}
              <Reply disabled={busy} onClick={() => setPicking(true)}>
                Another day
              </Reply>
              <Reply quiet disabled={busy} onClick={() => void choose(USUAL_CHECK_IN, "off")}>
                Not now
              </Reply>
            </Replies>
          )}
          <Problem>{error}</Problem>
        </>
      }
    >
      Want me to check in once a month? I&apos;ll ask one quick question about how the month went,
      so the good parts don&apos;t slip away.
    </PlytosSays>
  );
}

/** Changing or turning off check-ins, from the line under the header. */
export function CheckInSettings({
  checkIns,
  onPlan,
  onClose,
}: {
  checkIns: CheckIns;
  onPlan: Plan;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = checkIns.plan ?? { ...USUAL_CHECK_IN, state: "off" as const };

  async function save(slot: CheckInSlot, state: "on" | "off") {
    setBusy(true);
    setError(null);
    const problem = await onPlan(slot, state);
    setBusy(false);
    setError(problem);
  }

  return (
    <section
      aria-label="Check-ins"
      className="mt-3 flex flex-col gap-3 rounded-card border bg-card p-4 shadow-card"
    >
      <p className="text-[14px] font-medium">Once a month, I&apos;ll ask one quick question. When suits you?</p>
      <CheckInPicker
        initial={current}
        busy={busy}
        onSave={(slot) => void save(slot, "on")}
        onCancel={onClose}
        onTurnOff={current.state === "on" ? () => void save(current, "off") : undefined}
      />
      <Problem>{error}</Problem>
    </section>
  );
}

const SELECT =
  "h-10 w-full rounded-xl border border-input bg-background px-3 text-[15px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40";

function CheckInPicker({
  initial,
  busy,
  onSave,
  onCancel,
  onTurnOff,
}: {
  initial: CheckInSlot;
  busy: boolean;
  onSave: (slot: CheckInSlot) => void;
  onCancel: () => void;
  onTurnOff?: () => void;
}) {
  const [week, setWeek] = useState(initial.week);
  const [weekday, setWeekday] = useState(initial.weekday);
  const [time, setTime] = useState(initial.time);
  const which = WEEKS.find((w) => w.week === week)?.label.toLowerCase() ?? "";
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    box.current?.scrollIntoView({ block: "nearest" });
  }, []);

  return (
    <div className="flex flex-col gap-3" ref={box}>
      <div className="grid grid-cols-3 gap-2">
        <label className="flex flex-col gap-1 text-[12px] font-medium text-muted-foreground">
          Week
          <select
            className={SELECT}
            value={week}
            onChange={(e) => setWeek(Number(e.target.value) as typeof week)}
          >
            {WEEKS.map((w) => (
              <option key={w.week} value={w.week}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-muted-foreground">
          Day
          <select className={SELECT} value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
            {WEEKDAYS.map((name, i) => (
              <option key={name} value={i + 1}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-muted-foreground">
          Time
          <select className={SELECT} value={time} onChange={(e) => setTime(e.target.value)}>
            {checkInTimes(initial.time).map((t) => (
              <option key={t} value={t}>
                {timeLabel(t)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-[13px] text-muted-foreground">
        The {which} {WEEKDAYS[weekday - 1]} of each month at {timeLabel(time)}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={() => onSave({ week, weekday, time })}>
          Check in then
        </Button>
        {onTurnOff && (
          <Button variant="outline" disabled={busy} onClick={onTurnOff}>
            Turn off
          </Button>
        )}
        <Button variant="ghost" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
