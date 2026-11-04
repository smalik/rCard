# Resume import

Importing a resume does three things:

1. **Reads** the file into lines in reading order (`imports/extract.py`).
2. **Splits** the lines into contact details, sections, roles, bullets,
   skills and entries (`imports/segment.py`).
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

## Proposed cards

| Resume part | Card |
| --- | --- |
| Summary or objective | `story`, marked as the summary |
| Each role | `role`, with employer, title, start, end, location and employment type as facts |
| Each client engagement under an agency or consultancy role | `role`, with the agency or firm as `employer` and the client as `client` |
| Each bullet | `accomplishment`, with the role's employer, client, title and dates as context, its workstream label if it sits under one, and every number in the text as `figures` |
| Each sentence of a role written as a paragraph | `accomplishment`, as for a bullet |
| Key achievements | `accomplishment` |
| Each skills line | `skill`, with the category and skills as facts |
| Education | `education`, with institution, degree and date |
| Certifications | `credential` |
| Projects | `project` |
| Awards | `accomplishment`, with the award as a fact |

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

## Trying it

Run the API and web app as in the README, then open
<http://localhost:3000/import>. Or run the import alone:

```sh
cd services/api
uv run python -m plytos_api.imports "path/to/resume.docx"
uv run python -m plytos_api.imports "path/to/resume.docx" --json
```
