# Resume import

Importing a resume does three things:

1. **Reads** the file into lines in reading order (`imports/extract.py`).
2. **Splits** the lines into contact details, sections, roles, bullets,
   skills and entries. Claude Haiku 5.5 does this when it's configured
   (`imports/ai.py`); otherwise, or when it fails, the rule-based parser does
   (`imports/segment.py`).
3. **Audits** it for problems a recruiter or an applicant tracking system
   (ATS) would trip on (`imports/audit.py`), and **proposes cards** in the
   resume's own words (`imports/cards.py`).

The import is kept, encrypted with the person's own key, so they can work
through it over several sittings: the original file, exactly as uploaded;
what was read from it; and their progress. Nothing becomes a card until the
person approves it, one card at a time.

## Formats

| Format | How it's read |
| --- | --- |
| Word (.docx) | From the XML, so text boxes, content controls, tracked insertions, page headers and footers aren't missed. Each line keeps where it sat (body, table, text box, header, footer), its list bullet, bold, capitals, fonts and sizes. |
| PDF | From the text layer with pdfplumber. Two-column layouts are detected by an empty vertical strip and read column by column. A scan with no text layer is reported, not guessed at. |
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
| Dates | Missing dates; year-only dates; client engagements with no dates of their own; end before start; dates in the future; not newest first (by end date); overlapping roles; gaps over six months; several current roles |
| Consistency | The same result quoted with different numbers (say, a highlight and the role it came from); date formats, including two formats in one range; range separators; "Present" vs "Current"; bullet styles; bold bullets; bullets typed by hand; title-first vs employer-first headers; end punctuation; fonts and sizes in bullets, role headings and client headings; heading formatting; number of fonts; heading capitalization; double spaces; present tense in past roles, including clauses ("Designed X, supervise Y") |
| Content | Objective instead of summary; "References available upon request"; duty openers ("Responsible for"); first person; roles with no numbers; roles written as paragraphs; bullets over 40 words; more than 8 bullets; roles with no description; repeated sentences anywhere; repeated opening verbs; stock phrases; personal details US employers avoid; detail on roles over 15 years old; skills spelled differently from their usual form ("Tableu", "Sagemaker") |
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
| Each bullet | `accomplishment`: its workstream label if it sits under one, and every number in the text as `figures` | its position or engagement |
| Each sentence of a role written as a paragraph | `accomplishment`, as for a bullet | its position or engagement |
| Key achievements | `accomplishment`; one that names a single client or employer is proposed under that work, with a question to confirm it | that work, or nothing |
| Each skills line | `skill`, with the category and skills as facts | nothing |
| Education | `education`, with institution, degree and date | nothing |
| Certifications | `credential` | nothing |
| Projects | `project` | nothing |
| Awards | `accomplishment`, with the award as a fact | nothing |

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

- Text inside images isn't read. The audit flags a large image in the body,
  but recovering a screenshot's text needs OCR, which comes later.
- Spelling and grammar aren't checked beyond skill names.
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
