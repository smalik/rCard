# Data model: cards, versions and variants

A person's cards must stay correct and readable for their whole working life,
across hundreds of tailored variants. These rules make that hold. The schema is
[`services/api/migrations/0001_foundations.sql`](../services/api/migrations/0001_foundations.sql).

## Records

| Record | Table | What it is |
| --- | --- | --- |
| Person | `plytos.app_user` | The account. Identified by a sign-in subject, nothing else in clear text |
| Data key | `plytos_vault.user_key` | The person's own 256-bit key, wrapped by the Cloud KMS key-encryption key |
| Card | `plytos.card` | One claim, kept for a whole career: kind, status, trust level, and the card it sits under (`parent_id`) |
| Target | `plytos.target` | An audience that spans cards (Finance, then JP Morgan under it). Name encrypted |
| Line | `plytos.card_line` | A card's line of versions. `target_id` null is the main line; otherwise a variant for one target |
| Version | `plytos.card_version` | One permanent snapshot on a line. Content encrypted; hashes in clear |
| Event | `plytos.event` | Append-only history: who did what to which record, never the content |
| Resume import | `plytos.resume_import` | A resume the person brought in: the original file, what was read from it, and their progress approving its cards. All encrypted; only the format, size, times and where the reading is (state, stage, tries, a short error code) are clear. Schema in [`0002_resume_import.sql`](../services/api/migrations/0002_resume_import.sql) and [`0009_import_reading.sql`](../services/api/migrations/0009_import_reading.sql) |
| Resume, resume version | `plytos.resume`, `plytos.resume_version`, `plytos.resume_version_name` | A resume is a selection over cards, with its own line of versions. Name and content encrypted; hashes in clear. Schema in [`0007_resumes.sql`](../services/api/migrations/0007_resumes.sql) and [`0008_resume_proposals.sql`](../services/api/migrations/0008_resume_proposals.sql). See "Resumes" below |
| Message, tidbit, proposal, agent run | `plytos.message`, `plytos.tidbit`, `plytos.proposal`, `plytos.agent_run` | The conversation with Plytos, the notes it keeps, what agents offer, and the work they did. Content encrypted. See [agents.md](agents.md) |
| Check-in plan | `plytos.check_in_plan` | When Plytos checks in, once a month: a week of the month, a weekday, a local time and a time zone. No content. See [agents.md](agents.md) |

## Rules

**Cards nest into a career tree.** An employment (employer and tenure) holds
its positions, and a position holds its accomplishments. Agency, consulting
and freelance work puts an engagement per client in between. A win that spans
promotions sits on the employment. Each level is its own card with its own
versions, so a fact lives at one level and the levels below show it without
copying it. Change the employer's name once and everything under it follows.

| Kind | May sit under |
| --- | --- |
| employment | nothing |
| position | employment |
| engagement | employment, position |
| project | employment, position, engagement |
| accomplishment | employment, position, engagement, project |
| story | accomplishment |
| skill, education, credential, activity | nothing |

Every allowed parent ranks above its child and a card's kind never changes, so
the tree can't loop. `role` is the flat kind from before the tree
([`0003_career_tree.sql`](../services/api/migrations/0003_career_tree.sql));
old cards keep it and new cards don't use it.

**Where a card sits is a fact.** The parent is part of the main version's
content (schema version 2), encrypted with the rest. `card.parent_id` mirrors
the current main version's parent in clear, holding only IDs, so the tree can
be read without decrypting. Moving a card is a new main version, so its
history shows where it used to sit. Variants can't move a card. A trigger
refuses a parent of the wrong kind, and a composite foreign key refuses a
parent that belongs to someone else.

**The order is the person's.** Siblings show in the order the person put
them in: `card.sort_key` ([`0010_card_order.sql`](../services/api/migrations/0010_card_order.sql)),
in clear like `parent_id` because it holds no text. Cards never placed sort
after placed ones, oldest first. `POST /v1/cards/reorder` places the cards
under one parent (`parent_id`, or none for the top of the tree) in the order
given (`card_ids`), and refuses (409) any card that isn't the person's or
doesn't sit there now; siblings left out keep their places. Reordering is
not a new version: it changes where a card shows, not what it says. Each
resume keeps its own order in its content.

