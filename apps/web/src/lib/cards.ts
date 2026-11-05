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

// A number as a resume line writes one: "$1.2M", "40%", "1,200", "3x".
const NUMBER = /\$?\d[\d,]*(?:\.\d+)?(?:\s?%|[kKmMbBx]\b)?/g;
// "24/7" says always on; it isn't two numbers.
const ROUND_THE_CLOCK = /\b24\s*[/x]\s*7\b/gi;
// A capitalised word right before a number: "Dynamics 365", "Windows 11".
const NAMED_BEFORE = /\S\s+[A-Z][A-Za-z]*\s$/;

/** The numbers an accomplishment's words cite, leaving out ones that are part
 * of a name or code ("Q3", "Windows 11"), years and "24/7". */
export function numbersIn(text: string): string[] {
  const plain = text.replace(ROUND_THE_CLOCK, " ");
  const found: string[] = [];
  for (const m of plain.matchAll(NUMBER)) {
    const token = m[0].trim();
    const before = plain.slice(0, m.index);
    if (/[A-Za-z]$/.test(before)) continue;
    if (/^\d+$/.test(token) && (NAMED_BEFORE.test(before) || /^(19|20)\d\d$/.test(token))) continue;
    found.push(token);
  }
  return [...new Set(found)];
}
