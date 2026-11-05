// Comparing two readings of a resume: two versions, or the saved resume and
// the changes being made to it. Works on pages as they read (RenderedResume),
// so it shows what a reader would see change: lines brought in or left out,
// lines worded differently, jobs and lines moved, and changes at the top.

import {
  lineParts,
  type RenderedEntry,
  type RenderedItem,
  type RenderedResume,
  type RenderedRole,
  type ResumeHeader,
} from "./resumes";

export type Presence = "same" | "added" | "removed";

export type DiffLine = {
  card: string;
  kind: string;
  text: string;
  detail: string;
  date: string;
  wording: RenderedItem["wording"];
  presence: Presence;
  // The text it read before, when only the wording changed.
  was: string | null;
  moved: boolean;
};

export type DiffRole = {
  key: string;
  title: string;
  dates: string;
  presence: Presence;
  lines: DiffLine[];
};

export type DiffEntry = {
  card: string;
  employer: string;
  location: string;
  dates: string;
  presence: Presence;
  moved: boolean;
  // Set when earlier titles were folded into one line, or unfolded.
  fold: "folded" | "unfolded" | null;
  earlier_titles: string[];
  roles: DiffRole[];
};

export type DiffSection = { kind: string; label: string; presence: Presence; lines: DiffLine[] };

export type HeaderChange = { field: keyof ResumeHeader; label: string; was: string; now: string };

export type DiffCounts = {
  added: number;
  removed: number;
  reworded: number;
  moved: number;
  jobsAdded: number;
  jobsRemoved: number;
  folds: number;
  header: number;
};

export type ResumeDiff = {
  header: HeaderChange[];
  entries: DiffEntry[];
  sections: DiffSection[];
  counts: DiffCounts;
};

// -- ordering ------------------------------------------------------------------

type Merged<T> = { item: T; presence: Presence; before: T | null };

/** The items of `after` in order, with the items only `before` had placed
 * after the item they followed there. */
export function mergeOrdered<T>(before: T[], after: T[], key: (item: T) => string): Merged<T>[] {
  const beforeByKey = new Map(before.map((b) => [key(b), b]));
  const afterKeys = new Set(after.map(key));
  const out: Merged<T>[] = after.map((a) => ({
    item: a,
    presence: beforeByKey.has(key(a)) ? "same" : "added",
    before: beforeByKey.get(key(a)) ?? null,
  }));
  let cursor = -1;
  for (const b of before) {
    const k = key(b);
    if (afterKeys.has(k)) {
      cursor = out.findIndex((m) => m.presence !== "removed" && key(m.item) === k);
    } else {
      out.splice(cursor + 1, 0, { item: b, presence: "removed", before: b });
      cursor += 1;
    }
  }
  return out;
}

/** The keys that kept their order: the longest run common to both lists.
 * Anything else that's in both moved. */
export function steady(before: string[], after: string[]): Set<string> {
  const common = new Set(after.filter((k) => before.includes(k)));
  const a = before.filter((k) => common.has(k));
  const b = after.filter((k) => common.has(k));
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i]![j] =
        a[i] === b[j] ? table[i + 1]![j + 1]! + 1 : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }
  const kept = new Set<string>();
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      kept.add(a[i]!);
      i++;
      j++;
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      i++;
    } else {
      j++;
    }
  }
  return kept;
}

// -- lines ---------------------------------------------------------------------

function shown(item: RenderedItem): string {
  return lineParts(item).text;
}

function line(item: RenderedItem, presence: Presence, was: RenderedItem | null): DiffLine {
  const now = shown(item);
  const before = was ? shown(was) : null;
  return {
    card: item.card,
    kind: item.kind,
    text: now,
    detail: lineParts(item).detail,
    date: item.date,
    wording: item.wording,
    presence,
    was: presence === "same" && before !== null && before !== now ? before : null,
    moved: false,
  };
}

/** Lines in one place (a title, a section), against the lines there before.
 * `elsewhere` holds cards still shown in the same job or section, which moved
 * rather than came or went. */
function diffLines(
  before: RenderedItem[],
  after: RenderedItem[],
  elsewhereBefore: Set<string> = new Set(),
  elsewhereAfter: Set<string> = new Set(),
): DiffLine[] {
  const merged = mergeOrdered(before, after, (i) => i.card).filter(
    (m) => !(m.presence === "removed" && elsewhereAfter.has(m.item.card)),
  );
  const kept = steady(
    before.map((i) => i.card),
    after.map((i) => i.card),
  );
  return merged.map((m) => {
    if (m.presence === "added" && elsewhereBefore.has(m.item.card)) {
      return { ...line(m.item, "same", null), moved: true };
    }
    const out = line(m.item, m.presence, m.before);
    out.moved = m.presence === "same" && !kept.has(m.item.card);
    return out;
  });
}

// -- jobs ------------------------------------------------------------------------

function roleKey(role: RenderedRole): string {
  return role.card ?? "employment";
}

function cardsIn(entry: RenderedEntry | null): Set<string> {
  return new Set(entry?.roles.flatMap((r) => r.items.map((i) => i.card)) ?? []);
}

