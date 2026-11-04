# Data model: cards, versions and variants

A person's cards must stay correct and readable for their whole working life,
across hundreds of tailored variants. These rules make that hold. The schema is
[`services/api/migrations/0001_foundations.sql`](../services/api/migrations/0001_foundations.sql).

## Records

| Record | Table | What it is |
| --- | --- | --- |
| Person | `plytos.app_user` | The account. Identified by a sign-in subject, nothing else in clear text |
| Data key | `vault.user_key` | The person's own 256-bit key, wrapped by the Cloud KMS key-encryption key |
| Card | `plytos.card` | One claim, kept for a whole career: kind, status, trust level |
| Target | `plytos.target` | An audience that spans cards (Finance, then JP Morgan under it). Name encrypted |
| Line | `plytos.card_line` | A card's line of versions. `target_id` null is the main line; otherwise a variant for one target |
| Version | `plytos.card_version` | One permanent snapshot on a line. Content encrypted; hashes in clear |
| Event | `plytos.event` | Append-only history: who did what to which record, never the content |

## Rules

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

## Open design point

Backups of the main database also contain wrapped data keys, so a key deleted
today stays recoverable from backups until they expire (7 days of
point-in-time recovery, 14 daily backups). Before launch, either move
`vault.user_key` to a separate store with short retention, or give each person
a Cloud KMS key of their own and destroy it on deletion (about $0.06 per
person per month). Account deletion should promise erasure within that window.
