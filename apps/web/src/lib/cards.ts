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
  | "activity"
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
  activity: "Activity",
  story: "Story",
};

export const CARD_KINDS = Object.keys(KIND_LABELS) as CardKind[];

export type FactValue = string | number | string[];

// The parts of a card's wording Plytos wrote itself, such as a job's headline
// or a title's story summed up from its accomplishments.
export type WrittenPart = "headline" | "body";

export type Framing = {
  headline: string;
  body: string;
  shown_facts?: string[] | null;
  // The parts Plytos wrote and nobody changed since. The API keeps this
  // honest: editing a part makes it the person's own.
  plytos_wrote?: WrittenPart[];
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
