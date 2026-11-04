// Pieces every Hybrid screen shares: the header, the step bar, and the small
// card shapes used in illustrations. None of them hold state, so they render
// on the server or inside a client screen alike.

import { faArrowLeft, faCheck, faLock } from "@fortawesome/free-solid-svg-icons";
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import type { CardKind } from "../lib/cards";
import { Icon } from "./icon";

type Back = { href: string; label?: string } | { onClick: () => void; label?: string };

export function AppHeader({ back }: { back?: Back }) {
  const label = back?.label ?? "Back";
  return (
    <div className="app-header">
      <div className="app-header-left">
        {back && "href" in back && (
          <Link className="round-button" href={back.href} aria-label={label}>
            <Icon icon={faArrowLeft} size={14} />
          </Link>
        )}
        {back && "onClick" in back && (
          <button className="round-button" type="button" onClick={back.onClick} aria-label={label}>
            <Icon icon={faArrowLeft} size={14} />
          </button>
        )}
        <Link className="logo" href="/cards" aria-label="Plytos, your cards">
          <span className="logo-mark" aria-hidden="true">
            P
          </span>
          Plytos
        </Link>
      </div>
      <span className="private-pill">
        <Icon icon={faLock} size={10} />
        Only you
      </span>
    </div>
  );
}

const STEPS = ["Bring in", "Check", "Approve", "See strengths"];

// The four steps of bringing a resume in. `progress` fills the current step's
// bar part of the way, from 0 to 1.
export function StepBar({ current, progress = 1 }: { current: 1 | 2 | 3 | 4; progress?: number }) {
  return (
    <ol className="steps" aria-label="Import steps">
      {STEPS.map((name, i) => {
        const number = i + 1;
        const state = number < current ? "done" : number === current ? "current" : "pending";
        const fill = state === "current" ? Math.max(0.08, Math.min(1, progress)) : 0;
        return (
          <li
            key={name}
            className="step"
            data-state={state}
            aria-current={state === "current" ? "step" : undefined}
          >
            <span className="step-track">
              {state === "current" && (
                <span className="step-fill" style={{ width: `${fill * 100}%` }} />
              )}
            </span>
            <span className="step-name">
              {state === "done" && (
                <span className="check-dot">
                  <Icon icon={faCheck} size={7} />
                </span>
              )}
              <span>
                {number} {name}
                {state === "done" && <span className="visually-hidden">, done</span>}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function PageHead({
  back,
  step,
  progress,
}: {
  back?: Back;
  step: 1 | 2 | 3 | 4;
  progress?: number;
}) {
  return (
    <header className="page-head">
      <AppHeader back={back} />
      <StepBar current={step} progress={progress} />
    </header>
  );
}

// Plytos shows four kinds of card, each with its own color: roles, results,
// skills, and the people and places around them.
export type KindStyle = "role" | "result" | "skill" | "people";

export function kindStyle(kind: CardKind): KindStyle {
  if (kind === "role") return "role";
  if (kind === "accomplishment" || kind === "project") return "result";
  if (kind === "skill") return "skill";
  return "people";
}

export function kindLabel(kind: CardKind, facts?: Record<string, unknown>): string {
  if (kind === "accomplishment") return facts?.award ? "Award" : "Result";
  if (kind === "story") return facts?.use === "summary" ? "Summary" : "Story";
  return {
    role: "Role",
    project: "Project",
    skill: "Skill",
    education: "Education",
    credential: "Credential",
  }[kind];
}

// A placeholder card: a colored bar, a label and grey lines where words go.
export function SketchCard({
  kind,
  label,
  lines = [100, 58, 38],
  badge,
  className,
  style,
}: {
  kind: KindStyle;
  label: string;
  lines?: number[];
  badge?: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`sketch-card kind-${kind} ${className ?? ""}`} style={style} aria-hidden="true">
      <div className="sketch-card-top">
        <span>{label}</span>
        {badge}
      </div>
      {lines.map((width, i) => (
        <span key={i} className="sketch-line" style={{ width: `${width}%` }} />
      ))}
    </div>
  );
}