**Evidence is attached on the main line.** Main versions carry `attachments`
(schema version 3): up to 20 papers, repositories or links, each a web
address (http or https only), a title and an optional note, encrypted with
the rest of the content. Variants can't add or change them. Versions saved
before schema 3 read as having none, so their hashes still verify.

**Facts live only on the main line.** Main versions hold `facts` (employer,
client, agency, title, dates, numbers, scope, skills, evidence) and default
`framing`. Variant versions hold `framing` only, so a variant can't change or
add a fact. A variant may also choose which facts to show (`shown_facts`).

**No new numbers.** Before a variant version is saved, every number in its
text must appear in the main version it's based on. Names, titles and skills
get the same check from the AI critics in M1.

**Depth: numbered versions.** Each save appends the next version on its line
(Main v1, v2, v3; Finance v1, v2). A version's number is its parent's plus one,
on the same line, enforced by a trigger.

**Breadth: one variant per target.** A card has one main line and at most one
variant line per target, enforced by unique indexes. Each variant version
records the main version it's based on.

**Behind.** When a main save changes facts, every current variant is marked
`behind`. Saving the variant again, against the latest main, makes it current.
Reworded main versions leave variants alone.

**The library is one read.** `GET /v1/library` returns every card that isn't
archived, with its main version's content, version number, author and time,
its `parent_id` and `sort_key`, and how many variants it has and how many
are behind. The cards screen polls it to stay live.

**Edits never overwrite each other.** A save names the version it started
from. If the line's head has moved, the save fails with a conflict (HTTP 409)
so the person or AI job can merge instead of overwriting.

**Append-only.** The app's database role can insert and read versions and
events but never update or delete them. A trigger blocks every update except
redaction, which blanks the content and keeps the number, date and hashes.

**Tamper evidence.** Each version stores the SHA-256 of its canonical JSON and
a chain hash over its parent's chain hash, like git. `GET /v1/cards/{id}/verify`
recomputes both. Attestations (M3) will sign one exact version's chain hash.

**Private by default.** Row-level security limits the app role to the person
set for the transaction. With no person set, nothing is visible. Composite
foreign keys stop any row from pointing at another person's rows.

**Deleted for real.** `plytos.purge_user` (callable only by the
`plytos_shredder` role) deletes the person's wrapped data key first, then
every row they own. Any copy left in a backup is unreadable without the key.

## Resumes

**A resume is a selection over cards, not a copy of them.** Its content
(`resumes/model.py`) lists the employments it shows, in order, the
accomplishments switched on under each, and the cards that come along at the
end (education, skills, credentials, activities). Positions and client work
show as headings under their employment, latest first; `fold_earlier` folds
every title but the latest into one line. Facts always come from the card as
it is now, so a corrected date shows in every resume at once.

**Each line names its wording.** `auto` uses the card's variant for the
resume's target if there is one, and the card's own wording otherwise. `main`
always uses the card's own wording, and a target ID picks that target's.
When the person rewords a line inside a resume, the item pins the card
version it was given, so that resume version keeps that exact wording.

**Every change is a version.** Versions are append-only and hash-chained like
card versions. A save names the version it started from and fails if the
resume moved on (409). Restoring version 2 makes a new version with
version 2's content and the note "Back to version 2"; nothing in between is
lost. A version can carry names the person gives it, such as "Sent to
Contoso".

**Versions for a target are made from a resume.** The first resume comes
from the person's own file: once they keep its cards, "as written" lays them
out in the file's order, in the file's words (`resumes/as_written.py`), one
per file. A version for a target records the resume it was made from
(`parent_id`) and which of that resume's versions it has caught up with
(`synced_parent_version_id`). When the parent changes, the person sees each
change since then that their version doesn't already reflect, takes the ones
they want, and passes on the rest; either way it catches up. Versions for a
target come from the Assembler in the conversation (see
[agents.md](agents.md)) or by hand, as a copy.

## Open design point

Backups of the main database also contain wrapped data keys, so a key deleted
today stays recoverable from backups until they expire (7 days of
point-in-time recovery, 14 daily backups). Before launch, either move
`plytos_vault.user_key` to a separate store with short retention, or give each person
a Cloud KMS key of their own and destroy it on deletion (about $0.06 per
person per month). Account deletion should promise erasure within that window.
