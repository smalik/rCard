"use client";

import { Check, Globe, Mail, MapPin, Phone } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import { useCardActions } from "@/components/cards/actions";
import { AttachmentChips } from "@/components/cards/attachments";
import { CardBack } from "@/components/cards/card-back";
import { FIELDS } from "@/components/cards/fields";
import { type Purpose, StrengthCard } from "@/components/cards/strength-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { type CardKind, KIND_LABELS } from "@/lib/cards";
import { cardDates, fact, headline, type LibraryCard, listFact } from "@/lib/library";
import type { ResumeHeader } from "@/lib/resumes";

function live(card: LibraryCard) {
  return {
    version: card.version,
    updatedAt: card.updated_at,
    author: card.version_author,
    variantsBehind: card.variants_behind,
  };
}

/** The shared shape of the context cards: a name, a line under it, a date,
 * the story, and what's attached. */
function FactCard({
  card,
  purpose,
  name,
  sub,
  fields,
  extra,
  title,
  className,
}: {
  card: LibraryCard;
  purpose: Purpose;
  name: string;
  sub?: string;
  fields: (typeof FIELDS)[keyof typeof FIELDS];
  extra?: ReactNode;
  // Overrides the purpose's label at the top of the card.
  title?: string;
  className?: string;
}) {
  const { now, fresh } = useCardActions();
  const dates = cardDates(card);
  const body = card.content?.framing.body ?? "";
  return (
    <StrengthCard
      purpose={purpose}
      title={title}
      label={`${title ?? purpose}: ${name}`}
      live={live(card)}
      now={now}
      fresh={fresh.has(card.id)}
      className={className}
      front={
        <div className="flex flex-col gap-2.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-[18px] leading-snug font-semibold tracking-[-0.015em] text-balance">
                {name}
              </h3>
              {sub && <p className="text-[14px] text-muted-foreground">{sub}</p>}
            </div>
            {dates && (
              <span className="shrink-0 pt-0.5 text-[13px] text-muted-foreground tabular-nums">
                {dates}
              </span>
            )}
          </div>
          {body && (
            <p className="text-[14.5px] leading-relaxed whitespace-pre-line text-foreground/80">
              {body}
            </p>
          )}
          {extra}
          <AttachmentChips attachments={card.content?.attachments ?? []} />
        </div>
      }
      back={() => (
        <CardBack
          card={card}
          fields={fields}
          headlineLabel="As it reads on a resume"
          story={{ label: "More about it", placeholder: "What it was, and why it matters." }}
        />
      )}
    />
  );
}

export function EducationCard({ card, className }: { card: LibraryCard; className?: string }) {
  const school = fact(card, "institution");
  const degree = [fact(card, "degree"), fact(card, "field")].filter(Boolean).join(", ");
  return (
    <FactCard
      card={card}
      purpose="education"
      name={school || headline(card)}
      sub={school ? degree || undefined : undefined}
      fields={FIELDS.education}
      className={className}
    />
  );
}

export function AwardCard({ card, className }: { card: LibraryCard; className?: string }) {
  const issuer = fact(card, "issuer");
  return (
    <FactCard
      card={card}
      purpose="award"
      name={fact(card, "award") || headline(card)}
      sub={issuer ? `Given by ${issuer}` : undefined}
      fields={FIELDS.award}
      className={className}
    />
  );
}

export function CredentialCard({ card, className }: { card: LibraryCard; className?: string }) {
  const issuer = fact(card, "issuer");
  return (
    <FactCard
      card={card}
      purpose="credential"
      name={fact(card, "name") || headline(card)}
      sub={issuer || undefined}
      fields={FIELDS.credential}
      className={className}
    />
  );
}

export function ProjectCard({ card, className }: { card: LibraryCard; className?: string }) {
  const role = fact(card, "role");
  return (
    <FactCard
      card={card}
      purpose="project"
      name={headline(card)}
      sub={role || undefined}
      fields={FIELDS.project}
      className={className}
    />
  );
}

export function ActivityCard({ card, className }: { card: LibraryCard; className?: string }) {
  const role = fact(card, "role");
  return (
    <FactCard
      card={card}
      purpose="activity"
      name={fact(card, "name") || headline(card)}
      sub={role || undefined}
      fields={FIELDS.activity}
      className={className}
    />
  );
}

const OTHER_FIELDS: Partial<Record<CardKind, (typeof FIELDS)[keyof typeof FIELDS]>> = {
  employment: FIELDS.employment,
  role: FIELDS.employment,
  position: FIELDS.position,
  engagement: FIELDS.engagement,
  accomplishment: FIELDS.accomplishment,
  project: FIELDS.project,
};

/** A card the other sections don't show, such as the summary from a resume,
 * a title whose employer was left out, or work under a project. */
export function OtherCard({ card, className }: { card: LibraryCard; className?: string }) {
  const summary = card.kind === "story" && fact(card, "use") === "summary";
  return (
    <FactCard
      card={card}
      purpose="highlight"
      title={summary ? "Summary" : KIND_LABELS[card.kind]}
      name={headline(card)}
      fields={OTHER_FIELDS[card.kind] ?? []}
      className={className}
    />
  );
}

/** A group of skills, each with how many accomplishments show it: skills
 * are strongest when the work backs them. */
