# Agents: one voice, many small helpers

People don't fill in Plytos. They talk to it. Plytos asks once a month what
moved at work, takes a quick note whenever they have one, and over weeks joins
the notes into accomplishments they can keep with one tap. Behind that one
voice, small agents each do one job over the person's data.

The concept, the full roster and the build order are in the
[agentic Plytos concept doc](https://claude.ai/artifact/Vtd2y46cDfBk1ZvWbaEXqX).
This page covers what is built.

## The rule that holds everything

**Agents propose, the person decides.** An agent never writes a card. It writes
a proposal, and Plytos offers it in the conversation. Keeping it creates the
card version: `author_kind = 'ai'` when kept as proposed, `'person'` when the
person edited it first. Dismissed and replaced proposals stay on record.

## Records

Schema: [`0004_agents.sql`](../services/api/migrations/0004_agents.sql) and
[`0005_check_ins.sql`](../services/api/migrations/0005_check_ins.sql). Every
table is owned by one person, under row-level security, and their content is
encrypted with that person's data key.

| Record | Table | What it is |
| --- | --- | --- |
| Message | `plytos.message` | The conversation, from the person or from Plytos. Append-only: the app can't change or delete a message. A message can point at a resume shared in the conversation (`import_id`); deleting the import removes the link |
| Tidbit | `plytos.tidbit` | A note about work, kept as the person wrote it, forever. The Listener reads it once and files it under a job |
| Proposal | `plytos.proposal` | Something an agent offers: a new card, and later a version, variant, resume, question or insight. Decided once |
| Agent run | `plytos.agent_run` | One piece of agent work: queued, running, done or failed, with what it cost in tokens. Never content |
| Check-in plan | `plytos.check_in_plan` | When Plytos checks in: once a month, on a week and weekday, at a local time in the person's time zone, or off. Never content |

The database enforces the rules that matter whatever the code does:

- A tidbit's text and time never change, and only an unread tidbit can take a
  reading (`tidbit_read_once`).
- A proposal changes only from open to decided, and only its decision columns
  change (`proposal_decided_once`).
- Only Plytos can offer a proposal in the conversation.
- A run's error is a short code (`^[a-z][a-z_]{0,63}$`), so no content can end
  up in it.

## The runtime

`plytos.agent_run` doubles as the queue. `plytos.claim_agent_runs` (security
definer, `for update skip locked`) hands the worker runs that are due and leases
them for five minutes, so a crashed worker's runs come back. The worker then
does each run inside that person's own transaction (`Database.as_user`), so
row-level security holds for everything the agent reads and writes.

If an agent fails, its writes roll back with the transaction and the run goes
back in the queue: after 1 minute, then 2. After the third try it stays failed.
A run queued with a `dedupe_key` stands in for any other run queued under the
same key, which is how a burst of notes turns into one Stitcher pass. A run can
also wait for a set time: the next check-in sits in the queue under the key
`check_in` until it's due, and moving the plan moves that run.

Agents ask the model through `Thinker` (`agents/thinking.py`) for answers that
match a Pydantic model. The person's words go to the model provider, so nothing
logs them: failures are logged by error class only.

| Setting | Default | What it does |
| --- | --- | --- |
| `PLYTOS_AI_PROVIDER` | `off` | `anthropic` or `vertex` turns the agents' thinking on |
| `PLYTOS_AGENTS_INLINE` | `false` | Runs a worker on a thread inside the API. For development |
| `PLYTOS_STITCH_DELAY_SECONDS` | `30` | How long the Stitcher waits after a note, so a burst is read together |

In production the worker runs as its own service: `python -m plytos_api.agents`.
It isn't deployed yet.

## The agents built so far

**Listener** (`agents/listener.py`) reads each message the person sends. If it
tells something about work, the Listener keeps it as a tidbit, files it under
the job it belongs to, and notes a summary, projects, figures and whether it
says how things turned out. Then it answers in a sentence or two, asking for
one missing number or outcome when that would make the note stronger. It never
mentions job hunting: people answer at work, near coworkers. A figure the
person didn't write is dropped, whatever the model says. With AI off, it still
keeps the note, under the current job when there is only one.

**Stitcher** (`agents/stitcher.py`) reads the notes not yet used, job by job,
with its own drafts still waiting. When notes written weeks apart are one
accomplishment, it drafts a card and offers it, asking for the result if it's
missing. A draft that gains a new note replaces the old one. A draft that
claims a number its notes don't contain is dropped: the Stitcher joins and
words what the person said, never adds to it.

**Check-in** (`agents/check_in.py`) asks one short question once a month, at
the time the person picked: the last Friday at 4 PM unless they choose another
week, day or time. Plytos offers check-ins after the person's first exchange,
and they can change them or turn them off from the top of the conversation.
When it's due, the Check-in follows up something open if there is one: a draft
win missing its result, or a note from the last couple of months that didn't
say how things turned out. Each is followed up once. Otherwise it asks a fresh
question about the month. A question the model writes may only use figures the
person wrote; anything else falls back to a plain question, and so does AI
being off. It doesn't interrupt: if the person wrote in the last two hours, it
asks at the same time the next day. A check-in more than six hours late (the
worker was down) is skipped. Either way the next month's is queued. The
person's answer goes to the Listener like any message, which reads it with the
question before it.

**Assembler** (`agents/assembler.py`) puts together a version of a resume
for a target. The person asks from a resume's page ("Make a version for…")
or just says it in the conversation, and the Listener hands it over. It
starts from the resume asked about, or else the person's own as written,
and picks from everything on file: which employments show, which
accomplishments are switched on under each and in what order, what comes
along at the end, whether earlier titles fold, and up to eight lines to word
for the target. The model sees refs (E1, A3, C2), never IDs, and an
accomplishment it puts under the wrong employment is dropped, as is a
rewording with a number its card doesn't have. If the ask doesn't say who
it's for, it asks once. It proposes; keeping it creates the target, makes
the resume from the one it started with (its first version is the
Assembler's), and turns each kept rewording into the card's variant for that
target, also the Assembler's. Keeping after changes makes the first version
the person's. With AI off, it says so and points to making a copy by hand.

## A resume in the conversation

The person can share a resume from the composer (or "Start from my resume"
on an empty thread). It's read and kept like any import (see
[resume-import.md](resume-import.md)), and Plytos answers in the thread with
what it found: employers, titles, results, and how many questions need an
answer first. The resume card in the thread leads to the next step: the
questions, then the cards, then what was read. Going through the cards still
uses the import screens for now.

## API

| Method and path | What it does |
| --- | --- |
| `GET /v1/conversation?before=&limit=` | The latest messages, oldest first. `before` pages back |
| `POST /v1/conversation` | The person says something. The Listener answers shortly after |
| `POST /v1/conversation/resume` | The person shares a resume (the file is the body, its name in `X-Plytos-Filename`). Returns both messages and the import's summary |
| `GET /v1/proposals?state=open` | Proposals, by state |
| `POST /v1/proposals/{id}/keep` | Keeps a proposed card, as proposed or with the person's edits (`content`) |
| `GET /v1/proposals/{id}/resume` | A proposed resume as it would read, with the wording drafted for it |
| `POST /v1/proposals/{id}/keep-resume` | Keeps a proposed resume, as proposed or with the person's changes (`content`), and the rewordings they kept (`rewordings`, card IDs; omitted keeps all) |
| `POST /v1/proposals/{id}/dismiss` | Says no to a proposal |
| `GET /v1/resumes` | The person's resumes, and files with kept cards that no resume was made from yet |
| `POST /v1/resumes/as-written` | Makes the resume as written from a file's kept cards (`import_id`). Asking again returns the one made |
| `GET /v1/resumes/{id}` | A resume with its versions, and the page as it reads now |
| `PATCH /v1/resumes/{id}` | Renames it |
| `POST /v1/resumes/{id}/preview` | How a change would read (the body is the content), without saving it |
| `POST /v1/resumes/{id}/versions` | Saves a change as a new version (`base_version_id`, `content`); 409 if it moved on |
| `GET /v1/resumes/{id}/versions/{n}` | One earlier version and how it reads |
| `POST /v1/resumes/{id}/restore` | Brings version `number` back as a new version |
| `POST /v1/resumes/{id}/versions/{n}/name` | Names a version |
| `GET /v1/resumes/{id}/parent-changes` | Changes in the resume it was made from that it hasn't taken, each said plainly |
| `POST /v1/resumes/{id}/take` | Takes the changes named by `keys` and catches up; no keys passes on them all |
| `POST /v1/resumes/{id}/copies` | Makes a version for a target by hand (`name`, `target`, `target_kind`) |
| `POST /v1/resumes/{id}/ask` | Asks Plytos in the conversation for a version of this resume (`text`); the Assembler answers there |
| `GET /v1/tidbits?card_id=` | The person's notes, oldest first, all or under one job |
| `GET /v1/agent-runs` | What the agents did lately, for "how I got here". Never content |
| `GET /v1/check-ins` | The check-in plan, said plainly, and when the next one is due. No plan means the person hasn't been asked yet |
| `PUT /v1/check-ins` | Sets the plan (`week`, `weekday`, `time`, `time_zone`) or turns it off (`state: "off"`). Plytos confirms in the conversation |

## Next

Check-ins reach people only when they open the app for now. Next come
notifications (web push, then text messages after carrier registration), moving
the resume import's card review into the conversation, and then the Scout for
finding roles to apply to.
