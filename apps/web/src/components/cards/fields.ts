import type { Field } from "@/components/cards/card-back";

const START: Field = { key: "start", label: "Started", placeholder: "2021-06", half: true };
const END: Field = { key: "end", label: "Ended", placeholder: "present", half: true };
const DATE: Field = { key: "date", label: "When", placeholder: "2023-04", half: true };

/** The facts each card's back lets the person edit, by what the card is for. */
export const FIELDS = {
  employment: [
    { key: "employer", label: "Employer" },
    { key: "former_employer", label: "Earlier name", placeholder: "Before a rename or acquisition" },
    { key: "location", label: "Where", placeholder: "Dallas, TX", half: true },
    { key: "employment_type", label: "Type", placeholder: "Full-time, contract", half: true },
    START,
    END,
  ],
  position: [
    { key: "title", label: "Official title" },
    { key: "plain_title", label: "Plain-language title", placeholder: "Shown beside it, never instead" },
    { key: "team", label: "Team", half: true },
    { key: "scope", label: "Scope", placeholder: "Team of 6, $2M budget", half: true },
    START,
    END,
  ],
  engagement: [
    { key: "client", label: "Client" },
    { key: "title", label: "Title" },
    START,
    END,
  ],
  accomplishment: [
    { key: "figures", label: "Figures", placeholder: "40%, $1.2M, 12 reports", list: true },
    { key: "skills", label: "Skills shown", placeholder: "SQL, Oracle", list: true },
    DATE,
    { key: "scope", label: "Scope", half: true },
  ],
  award: [
    { key: "award", label: "Award" },
    { key: "issuer", label: "Given by", half: true },
    DATE,
  ],
  education: [
    { key: "institution", label: "School" },
    { key: "degree", label: "Degree", half: true },
    { key: "field", label: "Field", half: true },
    DATE,
  ],
  credential: [
    { key: "name", label: "Certification" },
    { key: "issuer", label: "Issued by", half: true },
    DATE,
    { key: "credential_id", label: "Credential ID", half: true },
  ],
  project: [
    { key: "role", label: "Your role", half: true },
    DATE,
    { key: "figures", label: "Figures", list: true },
  ],
  activity: [
    { key: "name", label: "What" },
    { key: "role", label: "Your part", placeholder: "Speaker, author, board member", half: true },
    DATE,
  ],
  skill: [
    { key: "category", label: "Group" },
    { key: "skills", label: "Skills", placeholder: "Python, SQL, dbt", list: true },
  ],
} satisfies Record<string, Field[]>;
