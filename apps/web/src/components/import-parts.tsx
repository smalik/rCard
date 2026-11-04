// Small pieces the import screens share. None hold state, so they render on
// the server or inside a client screen alike.

import {
  faArrowRight,
  faBookOpen,
  faBriefcase,
  faBuilding,
  faCertificate,
  faCheck,
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
  contentFor,
  dateSpan,
  type ImportFileInfo,
  type OutlineNode,
  outline,
  plural,
  type Proposal,
  type Review,
} from "../lib/imports";
import { kindLabel, kindStyle, SketchCard } from "./hybrid";
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

// Three cards fanned out: a role, a result and a skill.
export function FannedCards({ size = "large" }: { size?: "large" | "small" }) {
  const lines = size === "large" ? [100, 70, 45] : [];
  return (
    <div className={`fan fan-${size}`} aria-hidden="true">
      <SketchCard
        kind="role"
        label={size === "large" ? "Role" : ""}
        lines={lines}
        className="fan-1"
      />
      <SketchCard
        kind="result"
        label={size === "large" ? "Result" : ""}
        lines={lines}
        className="fan-2"
        badge={
          size === "large" ? (
            <span className="sketch-check">
              <Icon icon={faCheck} size={8} />
            </span>
          ) : undefined
        }
      />
      <SketchCard
        kind="skill"
        label={size === "large" ? "Skill" : ""}
        lines={lines}
        className="fan-3"
      />
    </div>
  );
}

// The career as the import read it: each employer and its tenure, the titles
// held there with their dates, and how many results sit under each.
export function CareerOutline({ review }: { review: Review }) {
  const jobs = outline(review).filter(
    (n) => n.card.kind === "employment" || n.card.kind === "role",
  );
  if (jobs.length === 0) return null;
  const content = (card: Proposal) => contentFor(card, review.progress);
  const results = (node: OutlineNode): number =>
    node.children.reduce(
      (n, child) => n + (child.card.kind === "accomplishment" ? 1 : 0) + results(child),
      0,
    );
  const line = (node: OutlineNode, frames: OutlineNode[]) => {
    const own = results(node) - frames.reduce((n, f) => n + results(f), 0);
    const facts = content(node.card).facts;
    return (
      <>
        <span className="outline-name">{content(node.card).framing.headline}</span>
        <span className="outline-meta">
          {[
            node.card.kind === "engagement" ? "Client" : null,
            dateSpan(facts),
            own > 0 ? plural(own, "result") : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </>
    );
  };
  const frames = (node: OutlineNode) =>
    node.children.filter((c) => c.card.kind === "position" || c.card.kind === "engagement");
  const branch = (node: OutlineNode) => (
    <li key={node.card.ref}>
      {line(node, frames(node))}
      {frames(node).length > 0 && <ul>{frames(node).map(branch)}</ul>}
    </li>
  );
  return (
    <ol className="career-outline">
      {jobs.map((job) => (
        <li key={job.card.ref} className="outline-job">
          {line(job, frames(job))}
          {frames(job).length > 0 && <ul>{frames(job).map(branch)}</ul>}
        </li>
      ))}
    </ol>
  );
}