export function SkillsCard({
  card,
  shownIn,
  className,
}: {
  card: LibraryCard;
  shownIn: (skill: string) => number;
  className?: string;
}) {
  const skills = listFact(card, "skills");
  const category = fact(card, "category");
  return (
    <FactCard
      card={card}
      purpose="skill"
      name={category && category !== "Skills" ? category : "Skills"}
      fields={FIELDS.skill}
      className={className}
      extra={
        skills.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Skills">
            {skills.map((skill) => {
              const n = shownIn(skill);
              return (
                <li
                  key={skill}
                  className="inline-flex items-center gap-1.5 rounded-full border bg-card py-1 pr-1.5 pl-2.5 text-[13px] font-medium shadow-sheet"
                >
                  {skill}
                  <span
                    className={
                      n > 0
                        ? "rounded-full bg-accent px-1.5 text-[11px] text-accent-foreground tabular-nums"
                        : "rounded-full bg-muted px-1.5 text-[11px] text-muted-foreground"
                    }
                    title={n > 0 ? `Shown in ${n} accomplishments` : "Not shown in any accomplishment yet"}
                  >
                    {n > 0 ? n : "–"}
                    <span className="sr-only">
                      {n > 0 ? ` accomplishments show it` : " no accomplishment shows it yet"}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )
      }
    />
  );
}

const CONTACT_ROWS: { key: keyof ResumeHeader; label: string; icon: typeof Mail }[] = [
  { key: "email", label: "Email", icon: Mail },
  { key: "phone", label: "Phone", icon: Phone },
  { key: "location", label: "Where", icon: MapPin },
];

/** Who the resume is from: the name, a line under it, and how to reach them.
 * It comes from a resume's top, and saving makes that resume's next version. */
export function ContactCard({
  header,
  from,
  onSave,
  className,
}: {
  header: ResumeHeader;
  // The resume it comes from, such as "As written".
  from: string;
  onSave: (next: ResumeHeader) => Promise<void>;
  className?: string;
}) {
  const { now } = useCardActions();
  const links = header.links.filter(Boolean);
  return (
    <StrengthCard
      purpose="contact"
      label={`Contact: ${header.name || "you"}`}
      now={now}
      className={className}
      front={
        <div className="flex flex-col gap-3">
          <div>
            <h3 className="text-[23px] leading-tight font-semibold tracking-[-0.02em]">
              {header.name || "Your name"}
            </h3>
            {header.headline && (
              <p className="text-[14.5px] text-muted-foreground">{header.headline}</p>
            )}
          </div>
          <ul className="flex flex-col gap-1.5">
            {CONTACT_ROWS.filter((r) => header[r.key]).map(({ key, label, icon: Icon }) => (
              <li key={key} className="flex items-center gap-2.5 text-[14.5px]">
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="sr-only">{label}: </span>
                <span className="truncate">{String(header[key])}</span>
              </li>
            ))}
            {links.map((link) => (
              <li key={link} className="flex items-center gap-2.5 text-[14.5px]">
                <Globe className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="truncate">{link.replace(/^https?:\/\/(www\.)?/, "")}</span>
              </li>
            ))}
          </ul>
          <p className="text-[12px] text-muted-foreground">From your “{from}” resume</p>
        </div>
      }
      back={() => <ContactBack header={header} onSave={onSave} />}
    />
  );
}

function ContactBack({
  header,
  onSave,
}: {
  header: ResumeHeader;
  onSave: (next: ResumeHeader) => Promise<void>;
}) {
  const [draft, setDraft] = useState({ ...header, links: header.links.join("\n") });
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);
  const next: ResumeHeader = {
    ...draft,
    links: draft.links
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(0, 5),
  };
  const dirty = JSON.stringify(next) !== JSON.stringify(header);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState("saving");
    setError(null);
    try {
      await onSave(next);
      setState("saved");
    } catch (e) {
      setState("idle");
      setError(e instanceof Error ? e.message : "That didn't save. Try again.");
    }
  }

  const field = (key: Exclude<keyof ResumeHeader, "links" | "summary">, label: string, half = false) => (
    <div className={half ? "col-span-1 grid gap-1.5" : "col-span-2 grid gap-1.5"}>
      <Label htmlFor={`contact-${key}`}>{label}</Label>
      <Input
        id={`contact-${key}`}
        value={draft[key]}
        onChange={(e) => {
          setState("idle");
          setDraft({ ...draft, [key]: e.target.value });
        }}
      />
    </div>
  );

  return (
    <form className="flex flex-col gap-4" onSubmit={submit}>
      <div className="grid grid-cols-2 gap-3">
        {field("name", "Name")}
        {field("headline", "Line under your name")}
        {field("email", "Email", true)}
        {field("phone", "Phone", true)}
        {field("location", "Where")}
        <div className="col-span-2 grid gap-1.5">
          <Label htmlFor="contact-links">Links, one per line</Label>
          <Textarea
            id="contact-links"
            value={draft.links}
            className="min-h-16"
            onChange={(e) => {
              setState("idle");
              setDraft({ ...draft, links: e.target.value });
            }}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!dirty || state === "saving"}>
          {state === "saving" ? "Saving…" : "Save to the resume"}
        </Button>
        {state === "saved" && !dirty && (
          <span role="status" className="flex items-center gap-1 text-[13px] text-primary">
            <Check className="size-4" /> Saved
          </span>
        )}
        {error && (
          <span role="alert" className="text-[13px] text-destructive">
            {error}
          </span>
        )}
      </div>
    </form>
  );
}
