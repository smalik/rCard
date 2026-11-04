// Card types shared by the server and the browser. See docs/data-model.md.

// Cards nest into a career tree: an employment holds its positions, a
// position holds its accomplishments, and client work under an agency is an
// engagement in between. "role" is the flat kind from before the tree.
export type CardKind =
  | "employment"
  | "position"
  | "engagement"
  | "role"
  | "accomplishment"
  | "skill"
  | "project"
  | "education"
  | "credential"
  | "story";

export const KIND_LABELS: Record<CardKind, string> = {
  employment: "Employer",
  position: "Title",
  engagement: "Client work",
  role: "Role",
  accomplishment: "Accomplishment",
  skill: "Skill",
  project: "Project",
  education: "Education",
  credential: "Credential",
  story: "Story",
};

export const CARD_KINDS = Object.keys(KIND_LABELS) as CardKind[];

export type FactValue = string | number | string[];

export type Framing = {
  headline: string;
  body: string;
  shown_facts?: string[] | null;
};

// A main-line version: the card it sits under, the facts, and the default way
// to tell them.
export type CardContent = {
  parent?: string | null;
  facts: Record<string, FactValue>;
  framing: Framing;
};

export const HEADLINE_MAX = 200;
export const BODY_MAX = 5000;
