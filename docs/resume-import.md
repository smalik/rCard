# Resume import

Importing a resume does three things:

1. **Reads** the file into lines in reading order (`imports/extract.py`).
   With Claude configured, the words in its pictures (a scanned page, a
   screenshot of bullets) become lines too (`imports/pictures.py`).
2. **Splits** the lines into contact details, sections, roles, bullets,
   skills and entries. Claude Haiku 5.5 does this when it's configured
   (`imports/ai.py`); otherwise, or when it fails, the rule-based parser does
   (`imports/segment.py`).
3. **Audits** it for problems a recruiter or an applicant tracking system
   (ATS) would trip on (`imports/audit.py`), and **proposes cards** in the
   resume's own words (`imports/cards.py`).
4. **Checks** that every line landed somewhere (`imports/accounting.py`) and
   that every result and title sits under the job it came from
   (`imports/placement.py`).

The import is kept, encrypted with the person's own key, so they can work
through it over several sittings: the original file, exactly as uploaded;
what was read from it; and their progress. Nothing becomes a card until the
person approves it, one card at a time.

## Formats

| Format | How it's read |
| --- | --- |
| Word (.docx) | From the XML, so text boxes, content controls, tracked insertions, page headers and footers aren't missed. Each line keeps where it sat (body, table, text box, header, footer), its list bullet, bold, capitals, fonts and sizes. Pictures big enough to hold words are kept to read. |
| PDF | From the text layer with pdfplumber. Two-column layouts are detected by an empty vertical strip and read column by column. A page with no text layer (a scan) is kept as a picture to read, and reported. Pictures on a page are kept to read too, unless text-layer words sit over them (a background, or a scan that was already turned into text). |
| Plain text | Line by line, with typed bullets. |

Old `.doc` files are refused with a request to save as .docx or PDF. Files
are capped at 5 MB and 12 pages, and Word files are checked for zip bombs
before they're opened.

## What the audit checks

Each check is deterministic: the same resume always gets the same audit.
Severity says how much it matters.

- **fix**: likely to cost the person (a misread or a rejection).
- **improve**: would read better.
- **note**: worth knowing.

