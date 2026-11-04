# Resume import

Importing a resume does three things, and stores nothing:

1. **Reads** the file into lines in reading order (`imports/extract.py`).
2. **Splits** the lines into contact details, sections, roles, bullets,
   skills and entries (`imports/segment.py`).
3. **Audits** it for problems a recruiter or an applicant tracking system
   (ATS) would trip on (`imports/audit.py`), and **proposes cards** in the
   resume's own words (`imports/cards.py`).

The person reviews the proposals and the audit. Only the cards they keep
become card versions, through `POST /v1/imports/accept`.

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

## Privacy

- Preview (`POST /v1/imports/preview`) takes the file as the request body and
  returns the result. Nothing is written to the database, disk or logs.
- The file name comes in the `X-Plytos-Filename` header, never the URL,
  because URLs reach request logs and resume file names carry names.
- `.docx`, `.pdf` and other document types are git-ignored, and tests build
  made-up resumes in code. A real resume never enters the repo.

## Trying it

```sh
cd services/api
uv run python -m plytos_api.imports "path/to/resume.docx"
uv run python -m plytos_api.imports "path/to/resume.docx" --json
```
