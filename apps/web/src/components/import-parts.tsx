// Small pieces the import screens share. None hold state, so they render on
// the server or inside a client screen alike.

import {
  faArrowRight,
  faBookOpen,
  faBriefcase,
  faBuilding,
  faCertificate,
  faFileLines,
  faGraduationCap,
  faHandshake,
  faLayerGroup,
  faLock,
  faPeopleGroup,
  faTrophy,
  faWandMagicSparkles,
  type IconDefinition,
} from "@fortawesome/free-solid-svg-icons";

import type { CardContent, CardKind, FactValue } from "../lib/cards";
import {
  cardPlace,
  type ImportFileInfo,
  plural,
  type Proposal,
} from "../lib/imports";
import { kindLabel, kindStyle } from "./hybrid";
import { Icon } from "./icon";

export function kindIcon(kind: CardKind): IconDefinition {
  return {
    employment: faBuilding,
    position: faBriefcase,
    engagement: faHandshake,
    role: faBriefcase,
    accomplishment: faTrophy,
    project: faLayerGroup,
    skill: faWandMagicSparkles,
    education: faGraduationCap,
    credential: faCertificate,
    activity: faPeopleGroup,
    story: faBookOpen,
  }[kind];
}

export function KindPill({ kind, content }: { kind: CardKind; content: CardContent }) {
  return (
    <span className={`kind-pill kind-${kindStyle(kind)}`}>
      <Icon icon={kindIcon(kind)} size={11} />
      {kindLabel(kind, content.facts)}
    </span>
  );
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileDetail(file: Pick<ImportFileInfo, "pages" | "size">): string {
  return `${file.pages ? plural(file.pages, "page") : formatSize(file.size)} · kept private`;
}

// The person's own file, with a way to open it again.
export function FileCard({
  name,
  detail,
  href,
}: {
  name: string;
  detail: string;
  href: string | null;
}) {
  return (
    <div className="surface file-card">
      <div className="file-card-main">
        <span className="icon-tile small">
          <Icon icon={faFileLines} size={18} />
        </span>
        <div className="file-card-text">
          <p className="file-name">{name}</p>
          <p className="file-meta">
            <Icon icon={faLock} size={10} />
            {detail}
          </p>
        </div>
      </div>
      <div className="file-card-foot">
        <span className="label small medium">Your original stays untouched</span>
        {href ? (
          <a className="text-button teal small" href={href} target="_blank" rel="noopener">
            View original
            <Icon icon={faArrowRight} size={12} />
          </a>
        ) : (
          <span className="label small medium">Saving…</span>
        )}
      </div>
    </div>
  );
}

export type Segment = "done" | "current" | "open" | "later" | "pending";

// A row of short bars, one per item: settled, current, set aside, or to do.
export function Segments({ states, label }: { states: Segment[]; label?: string }) {
  return (
    <div
      className="segments"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {states.map((state, i) => (
        <span key={i} data-state={state} />
      ))}
    </div>
  );
}

// A small found card: its kind, its headline, and where it sits.
export function MiniCard({
  card,
  content,
  above,
}: {
  card: Proposal;
  content: CardContent;
  above?: Record<string, FactValue>;
}) {
  const style = kindStyle(card.kind);
  const place = cardPlace(content, above);
  return (
    <div className={`mini-card kind-${style}`}>
      <span className="mini-card-kind">
        <Icon icon={kindIcon(card.kind)} size={11} />
        {kindLabel(card.kind, content.facts)}
      </span>
      <p className={kindStyle(card.kind) === "role" ? "mini-card-title large" : "mini-card-title"}>
        {content.framing.headline}
      </p>
      {place && <p className="mini-card-meta">{place}</p>}
    </div>
  );
}