function diffEntry(
  before: RenderedEntry | null,
  after: RenderedEntry,
  presence: Presence,
  moved: boolean,
): DiffEntry {
  const base = {
    card: after.card,
    employer: after.employer,
    location: after.location,
    dates: after.dates,
    presence,
    moved,
    earlier_titles: after.earlier_titles,
  };
  if (presence !== "same" || before === null) {
    // A job brought in or left out: every line comes or goes with it.
    const roles = after.roles.map((r) => ({
      key: roleKey(r),
      title: r.title,
      dates: r.dates,
      presence,
      lines: r.items.map((i) => line(i, presence, null)),
    }));
    return { ...base, fold: null, roles };
  }

  const fold =
    before.fold_earlier !== after.fold_earlier ? (after.fold_earlier ? "folded" : "unfolded") : null;
  const beforeCards = cardsIn(before);
  const afterCards = cardsIn(after);
  const beforeByKey = new Map(before.roles.map((r) => [roleKey(r), r]));
  const roles: DiffRole[] = after.roles.map((role) => {
    const was = beforeByKey.get(roleKey(role))?.items ?? [];
    const here = new Set(role.items.map((i) => i.card));
    const lines = diffLines(
      was,
      role.items,
      new Set([...beforeCards].filter((c) => !was.some((i) => i.card === c))),
      new Set([...afterCards].filter((c) => !here.has(c))),
    );
    // Folding titles moves their lines under the latest one; that's the
    // fold, not a move the person made line by line.
    if (fold) for (const l of lines) l.moved = false;
    return { key: roleKey(role), title: role.title, dates: role.dates, presence: "same", lines };
  });

  // Lines left out whose title no longer shows on its own, so they aren't
  // lost from view: they show, struck, under the first title.
  const afterKeys = new Set(after.roles.map(roleKey));
  const orphans = before.roles
    .filter((r) => !afterKeys.has(roleKey(r)))
    .flatMap((r) => r.items)
    .filter((i) => !afterCards.has(i.card))
    .map((i) => line(i, "removed", null));
  if (orphans.length > 0) {
    const home = roles.find((r) => r.key !== "employment") ?? roles[0];
    if (home) home.lines.push(...orphans);
    else roles.push({ key: "employment", title: "", dates: "", presence: "same", lines: orphans });
  }
  return { ...base, fold, roles };
}

// -- the top ---------------------------------------------------------------------

const HEADER_FIELDS: { field: keyof ResumeHeader; label: string }[] = [
  { field: "name", label: "Name" },
  { field: "headline", label: "Headline" },
  { field: "email", label: "Email" },
  { field: "phone", label: "Phone" },
  { field: "location", label: "Location" },
  { field: "links", label: "Links" },
  { field: "summary", label: "Summary" },
];

function headerText(header: ResumeHeader, field: keyof ResumeHeader): string {
  const value = header[field];
  return (Array.isArray(value) ? value.join(" · ") : value).trim();
}

// -- the whole page ------------------------------------------------------------

export function compareResumes(before: RenderedResume, after: RenderedResume): ResumeDiff {
  const header = HEADER_FIELDS.flatMap(({ field, label }) => {
    const was = headerText(before.header, field);
    const now = headerText(after.header, field);
    return was === now ? [] : [{ field, label, was, now }];
  });

  const keptJobs = steady(
    before.entries.map((e) => e.card),
    after.entries.map((e) => e.card),
  );
  const entries = mergeOrdered(before.entries, after.entries, (e) => e.card).map((m) =>
    diffEntry(
      m.presence === "same" ? m.before : null,
      m.item,
      m.presence,
      m.presence === "same" && !keptJobs.has(m.item.card),
    ),
  );

  const sections = mergeOrdered(before.sections, after.sections, (s) => s.kind).map((m) => ({
    kind: m.item.kind,
    label: m.item.label,
    presence: m.presence,
    lines:
      m.presence === "same"
        ? diffLines(m.before?.items ?? [], m.item.items)
        : m.item.items.map((i) => line(i, m.presence, null)),
  }));

  const all = [...entries.flatMap((e) => e.roles.flatMap((r) => r.lines)), ...sections.flatMap((s) => s.lines)];
  const counts: DiffCounts = {
    added: all.filter((l) => l.presence === "added").length,
    removed: all.filter((l) => l.presence === "removed").length,
    reworded: all.filter((l) => l.was !== null).length,
    moved: all.filter((l) => l.moved).length + entries.filter((e) => e.moved).length,
    jobsAdded: entries.filter((e) => e.presence === "added").length,
    jobsRemoved: entries.filter((e) => e.presence === "removed").length,
    folds: entries.filter((e) => e.fold !== null).length,
    header: header.length,
  };
  return { header, entries, sections, counts };
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "2 lines added, 1 left out, Northwind moved", or null when nothing changed. */
export function diffSummary(diff: ResumeDiff): string | null {
  const c = diff.counts;
  const parts: string[] = [];
  if (c.jobsAdded) parts.push(`${plural(c.jobsAdded, "job", "jobs")} added`);
  if (c.jobsRemoved) parts.push(`${plural(c.jobsRemoved, "job", "jobs")} left out`);
  if (c.added) parts.push(`${plural(c.added, "line", "lines")} added`);
  if (c.removed) parts.push(`${plural(c.removed, "line", "lines")} left out`);
  if (c.reworded) parts.push(`${c.reworded} reworded`);
  if (c.moved) parts.push(`${c.moved} moved`);
  if (c.folds) parts.push(c.folds === 1 ? "titles folded or unfolded at 1 job" : `titles folded or unfolded at ${c.folds} jobs`);
  if (c.header) parts.push("the top changed");
  if (parts.length === 0) return null;
  const text = parts.join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function changeCount(diff: ResumeDiff): number {
  const c = diff.counts;
  return c.added + c.removed + c.reworded + c.moved + c.jobsAdded + c.jobsRemoved + c.folds + c.header;
}
