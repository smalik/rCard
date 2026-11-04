# Agents: one voice, many small helpers

People don't fill in Plytos. They talk to it. Plytos asks now and then what
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

Schema: [`0004_agents.sql`](../services/api/migrations/0004_agents.sql). Every
table is owned by one person, under row-level security, and their content is
encrypted with that person's data key.

| Record | Table | What it is |
| --- | --- | --- |
| Message | `plytos.message` | The conversation, from the person or from Plytos. Append-only: the app can't change or delete a message |
| Tidbit | `plytos.tidbit` | A note about work, kept as the person wrote it, forever. The Listener reads it once and files it under a job |
| Proposal | `plytos.proposal` | Something an agent offers: a new card, and later a version, variant, resume, question or insight. Decided once |
| Agent run | `plytos.agent_run` | One piece of agent work: queued, running, done or failed, with what it cost in tokens. Never content |

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
same key, which is how a burst of notes turns into one Stitcher pass.

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

## API

| Method and path | What it does |
| --- | --- |
| `GET /v1/conversation?before=&limit=` | The latest messages, oldest first. `before` pages back |
| `POST /v1/conversation` | The person says something. The Listener answers shortly after |
| `GET /v1/proposals?state=open` | Proposals, by state |
| `POST /v1/proposals/{id}/keep` | Keeps a proposed card, as proposed or with the person's edits (`content`) |
| `POST /v1/proposals/{id}/dismiss` | Says no to a proposal |
| `GET /v1/tidbits?card_id=` | The person's notes, oldest first, all or under one job |
| `GET /v1/agent-runs` | What the agents did lately, for "how I got here". Never content |

## Next

Check-ins on a schedule (in the app first, text messages after carrier
registration), the conversation screen in the web app, and moving the resume
import into the conversation. Then the Scout and Assembler for applying.