| Area | Checks |
| --- | --- |
| ATS and layout | No text layer; contact details only in the page header, footer or text boxes; other text in text boxes; tables; multiple columns; a text-width image in the body (often a screenshot of text); smaller images and icons; no experience found; a summary filed under an Experience heading; roles missing a title or employer; non-standard section headings; no skills or education section; body text under 10 pt; lines under 8 pt |
| Dates | Missing dates; year-only dates; client engagements with no dates of their own; end before start; dates in the future; not newest first (by end date); overlapping roles (not when they only share a year written without months, as in "2003 – 2005" then "MAR 2005 – Present"); gaps over six months; several current roles |
| Consistency | The same result quoted with different numbers (say, a highlight and the role it came from); date formats, including two formats in one range; range separators; "Present" vs "Current"; bullet styles; bold bullets; bullets typed by hand; title-first vs employer-first headers; end punctuation; fonts and sizes in bullets, role headings and client headings; heading formatting; number of fonts; heading capitalization; double spaces; present tense in past roles, including clauses ("Designed X, supervise Y") |
| Content | Objective instead of summary; "References available upon request"; duty openers ("Responsible for"); first person; roles with no numbers; roles written as paragraphs; bullets over 40 words; more than 8 bullets; roles with no description; repeated sentences anywhere; repeated opening verbs; stock phrases (whole words, so "Dynamics 365" isn't "dynamic"); notes left in the text ("(confirm employer)", "TBD", "XX%"); personal details US employers avoid; detail on roles over 15 years old; skills spelled differently from their usual form ("Tableu", "Sagemaker") |
| Contact | Name, email, phone, LinkedIn, city and state; several emails; a full street address; phone spacing |
| Length | Over two pages; very short; a long summary |
| File | An employer's sensitivity or classification marking (from Microsoft Purview and similar tools, read from the page and from the file's properties); tailoring tags (such as an employer's initials); version words like "final"; no name |

Every finding names the lines it's about, so the review screen can show the
problem on the card it belongs to.

Each finding also says what it's `about`:

- **`cards`**: the problem is in the words or facts that become cards (tense,
  conflicting figures, duty openers, missing numbers, dates, gaps and
  overlaps). It travels into the cards and needs fixing there.
- **`document`**: the problem is in how this file is laid out or formatted
  (date formats, bullet styles, fonts, text boxes, the file name). It doesn't
  come along into the cards, because Plytos stores facts and words, not
  formatting.

The list of card rules is `CARD_RULES` in `imports/audit.py`.

## Screens

`/import` in the web app (`apps/web/src/app/import`) follows the four steps
of the Hybrid designs in Figma: Bring in, Check, Approve, and See strengths
(still to come). Phone first; on a laptop the Check and Approve screens put
the card and its source side by side.

1. **Start** (`/import`): upload a Word, PDF or text file, or paste text.
   Photo and voice are shown as coming soon. If an import still has cards
   waiting, the screen offers to pick up where the person left off.
2. **Reading**: the browser posts the file to `/import/upload`, which passes
   it to `POST /v1/imports`. While the API reads, the screen shows progress,
   then ticks off what was found with the real counts.
3. **Check** (`/import/{id}`): the starting proof (accomplishments with and
   without numbers), an audit checklist (jobs and dates, numbers, repeats,
   skills, wording tips, what was left out), the person's file with "View
   original" and a delete button, and the full audit at `/import/{id}/audit`.
4. **Settle** (`/import/{id}/settle`): the questions of fact, one open at a
   time, each with the lines it came from. When a result has two numbers,
   the person picks the right one, and every proposed card that used the
   other is rewritten to match. Other questions take "it's right", "I'll fix
   it on the card" or "later". Answers can change until a card is approved.
5. **Approve** (`/import/{id}/approve`): ten cards at a sitting, strongest
   first (results with numbers, then other results, awards and projects,
   roles, the rest). Each card shows its facts, open questions, the lines it
   came from, and wording tips. The person approves it, edits it first,
   leaves it out, or says "Not now", which keeps it as a draft for later.

Every route handler checks the request came from Plytos's own pages. The
screens get only the lines each card came from; the rest of the text and the
contact details stay on the server. Nothing goes to browser storage.

## API

| Endpoint | What it does |
| --- | --- |
| `POST /v1/imports` | Reads the file in the request body and keeps the import. The file name comes in `X-Plytos-Filename` |
| `GET /v1/imports` | The person's imports, with counts of cards approved, for later, left out and questions open |
| `GET /v1/imports/{id}` | One import: what was read, and the person's progress |
| `GET /v1/imports/{id}/original` | The original file, byte for byte |
| `POST /v1/imports/{id}/settle` | Answers one question. A chosen number rewrites the proposed cards that use the other |
| `POST /v1/imports/{id}/cards/{ref}/decision` | Sets a proposed card aside for later, leaves it out, or undoes that |
| `POST /v1/imports/{id}/cards/{ref}/place` | Answers a placement question: the card it sits under (`parent_ref`, or null for none) |
| `POST /v1/imports/{id}/cards/{ref}/approve` | Makes the card, as proposed or in the person's edited words, as an approved card written by the person |
| `DELETE /v1/imports/{id}` | Deletes the original file and everything read from it. Approved cards stay |

## Reading the structure with Claude

Rules can't keep up with every way people lay out a resume. Several titles
listed under one employer line with the whole tenure beside it (promotions) is
the case that showed it: the rules read the employer line as a role of its
own, split "Director, Supply Chain Operations" into a title and an employer,
and left the earlier titles with no employer.

So Claude decides which line is which:

- It gets the resume as numbered lines with layout hints (bullet, bold, caps,
  table, text box, page header) and returns JSON that matches a fixed schema
  (`AiResume`): sections, contact lines, roles with their own lines and
  dates, bullets, skills and entries. Promotions under one employer become one
  role per title, each with the employer and its own dates.
- It points at lines and copies values; it doesn't write text. Every value is
  then checked against the lines it came from (`verbatim`). A title, employer,
  client, date or skill the resume doesn't contain is dropped, and the card
  asks the person instead, so a card never says something the resume doesn't.
  Line numbers that don't exist are ignored, a line belongs to one role only,
  and experience lines it left out stay with the role above them.
- The audit and the proposed cards run on its reading exactly as they do on
  the rules' reading. The import records which model read it (`read_by`).
- If it isn't configured, errors, declines or returns something that doesn't
  match the schema, the rule-based parser runs instead. An import never
  depends on it.

Because Claude only points at the person's own words, an approved card is
still the person's text and is recorded as theirs. Rewording with AI is a
different step and will be recorded with `author_kind = 'ai'`.

| Setting | Default | |
| --- | --- | --- |
| `PLYTOS_AI_PROVIDER` | `off` | `anthropic` (Claude API, key from `ANTHROPIC_API_KEY`) or `vertex` (Claude on Vertex AI, with the service's identity) |
| `PLYTOS_AI_MODEL` | `claude-haiku-5-5` | |
| `PLYTOS_AI_EFFORT` | `medium` | |
| `PLYTOS_AI_VERTEX_PROJECT`, `PLYTOS_AI_VERTEX_REGION` | `""`, `global` | For `vertex` only |

A resume is a few thousand tokens in and out, which is well under a cent on
Haiku 5.5.

### What it costs

Every Claude call is recorded (`imports/usage.py`) with the step it served
(`pictures`, `structure`, `placement`, `facts`, `proofread`), its effort, the
tokens the API reported (input, output, thinking, cache reads and writes), its
seconds and its list price. The import keeps them with its result (`usage`),
and each is logged as one line of numbers, never the resume's text. Each
import counts its own calls (`ClaudeReader.metered()`), and resumes share no
prompt cache: each is read as one person's upload.

To measure it over many resumes, the bench runs the same import over folders
of files and stops at a spend cap kept across runs:

```sh
cd services/api
PLYTOS_AI_PROVIDER=anthropic uv run python -m plytos_api.imports.bench \
  ~/resumes --budget 20 --sample 50 --out ~/.plytos/bench
```

It samples across the folders (one category per subfolder), skips resumes it
measured before, and writes `results.jsonl` (numbers per resume), `index.jsonl`
(what grouping similar resumes needs: category, size, employers, titles,
years, skills) and a summary of cost per resume and per step and what $1, $3
and $20 buy. The output holds what was read from the resumes, so it stays on
the machine that has them.

A reply that doesn't fit the schema is asked for once more before the import
falls back to the rules; only the error's field and type are logged. A call
made with a model missing from the price table is counted at the dearest priced
call of its step, so the spend cap is never undercounted.

## Reading pictures

Some resumes carry words the file's text doesn't: a screenshot of bullets, a
heading or name drawn as an image, labelled skill bars, or a whole page
scanned with no text layer. Before the lines are sorted, Claude reads them:

- Extraction keeps the pixels of each picture at least 1 inch wide and a
  quarter inch tall (icons and bullets aren't worth it), up to 10 per resume:
  Word pictures from the file, PDF pictures and scanned pages rendered with
  pdfium. They're shrunk to what Claude reads (1568 px on the long edge) and
  never stored or logged; the import keeps only the lines read from them.
- One request, at low effort, sends every picture with a label ("Picture 2:
  page 1, which is a scan with no text in it"). Claude says what each is
  (text, logo, photo, chart, decoration) and, for text, copies its lines
  exactly, in reading order, with bullets and bold marked and `[?]` for a word
  it can't make out (`AiPictures`).
- Each line goes in right after the line the picture follows, marked
  `where: "image"`, and the lines are renumbered. From there it's a line like
  any other: Claude's reading, the audit, the cards and the line accounting
  all see it. Logos, photos and charts add nothing.
- Every card made from a picture's words asks the person to check the
  wording, since reading a picture can get a word wrong.
- The audit still says the picture is a problem for applicant tracking
  systems (`ats.large_image`, `ats.no_text`, or `ats.scanned_page` for one
  scanned page in a PDF with text), and says Plytos read its words.

Without Claude, or when the request fails, pictures stay unread and the audit
reports them as before.

## Facts in each accomplishment

Once the cards are proposed, Claude reads the accomplishments (as R1, R2...,
at low effort) and names, for each, the skills, tools or fields its words
name (`skills`), what shows its size or reach, such as a team, budget, sites
or money (`scope`), and the phrase that states what it achieved (`outcome`).
Each value is kept only when it's in that accomplishment word for word, so a
card never claims a skill or a size its words don't. They show on the card
as Result, Scope and Skills, and the person can change them before approving.
This runs alongside the placement check, and only when Claude read the
structure.

## Proofreading

While the structure is read, Claude proofreads the lines for misspellings,
wrong words (lead for led) and broken grammar, leaving style, tense, resume
conventions and names alone. Each typo becomes a `content.proofread` finding
with the words as written and a suggestion. A typo is kept only when its
quote is on the line it names, misspelled skills the audit already flags
aren't repeated, and there are at most 20. Nothing changes unless the person
edits the card.

## Every line accounted for

After the cards are proposed, every line of the resume must be in one of five
places: on a card, in the contact details, a section heading, skipped for a
stated reason (`page_number`, `page_header`, `decoration`, `references`, or a
classification `marking`), or on a card of its own. A short label inside a job
that its bullets sit under ("Enterprise AI") counts as a heading and becomes
those cards' workstream. A "Continued..." footer is skipped as a page number,
even when the reader took it for contact details. A line nothing claimed
gets that card, placed by the section it sits in (an accomplishment under the
nearest job above it, a skill, an education entry, an activity), with a
question asking the person to keep, move or drop it. The import records the
count (`lines`), so nothing the person wrote is lost without them seeing it.

## Checking where each line was filed

An accomplishment under the wrong title misstates someone's career, so two
checks go over the tree once it's built:

- **Order.** On most resumes a line belongs to the title written above it,
  and a title to the employer above it, within the same section. A title
  written on the employer's own line ("Consultant, Contoso - 2019 – 2023") is
  under that employer. Skipped for multi-column layouts, where reading order
  isn't reliable.
- **A second look by Claude**, separate from the reading. It gets the numbered
  lines and the tree in short refs (E1 employer, T1 title, C1 client work) and
  names anything filed in the wrong place, with the cue in the resume that
  shows it.

A card either check flags gets a question: "Which job is this from?", "Which
employer was this title at?" or "Which job was this client work part of?".
When both checks agree on another place, the card is moved there and the
question asks the person to confirm; otherwise it stays put and the question
offers the other place. The card can't be approved until the person answers.

## Proposed cards

Cards are proposed as a career tree (see [data-model.md](data-model.md)).
Titles held at one employer go inside one employment, and every bullet goes
under the title it was written under.

| Resume part | Card | Sits under |
| --- | --- | --- |
| Summary or objective | `story`, marked as the summary | nothing |
| Each employer, with the tenure | `employment`: employer, start, end, location, employment type | nothing |
| Each title held there | `position`: title, its own start and end, and a location or type only when it differs from the employment's | its employment |
| Each client engagement under an agency or consultancy role | `engagement`: client, title, dates | the agency position |
| Each bullet | `accomplishment`: its workstream label if it sits under one, and every number in the text as `figures`, except ones in a name or code ("Dynamics 365", "Q3") and "24/7" | its position or engagement |
| Each sentence of a role written as a paragraph | `accomplishment`, as for a bullet | its position or engagement |
| Key achievements | `accomplishment`; one that names a single client or employer is proposed under that work, with a question to confirm it | that work, or nothing |
| Each skills line | `skill`, with the category and skills as facts | nothing |
| Education | `education`, with institution, degree and date | nothing |
| Certifications | `credential` | nothing |
| Projects | `project` | nothing |
| Awards | `accomplishment`, with the award as a fact | nothing |
| Talks, publications, board seats, memberships, interests | `activity`, with its name and date | nothing |

Titles join one employment when they share the employer's own line, or when
they sit next to each other at the same employer with no more than six months
between them. A longer gap, or another employer in between, reads as leaving
and coming back: two employments. The tenure comes from the employer's line
when the resume writes one, and is otherwise worked out from the titles'
dates (marked `tenure: from positions`). A title whose dates fall outside a
written tenure is flagged (`dates.outside_tenure`). Overlapping titles at one
employer aren't flagged; overlapping jobs at different employers still are.

Approving keeps the tree: a card sits under the saved card of its nearest
approved parent. A card whose parent is still undecided can't be approved
until the parent is; a dropped parent passes its children up a level.

The words are the person's own; nothing is rewritten. Where the import had to
guess (which part is the title, a role's employer inferred from the line
above, an engagement's dates, year-only dates) the card carries `needs_check`
questions for the person to answer during review. Rewriting with AI comes later and follows the
usual rule: AI proposes, the person decides.

Numbers go into `figures` so that variants can cite them: the "no new
numbers" rule only lets a variant use numbers its main version has.

## Known gaps

- Text inside images is read only when Claude is configured. Pictures in
  formats Claude can't take (Windows metafiles) stay unread.
- Without Claude, spelling and grammar aren't checked beyond skill names.
- Facts are compared only where a figure repeats between the summary or
  highlights and a role. Checking names and titles against each other needs
  language understanding and comes with the AI critics in M1.
- Findings come from the uploaded file. Editing a card doesn't re-run them.
- Findings don't come with proposed rewrites yet.

## Privacy

- The original file, its name, what was read and the person's progress are
  each encrypted with the person's own data key, bound to the import's id.
  The app role can't change the file or what was read; only progress
  updates. Deleting an import, or the person, deletes all of it.
- Nothing about the file is written to disk or logs. Events record that an
  import was created or deleted, never what was in it.
- "View original" serves the file with its own content security policy: no
  scripts, no framing. Word files download; PDFs and text open in the browser.
- The file name comes in the `X-Plytos-Filename` header, never the URL,
  because URLs reach request logs and resume file names carry names.
- `.docx`, `.pdf` and other document types are git-ignored, and tests build
  made-up resumes in code. A real resume never enters the repo.
- With `PLYTOS_AI_PROVIDER` set, the resume's text (not the file) is sent to
  the model provider for each import: Anthropic for `anthropic`, Google Cloud
  for `vertex`. Check the provider's data retention terms before production;
  `vertex` keeps it inside the Plytos Google Cloud account's agreements. The
  API key lives in Secret Manager in production, never in the repo. Failures
  are logged by error class only, never with the text.

## Trying it

Run the API and web app as in the README, then open
<http://localhost:3000/import>. Or run the import alone:

```sh
cd services/api
uv run python -m plytos_api.imports "path/to/resume.docx"
uv run python -m plytos_api.imports "path/to/resume.docx" --json
# Claude reads the structure (needs ANTHROPIC_API_KEY):
uv run python -m plytos_api.imports "path/to/resume.docx" --ai
```
