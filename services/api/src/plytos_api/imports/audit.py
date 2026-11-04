"""The import audit: problems a recruiter or an applicant tracking system would trip on.

Each check is deterministic, so the same resume always gets the same audit.
Severities: "fix" is likely to cost you (a misread or a rejection), "improve"
would read better, and "note" is worth knowing.
"""

import itertools
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import PurePath

from plytos_api.imports.model import (
    Block,
    Category,
    DateRange,
    ExtractedDocument,
    Finding,
    Location,
    ParsedResume,
    Role,
    Severity,
)
from plytos_api.imports.segment import (
    EMAIL,
    PHONE,
    STREET,
    TITLE_WORDS,
    body_size,
    is_marking,
    sentences,
)
from plytos_api.imports.skills import spelling_fixes

SEVERITY_ORDER: dict[Severity, int] = {"fix": 0, "improve": 1, "note": 2}

_SUGGESTED_HEADING = {
    "summary": "Summary",
    "objective": "Summary",
    "highlights": "Key Achievements",
    "experience": "Experience",
    "education": "Education",
    "skills": "Skills",
    "certifications": "Certifications",
    "projects": "Projects",
    "awards": "Awards",
    "publications": "Publications",
    "volunteer": "Volunteer Experience",
    "affiliations": "Affiliations",
    "languages": "Languages",
    "interests": "Interests",
}

WEAK_OPENERS = re.compile(
    r"^(?:responsible for|duties (?:included|include)|worked on|helped|assisted|"
    r"participated in|involved in|tasked with|handled|in charge of|exposure to)\b",
    re.IGNORECASE,
)
FIRST_PERSON = re.compile(r"\b(?:I|me|my|myself)\b")
CLICHES = [
    "results-driven",
    "results driven",
    "results-oriented",
    "detail-oriented",
    "detail oriented",
    "team player",
    "self-starter",
    "go-getter",
    "hard worker",
    "hard-working",
    "hardworking",
    "dynamic",
    "synergy",
    "think outside the box",
    "proven track record",
    "excellent communication skills",
    "strong work ethic",
    "seeking a challenging",
    "leverage my skills",
    "best of breed",
    "passionate about",
]
PERSONAL = re.compile(
    r"\b(?:date of birth|d\.?o\.?b\.?|birth ?date|marital status|social security|ssn|"
    r"religion|gender:|age:\s*\d)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d")


def _wordset(text: str) -> frozenset[str]:
    return frozenset(text.split())


PAST_IRREGULAR = _wordset(
    """
    led built ran won grew drove made took began wrote cut saw became oversaw brought
    sold taught held kept met found gave got chose spoke told thought understood rebuilt
    rewrote spun stood went did undertook withdrew sought bought fought caught paid laid
    sent spent lent struck shook rode rose drew flew knew threw wore swore
    """
)
PRESENT_BASE = _wordset(
    """
    manage lead build drive develop own oversee partner create design deliver support
    coordinate prepare analyze analyse maintain implement conduct ensure provide perform
    serve collaborate monitor review run handle write track execute train mentor
    negotiate establish identify improve increase reduce streamline administer advise
    assist facilitate plan report research launch guide direct supervise approve
    reconcile process generate define translate present model communicate organize
    organise recruit hire coach evaluate assess audit resolve respond schedule budget
    allocate architect automate optimize optimise scale spearhead champion influence
    teach sell grow win make take begin hold keep meet find give get speak tell operate
    produce publish represent secure source test validate verify
    """
)


def audit(
    doc: ExtractedDocument, parsed: ParsedResume, *, today: date | None = None
) -> list[Finding]:
    today = today or date.today()
    blocks = {b.index: b for b in doc.blocks}
    findings: list[Finding] = []
    checks: list[Callable[[], Iterable[Finding]]] = [
        lambda: _layout(doc, parsed, blocks),
        lambda: _headings(parsed, blocks),
        lambda: _file_name(doc, parsed),
        lambda: _contact(parsed, blocks),
        lambda: _date_checks(parsed, blocks, today),
        lambda: _consistency(doc, parsed, blocks),
        lambda: _content(doc, parsed, blocks, today),
        lambda: _length(doc, parsed),
    ]
    for check in checks:
        findings.extend(check())
    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    return findings


# Problems in the words and facts themselves. They come along into the cards
# and need fixing there. Every other rule is about the document: layout,
# formatting consistency, how software reads it, or the file.
CARD_RULES = frozenset(
    {
        "consistency.figures",
        "consistency.tense",
        "content.cliches",
        "content.duplicates",
        "content.first_person",
        "content.long_bullets",
        "content.no_bullets",
        "content.no_numbers",
        "content.objective",
        "content.old_detail",
        "content.personal_info",
        "content.repeated_openers",
        "content.skill_spelling",
        "content.weak_openers",
        "dates.end_before_start",
        "dates.future",
        "dates.gap",
        "dates.many_current",
        "dates.missing",
        "dates.outside_tenure",
        "dates.overlap",
        "dates.titles_share_tenure",
        "dates.undated_engagements",
        "dates.year_only",
    }
)


def _finding(
    rule: str,
    severity: Severity,
    category: Category,
    title: str,
    detail: str,
    where: Iterable[Block] = (),
) -> Finding:
    return Finding(
        rule=rule,
        severity=severity,
        category=category,
        about="cards" if rule in CARD_RULES else "document",
        title=title,
        detail=detail,
        locations=[_loc(b) for b in where],
    )


def _loc(block: Block) -> Location:
    text = block.text.replace("\t", "  ")
    return Location(block=block.index, excerpt=text if len(text) <= 100 else text[:97] + "…")


def _quote(block: Block, sentence: str) -> Location:
    """Points at one sentence inside a longer line."""
    text = sentence if len(sentence) <= 160 else sentence[:157] + "…"
    return Location(block=block.index, excerpt=text)


def _role_label(role: Role) -> str:
    parts = [p for p in (role.title, role.organization) if p]
    return ", ".join(parts) if parts else role.header_text.split("\n")[0]


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# --- Layout and parsing -------------------------------------------------------------


def _layout(
    doc: ExtractedDocument, parsed: ParsedResume, blocks: dict[int, Block]
) -> Iterable[Finding]:
    facts = doc.facts
    if not doc.blocks:
        yield _finding(
            "ats.no_text",
            "fix",
            "ats",
            "No readable text",
            "This file has no text layer; it's probably a scan or an image. Applicant "
            "tracking systems will read it as blank. Export it from Word or Google Docs "
            "instead of scanning or printing to an image.",
        )
        return
    if not facts.has_text_layer:
        yield _finding(
            "ats.no_text",
            "fix",
            "ats",
            "No readable text",
            "This file has no text layer; it's a scan or an image. Plytos read the words "
            "from the picture for your cards, but applicant tracking systems will read it "
            "as blank. Export it from Word or Google Docs instead of scanning or printing "
            "to an image.",
        )
    else:
        for page in facts.scanned_pages:
            read = [b for b in doc.blocks if b.where == "image" and b.page == page]
            yield _finding(
                "ats.scanned_page",
                "fix",
                "ats",
                f"Page {page} is a scan",
                f"Page {page} has no text layer; it's a picture of a page. Applicant "
                "tracking systems skip it, with everything on it. "
                + ("Plytos read its words for your cards. " if read else "")
                + "Export the whole resume from Word or Google Docs.",
                [read[0]] if read else [],
            )

    marked = [b for b in doc.blocks if is_marking(b, facts.markings)]
    if facts.markings or marked:
        label = facts.markings[0] if facts.markings else marked[0].text
        yield _finding(
            "file.classification_marking",
            "fix",
            "file",
            "An employer's confidentiality marking is on the page",
            f'The page header carries "{label}", a sensitivity marking stamped by an '
            "organization's labelling tool. It tells every reader this file came off an "
            "employer's managed system and is marked confidential. Save a clean copy from "
            "a personal account, without the label, before sending it anywhere.",
            marked,
        )

    marked_ids = {b.index for b in marked}
    contact_ids = set(parsed.contact.blocks)
    in_header = [
        b for b in doc.blocks if b.where in ("header", "footer") and b.index not in marked_ids
    ]
    boxed_contact = [b for b in doc.blocks if b.where == "text_box" and b.index in contact_ids]
    body_contact = [
        b
        for b in doc.blocks
        if b.where in ("body", "table") and (EMAIL.search(b.text) or PHONE.search(b.text))
    ]
    if not body_contact and any(EMAIL.search(b.text) or PHONE.search(b.text) for b in in_header):
        yield _finding(
            "ats.contact_in_header",
            "fix",
            "ats",
            "Contact details are in the page header",
            "Your name, email or phone sit in Word's page header. Many applicant tracking "
            "systems skip headers and footers, so your application can arrive with no way "
            "to reach you. Move them into the first lines of the page body.",
            in_header,
        )
    if not body_contact and boxed_contact:
        yield _finding(
            "ats.contact_in_text_boxes",
            "fix",
            "ats",
            "Your name and contact details are in text boxes",
            "Many applicant tracking systems skip text boxes, so your application can "
            "arrive with no name, email or phone. Put them as plain lines at the top of "
            "the page.",
            boxed_contact,
        )

    boxed = [
        b
        for b in doc.blocks
        if b.where == "text_box" and b.index not in marked_ids and b.index not in contact_ids
    ]
    if boxed:
        yield _finding(
            "ats.text_boxes",
            "fix",
            "ats",
            f"{_plural(len(boxed), 'line')} in text boxes",
            "Text boxes are often skipped or read out of order by applicant tracking "
            "systems. Put this text in the normal flow of the page.",
            boxed,
        )

    body = [b for b in doc.blocks if b.where in ("body", "table") and b.font_sizes]
    if body:
        size = body_size(body)
        if size < 10:
            yield _finding(
                "layout.small_text",
                "improve",
                "layout",
                f"Body text is {size:g} pt",
                f"Most of the resume is set in {size:g} pt, which is hard to read, "
                "especially on a phone, where many recruiters first open it. Use 10 to "
                "12 pt and cut words rather than shrinking the type.",
            )
    tiny = [
        b
        for b in doc.blocks
        if b.font_sizes and max(b.font_sizes) < 8 and b.index not in marked_ids
    ]
    if tiny:
        yield _finding(
            "layout.tiny_text",
            "improve",
            "layout",
            f"{_plural(len(tiny), 'line')} under 8 pt",
            "Text this small is hard to read and can be dropped when a file is converted. "
            "Your contact details especially should be easy to read.",
            tiny[:6],
        )

    if facts.tables:
        share = facts.table_words / max(1, facts.word_count)
        tabled = [b for b in doc.blocks if b.where == "table"]
        yield _finding(
            "ats.tables",
            "improve" if share >= 0.05 else "note",
            "ats",
            f"{_plural(facts.tables, 'table')} holding {facts.table_words} words",
            "Some applicant tracking systems read tables row by row and run neighbouring "
            "cells together. Use plain lines with commas or tabs instead.",
            tabled[:6],
        )

    if facts.columns > 1:
        yield _finding(
            "ats.columns",
            "improve",
            "ats",
            "Multi-column layout",
            "Two-column layouts are often read straight across the page, mixing the "
            "columns line by line. A single column parses reliably.",
        )

    width = facts.text_width_in or 6.5
    big = [p for p in facts.pictures if p.width_in >= width * 0.6 and p.height_in >= 1.0]
    for picture in big:
        after = blocks.get(picture.after_block) if picture.after_block is not None else None
        place = f' right after "{_loc(after).excerpt}"' if after else ""
        if picture.lines_read:
            detail = (
                f"An image as wide as the text sits{place}, and it holds "
                f"{_plural(picture.lines_read, 'line')} of text. Plytos read them for your "
                "cards, but applicant tracking systems and screen readers can't read a word "
                "of it, and it won't match any search. Retype its content as text."
            )
        else:
            detail = (
                f"An image as wide as the text sits{place}. If it shows text (a screenshot "
                "of bullets, say), applicant tracking systems and screen readers can't read "
                "a word of it, and it won't match any search. Retype its content as text."
            )
        yield _finding(
            "ats.large_image",
            "fix",
            "ats",
            f"A {picture.width_in:g} × {picture.height_in:g} inch image in the page body",
            detail,
            [after] if after else [],
        )
    small = facts.images - len(big)
    if small > 0:
        yield _finding(
            "ats.images",
            "note",
            "ats",
            f"{_plural(small, 'image')} or icon{'s' if small != 1 else ''}",
            "Images and icons are invisible to applicant tracking systems, so anything "
            "they carry (such as phone or email icons, skill bars or a logo) is lost. If "
            "one is a photo, remove it: US employers generally avoid resumes with photos.",
        )

    if not parsed.roles:
        yield _finding(
            "ats.no_experience",
            "fix",
            "ats",
            "No work experience found",
            "We couldn't find an experience section with dated roles. Use a heading such "
            "as Experience, and give each role a title, employer and dates.",
        )
    unclear = [r for r in parsed.roles if not r.organization or (not r.title and r.client is None)]
    if unclear:
        yield _finding(
            "ats.unclear_roles",
            "improve",
            "ats",
            f"{_plural(len(unclear), 'role')} missing a title or employer",
            "We couldn't find both a job title and an employer in these lines, and an "
            "applicant tracking system may not either. Give every role both, in the same "
            'order, for example "Title, Employer".',
            [blocks[r.header_blocks[0]] for r in unclear if r.header_blocks],
        )


def _headings(parsed: ParsedResume, blocks: dict[int, Block]) -> Iterable[Finding]:
    odd = [s for s in parsed.sections if s.heading is not None and not s.heading_recognized]
    if odd:
        suggestions = []
        for s in odd:
            better = _SUGGESTED_HEADING.get(s.kind)
            if better:
                suggestions.append(f'"{s.heading}" → "{better}"')
        detail = (
            "Applicant tracking systems file your content by standard section names. "
            "Unfamiliar headings can leave it unfiled."
        )
        if suggestions:
            detail += " Try: " + "; ".join(suggestions) + "."
        yield _finding(
            "ats.nonstandard_headings",
            "improve",
            "ats",
            f"{_plural(len(odd), 'heading')} an ATS may not recognize",
            detail,
            [blocks[s.heading_block] for s in odd if s.heading_block is not None],
        )
    for section in parsed.sections:
        if section.holds == "summary" and section.heading_block is not None:
            yield _finding(
                "ats.misfiled_summary",
                "fix",
                "ats",
                f'Your summary sits under an "{section.heading}" heading',
                f'The paragraph under the first "{section.heading}" heading is a summary, not '
                "a job. An applicant tracking system will try to read it as a role with no "
                "title, employer or dates. Retitle it Summary.",
                [blocks[section.heading_block], *(blocks[i] for i in section.blocks[:1])],
            )
    kinds = {s.holds or s.kind for s in parsed.sections}
    if parsed.roles and "skills" not in kinds:
        yield _finding(
            "ats.no_skills",
            "improve",
            "ats",
            "No skills section",
            "Recruiters search applicant tracking systems by skill. A short Skills section "
            "with the tools and methods you use makes you findable.",
        )
    if "education" not in kinds:
        yield _finding(
            "ats.no_education",
            "note",
            "ats",
            "No education section",
            "Many postings filter on education. If you have a degree or relevant training, "
            "add an Education section.",
        )
    if "objective" in kinds:
        section = next(s for s in parsed.sections if s.kind == "objective")
        yield _finding(
            "content.objective",
            "improve",
            "content",
            "Objective instead of a summary",
            "An objective says what you want; a summary says what you offer. Replace it "
            "with two or three lines on the work you do best and the results behind it.",
            [blocks[section.heading_block]] if section.heading_block is not None else [],
        )
    references = [i for i, why in parsed.skipped.items() if why == "references" and i in blocks]
    if "references" in kinds or references:
        heading = next((s for s in parsed.sections if s.kind == "references"), None)
        line = heading.heading_block if heading is not None else None
        line = line if line is not None else (references[0] if references else None)
        yield _finding(
            "content.references",
            "improve",
            "content",
            '"References available upon request"',
            "Employers assume this, so the line only takes space. Remove it and keep your "
            "references ready separately.",
            [blocks[line]] if line is not None else [],
        )
    # Real heading lines only: not "Certifications: CPA" or the references line.
    titled = [
        s
        for s in parsed.sections
        if s.heading
        and s.heading_block is not None
        and s.kind != "references"
        and blocks[s.heading_block].text.strip().rstrip(":") == s.heading.rstrip(":")
    ]
    cases = Counter(_case(s.heading or "") for s in titled)
    if len(cases) > 1:
        examples = ", ".join(f'"{s.heading}"' for s in titled)
        yield _finding(
            "consistency.heading_case",
            "improve",
            "consistency",
            "Headings use different capitalization",
            f"Your headings mix styles: {examples}. Pick one style, such as all capitals, "
            "for every heading.",
            [blocks[s.heading_block] for s in titled if s.heading_block is not None],
        )


def _case(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return "upper"
    words = [
        w
        for w in re.findall(r"[A-Za-z]+", text)
        if w.lower() not in {"and", "of", "the", "for", "in"}
    ]
    if words and all(w[0].isupper() for w in words):
        return "title"
    return "sentence"


def _file_name(doc: ExtractedDocument, parsed: ParsedResume) -> Iterable[Finding]:
    stem = PurePath(doc.facts.filename).stem
    tokens = [t for t in re.split(r"[\s_\-.()]+", stem) if t]
    name_parts = {p.lower() for p in (parsed.contact.name or "").split()}
    generic = {"resume", "résumé", "cv", "curriculum", "vitae", "updated", "new", "copy", "draft"}
    versions = [t for t in tokens if re.fullmatch(r"(?i)final|v\d+|ver\d+|\d+|copy|draft", t)]
    extra = [
        t
        for t in tokens
        if t.lower() not in name_parts
        and t.lower() not in generic
        and t not in versions
        and not re.fullmatch(r"(?:19|20)\d{2}", t)
    ]
    if extra:
        tag = " ".join(extra)
        yield _finding(
            "file.tailored_name",
            "note",
            "file",
            f'The file name includes "{tag}"',
            f'"{doc.facts.filename}" carries "{tag}". If that marks the employer or posting '
            "you tailored it for, anyone else you send it to will see that. In Plytos a "
            "tailored version is a variant of the same cards, so the file you send can be "
            'named for you alone, such as "Firstname Lastname Resume.pdf".',
        )
    if versions:
        yield _finding(
            "file.version_name",
            "note",
            "file",
            "The file name shows a version",
            f'"{doc.facts.filename}" includes "{" ".join(versions)}". Recruiters see the file '
            "name; Plytos keeps the version history so the name doesn't have to.",
        )
    if parsed.contact.name and not name_parts & {t.lower() for t in tokens}:
        yield _finding(
            "file.no_name",
            "note",
            "file",
            "The file name doesn't include your name",
            "Recruiters save hundreds of resumes. Put your name in the file name so yours is "
            "easy to find again.",
        )


# --- Contact --------------------------------------------------------------------


def _contact(parsed: ParsedResume, blocks: dict[int, Block]) -> Iterable[Finding]:
    contact = parsed.contact
    where = [blocks[i] for i in contact.blocks[:3] if i in blocks]
    if not contact.name:
        yield _finding(
            "contact.no_name",
            "improve",
            "contact",
            "Name not found at the top",
            "Start the page with your name on its own line, in the page body.",
            where,
        )
    if not contact.emails:
        yield _finding(
            "contact.no_email",
            "fix",
            "contact",
            "No email address",
            "Add an email address near your name so recruiters can reach you.",
            where,
        )
    elif len(contact.emails) > 1:
        yield _finding(
            "contact.many_emails",
            "note",
            "contact",
            f"{len(contact.emails)} email addresses",
            "Give one email address so it's clear where to reply: "
            + ", ".join(contact.emails)
            + ".",
            where,
        )
    if not contact.phones:
        yield _finding(
            "contact.no_phone",
            "improve",
            "contact",
            "No phone number",
            "Most recruiters call first. Add a mobile number.",
            where,
        )
    odd_phones = [p for p in contact.phones if re.search(r"\s[-.]\s|\s-|-\s", p)]
    if odd_phones:
        phone_blocks = [
            blocks[i] for i in contact.blocks if any(p in blocks[i].text for p in odd_phones)
        ]
        yield _finding(
            "contact.phone_format",
            "note",
            "contact",
            "Phone number spacing",
            f'"{odd_phones[0]}" has spaces around the dash. Some systems and phones won\'t '
            'recognize it as a number to tap or store. Write it as "(303) 555-0100".',
            phone_blocks,
        )
    if not any("linkedin.com" in link.lower() for link in contact.links):
        yield _finding(
            "contact.no_linkedin",
            "note",
            "contact",
            "No LinkedIn link",
            "Recruiters usually check LinkedIn. Add your profile URL, and make sure its "
            "titles and dates match this resume.",
        )
    if contact.street_address:
        yield _finding(
            "contact.street_address",
            "improve",
            "contact",
            "Full street address",
            "A street address isn't needed and exposes where you live to everyone the "
            "resume reaches. City and state are enough.",
            [blocks[i] for i in contact.blocks if i in blocks and STREET.search(blocks[i].text)],
        )
    if not contact.location:
        yield _finding(
            "contact.no_location",
            "note",
            "contact",
            "No city and state",
            'Many searches filter by location. Add your city and state, or "Remote".',
            where,
        )


# --- Dates ------------------------------------------------------------------------


def _months(found: DateRange, today: date) -> tuple[int, int] | None:
    if found.start is None:
        return None
    start = found.start.ordinal()
    if found.current:
        end = today.year * 12 + today.month - 1
    elif found.end is not None:
        end = found.end.ordinal(end=True)
    else:
        return None
    return start, end


def _ym(ordinal: int) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[ordinal % 12]} {ordinal // 12}"


def _header_blocks(roles: Iterable[Role], blocks: dict[int, Block]) -> list[Block]:
    return [blocks[r.header_blocks[0]] for r in roles if r.header_blocks]


def _date_checks(parsed: ParsedResume, blocks: dict[int, Block], today: date) -> Iterable[Finding]:
    roles = parsed.roles
    # Titles inside an employer whose tenure is written are dated by that tenure.
    dated_by_tenure = {
        ref
        for e in parsed.employments
        if e.dates is not None and e.tenure_written
        for ref in e.role_refs
    }
    undated = [
        r
        for r in roles
        if r.dates is None and r.parent_ref is None and r.ref not in dated_by_tenure
    ]
    shared: dict[str, list[Role]] = defaultdict(list)
    for r in roles:
        if r.dates is None and r.parent_ref is None and r.ref in dated_by_tenure:
            shared[r.employment_ref or ""].append(r)
    employments = {e.ref: e for e in parsed.employments}
    for ref, titles in shared.items():
        employment = employments.get(ref)
        if employment is None or employment.dates is None or len(employment.role_refs) < 2:
            continue  # One title under a dated employer: the tenure is its dates.
        yield _finding(
            "dates.titles_share_tenure",
            "note",
            "dates",
            f"{_plural(len(titles), 'title')} at {employment.organization or 'one employer'} "
            "share one date range",
            f"Your time at {employment.organization or 'this employer'} is dated "
            f"({employment.dates.raw}), so this is fine as it is. Adding when you moved into "
            "each title shows the progression at a glance.",
            _header_blocks(titles, blocks),
        )
    by_ref = {r.ref: r for r in roles}
    engagements: dict[str, list[Role]] = defaultdict(list)
    for r in roles:
        if r.parent_ref is not None and r.dates is None:
            engagements[r.parent_ref].append(r)
    for parent_ref, clients in engagements.items():
        parent = by_ref[parent_ref]
        names = ", ".join(c.client or "?" for c in clients)
        yield _finding(
            "dates.undated_engagements",
            "improve",
            "dates",
            f"{_plural(len(clients), 'engagement')} under {parent.organization} without dates",
            f"{names} sit under {_role_label(parent)} ({parent.dates.raw if parent.dates else ''}) "
            "with no dates of their own, so a reader can't tell how long each lasted or "
            "which came first. Give each engagement its own months.",
            _header_blocks(clients, blocks),
        )
    if undated:
        yield _finding(
            "dates.missing",
            "fix",
            "dates",
            f"{_plural(len(undated), 'role')} without dates",
            "Every role needs a start and end date. Missing dates read as something hidden "
            "and many applicant tracking systems reject them.",
            _header_blocks(undated, blocks),
        )
    dated = [r for r in roles if r.dates is not None]
    year_only = [
        r
        for r in dated
        if r.dates is not None and ("YYYY" in (r.dates.start_format, r.dates.end_format))
    ]
    if year_only:
        yield _finding(
            "dates.year_only",
            "improve",
            "dates",
            f"{_plural(len(year_only), 'role')} with years but no months",
            'Year-only dates make a recruiter guess: "2016 to 2018" could be just over a '
            "year or nearly three. Use month and year for every role.",
            _header_blocks(year_only, blocks),
        )

    spans: list[tuple[Role, int, int]] = []
    current_year_month = today.year * 12 + today.month - 1
    for role in dated:
        assert role.dates is not None
        span = _months(role.dates, today)
        if span is None:
            continue
        start, end = span
        if end < start:
            yield _finding(
                "dates.end_before_start",
                "fix",
                "dates",
                "A role ends before it starts",
                f'{_role_label(role)}: "{role.dates.raw}". Check the order of the dates.',
                _header_blocks([role], blocks),
            )
            continue
        if start > current_year_month or (
            not role.dates.current
            and role.dates.end
            and role.dates.end.ordinal() > current_year_month
        ):
            yield _finding(
                "dates.future",
                "fix",
                "dates",
                "A date is in the future",
                f'{_role_label(role)}: "{role.dates.raw}".',
                _header_blocks([role], blocks),
            )
        spans.append((role, start, end))

    current = [r for r in dated if r.dates is not None and r.dates.current]
    if len(current) > 1:
        yield _finding(
            "dates.many_current",
            "note",
            "dates",
            f"{len(current)} roles marked as current",
            "If you hold these at the same time, that's fine; say which is your main job "
            "so a recruiter doesn't read it as an error.",
            _header_blocks(current, blocks),
        )

    work = [(r, s, e) for r, s, e in spans if r.section == "experience"]
    # Newest first means by end date (current roles first), then by start date.
    keys = [(e, s) for _, s, e in work]
    if any(later > earlier for earlier, later in itertools.pairwise(keys)):
        yield _finding(
            "dates.order",
            "improve",
            "dates",
            "Roles aren't newest first",
            "Recruiters expect the most recent role first and read down from there. List "
            "roles in reverse date order.",
            _header_blocks([r for r, _, _ in work], blocks),
        )

    overlaps: list[tuple[Role, Role, int]] = []
    for i, (a, a_start, a_end) in enumerate(spans):
        for b, b_start, b_end in spans[i + 1 :]:
            if a.employment_ref is not None and a.employment_ref == b.employment_ref:
                continue  # two titles at once at one employer is normal
            months = min(a_end, b_end) - max(a_start, b_start)
            if months >= 2:
                overlaps.append((a, b, months))
    for a, b, months in overlaps:
        yield _finding(
            "dates.overlap",
            "note",
            "dates",
            "Two roles overlap",
            f"{_role_label(a)} and {_role_label(b)} overlap by about {months} months. If "
            "one was part-time, contract, volunteer or a promotion, label it so it doesn't "
            "read as a mistake.",
            _header_blocks([a, b], blocks),
        )

    tenures = {
        e.ref: (e, _months(e.dates, today))
        for e in parsed.employments
        if e.dates is not None and e.tenure_written and e.header_blocks
    }
    for role, start, end in spans:
        employment, tenure = tenures.get(role.employment_ref or "", (None, None))
        if employment is None or tenure is None or employment.dates is None:
            continue
        if start < tenure[0] or end > tenure[1]:
            yield _finding(
                "dates.outside_tenure",
                "fix",
                "dates",
                "A title's dates fall outside the employer's",
                f"{_role_label(role)} ({role.dates.raw if role.dates else ''}) runs outside "
                f"your time at {employment.organization or 'that employer'} "
                f"({employment.dates.raw}). One of the two is likely a typo.",
                [
                    blocks[b]
                    for b in dict.fromkeys([*employment.header_blocks[:1], *role.header_blocks[:1]])
                ],
            )

    chronological = sorted(work, key=lambda item: item[1])
    reach: tuple[Role, int] | None = None
    for role, start, end in chronological:
        if reach is not None and start - reach[1] > 6:
            gap = start - reach[1] - 1
            yield _finding(
                "dates.gap",
                "note",
                "dates",
                f"A {gap}-month gap",
                f"Between {_role_label(reach[0])} (ended {_ym(reach[1])}) and "
                f"{_role_label(role)} (started {_ym(start)}). Gaps are common; a short line "
                "on what you did (study, caregiving, a contract) answers the question "
                "before it's asked.",
                _header_blocks([reach[0], role], blocks),
            )
        if reach is None or end > reach[1]:
            reach = (role, end)


# --- Consistency --------------------------------------------------------------


def _consistency(
    doc: ExtractedDocument, parsed: ParsedResume, blocks: dict[int, Block]
) -> Iterable[Finding]:
    roles = [r for r in parsed.roles if r.dates is not None]

    formats: dict[str, list[Role]] = defaultdict(list)
    for role in roles:
        assert role.dates is not None
        for fmt in {role.dates.start_format, role.dates.end_format}:
            if fmt:
                formats[fmt].append(role)
    if len(formats) > 1:
        examples = []
        for fmt, members in formats.items():
            sample = members[0].dates
            examples.append(f'{fmt} ("{sample.raw}")' if sample else fmt)
        mixed = [
            r.dates.raw
            for r in roles
            if r.dates and r.dates.end_format and r.dates.start_format != r.dates.end_format
        ]
        within = f' One range mixes two: "{mixed[0]}".' if mixed else ""
        yield _finding(
            "consistency.date_formats",
            "improve",
            "consistency",
            f"{len(formats)} date formats",
            "Dates are written several ways: " + "; ".join(examples) + "." + within + " Use "
            'one format, such as "Jan 2021 – Present", for every date.',
            _header_blocks(roles, blocks),
        )

    separators = Counter(r.dates.separator for r in roles if r.dates and r.dates.separator)
    if len(separators) > 1:
        shown = ", ".join(f'"{s}"' for s in separators)
        yield _finding(
            "consistency.date_separators",
            "improve",
            "consistency",
            "Date ranges use different separators",
            f"Ranges are joined with {shown}. Pick one, such as an en dash (–).",
            _header_blocks([r for r in roles if r.dates and r.dates.separator], blocks),
        )

    words = Counter(r.dates.current_word.lower() for r in roles if r.dates and r.dates.current_word)
    if len(words) > 1:
        yield _finding(
            "consistency.current_word",
            "note",
            "consistency",
            "Current roles are marked different ways",
            "You use " + " and ".join(f'"{w}"' for w in words) + ". Use one word.",
        )

    bullets = [blocks[b.block] for r in parsed.roles for b in r.bullets]
    every_bullet = [b for b in doc.blocks if b.is_bullet]
    glyphs = Counter(b.bullet_char for b in every_bullet if b.bullet_char)
    if len(glyphs) > 1:
        shown = ", ".join(f'"{g}" ({n})' for g, n in glyphs.most_common())
        minority = {g for g, _ in glyphs.most_common()[1:]}
        yield _finding(
            "consistency.bullets",
            "improve",
            "consistency",
            f"{len(glyphs)} bullet styles",
            f"Bullets are drawn with {shown}. Use one bullet style throughout, set as a "
            "list rather than typed characters.",
            [b for b in every_bullet if b.bullet_char in minority][:8],
        )
    bold = [b for b in every_bullet if b.bold]
    if bold and len(bold) < len(every_bullet):
        yield _finding(
            "consistency.bullet_bold",
            "improve",
            "consistency",
            f"{_plural(len(bold), 'bullet')} in bold",
            f"{len(bold)} of {len(every_bullet)} bullets are bold. Bold reads as a heading; "
            "keep bullets in regular weight so the headings stand out.",
            bold[:6],
        )
    typed = [
        b
        for b in bullets
        if b.bullet_char and b.style and "List" not in b.style and b.bullet_char in "-*–—"
    ]
    if typed and doc.facts.format == "docx":
        yield _finding(
            "consistency.typed_bullets",
            "note",
            "consistency",
            f"{_plural(len(typed), 'bullet')} typed by hand",
            "Hyphens or asterisks typed at the start of a line can be read as part of the "
            "text. Use Word's bullet list instead.",
            typed[:6],
        )

    orders = {
        r.title_first for r in parsed.roles if r.title_first is not None and r.confidence == "high"
    }
    if len(orders) > 1:
        yield _finding(
            "consistency.role_order",
            "improve",
            "consistency",
            "Roles put title and employer in different orders",
            "Some roles lead with the job title and others with the employer. Use the same "
            "order for every role so the eye (and the ATS) knows where to look.",
            _header_blocks([r for r in parsed.roles if r.title_first is not None], blocks),
        )

    ended = [b for b in bullets if b.text.rstrip().endswith(".")]
    open_ended = [b for b in bullets if not b.text.rstrip().endswith((".", "!", "?"))]
    if ended and open_ended:
        minority_blocks = ended if len(ended) < len(open_ended) else open_ended
        yield _finding(
            "consistency.end_punctuation",
            "improve",
            "consistency",
            "Some bullets end with a period and some don't",
            f"{len(ended)} bullets end with a period and {len(open_ended)} don't. Either is "
            "fine; mixing them looks unfinished.",
            minority_blocks[:6],
        )

    yield from _font_consistency(doc, parsed, blocks, bullets)

    if doc.facts.format != "pdf":
        doubled = [b for b in doc.blocks if re.search(r"\S {2,}\S", b.text)]
        if doubled:
            yield _finding(
                "consistency.spacing",
                "note",
                "consistency",
                f"Double spaces on {_plural(len(doubled), 'line')}",
                "Extra spaces used for alignment break when the file is read or reflowed. "
                "Use tabs or a right-aligned tab stop.",
                doubled[:6],
            )

    by_ref = {r.ref: r for r in parsed.roles}
    tense_slips: list[Location] = []
    for role in parsed.roles:
        dates = role.dates or (by_ref[role.parent_ref].dates if role.parent_ref else None)
        if dates is None or dates.current:
            continue
        lines = [(blocks[b.block], b.text) for b in role.bullets]
        lines += [(blocks[i], blocks[i].text) for i in role.description_blocks]
        for block, text in lines:
            for sentence in sentences(text):
                if _present_clause(sentence):
                    tense_slips.append(_quote(block, sentence))
    if tense_slips:
        finding = _finding(
            "consistency.tense",
            "fix",
            "consistency",
            f"{_plural(len(tense_slips), 'line')} in present tense for a past role",
            'Past roles should read in the past tense ("Managed", not "Manage"); the '
            "present tense makes it look like you still do this work.",
        )
        finding.locations = tense_slips
        yield finding

    yield from _figure_conflicts(parsed, blocks)


_STOP = _wordset(
    "the and for with from that this into over than were was our their its across within "
    "such more most an a of to in on by as at or is are be"
)
_FIGURE = re.compile(r"[~≈]?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|[kKmMbB]\b|x\b)")


def _figures(text: str) -> list[tuple[str, set[str]]]:
    """Each figure in a text with the words around it, to match claims across sections."""
    words = re.findall(r"[~≈$]?[\w%.,/+]+", text)
    out: list[tuple[str, set[str]]] = []
    for i, word in enumerate(words):
        m = _FIGURE.fullmatch(word.rstrip(".,")) or (
            _FIGURE.fullmatch(word + (words[i + 1] if i + 1 < len(words) else ""))
        )
        if not m:
            continue
        window = words[max(0, i - 6) : i] + words[i + 1 : i + 7]
        context = {
            w.lower().strip(".,")
            for w in window
            if len(w) > 3 and w.lower() not in _STOP and not any(c.isdigit() for c in w)
        }
        out.append((word.rstrip(".,").lstrip("~≈"), context))
    return out


def _figure_conflicts(parsed: ParsedResume, blocks: dict[int, Block]) -> Iterable[Finding]:
    """The same result quoted with different numbers in two places."""
    claims: list[tuple[int, str, str, set[str]]] = []  # block, sentence, figure, context
    summary_like = [e.blocks[0] for e in parsed.highlights] + parsed.summary_blocks
    for i in summary_like:
        for sentence in sentences(blocks[i].text):
            for figure, context in _figures(sentence):
                claims.append((i, sentence, figure, context))
    role_claims: list[tuple[int, str, str, set[str]]] = []
    for role in parsed.roles:
        for i in [b.block for b in role.bullets] + role.description_blocks:
            for sentence in sentences(blocks[i].text):
                for figure, context in _figures(sentence):
                    role_claims.append((i, sentence, figure, context))
    reported: set[tuple[int, int]] = set()
    for block, sentence, figure, context in claims:
        for role_block, role_sentence, role_figure, role_context in role_claims:
            shared = context & role_context
            same_unit = figure.endswith("%") == role_figure.endswith("%")
            if len(shared) >= 2 and same_unit and _value(figure) != _value(role_figure):
                if (block, role_block) in reported:
                    continue
                reported.add((block, role_block))
                topic = ", ".join(sorted(shared)[:3])
                finding = _finding(
                    "consistency.figures",
                    "fix",
                    "consistency",
                    "The same result has two different numbers",
                    f"One place says {figure} and another says {role_figure} for what reads as "
                    f"the same result ({topic}). A reader who notices will doubt both. Pick "
                    "the number you can back up and use it everywhere.",
                )
                first = _quote(blocks[block], sentence)
                second = _quote(blocks[role_block], role_sentence)
                first.figure, second.figure = figure, role_figure
                finding.locations = [first, second]
                yield finding


def _value(figure: str) -> str:
    return re.sub(r"[^\d.%kmbx]", "", figure.lower())


def _present_clause(sentence: str) -> bool:
    """A sentence, or a clause after a comma or "and", that opens in the present tense."""
    words = re.findall(r"[A-Za-z\-]+", sentence)
    if not words:
        return False
    if _tense(words[0]) == "present" and not _is_title_phrase(words[:4]):
        return True
    if _tense(words[0]) == "past" and not re.search(r"\bto\s+[a-z]+\b", sentence):
        for m in re.finditer(r"(?:,\s*(?:and\s+)?|\band\s+)([a-z]+)\b", sentence):
            if m.group(1) in PRESENT_BASE and m.group(1) not in _NOUN_TOO:
                return True
    return False


# Words that are verbs in a resume line but nouns in "... and support staff".
_NOUN_TOO = _wordset("support model process plan report review research test design")


def _is_title_phrase(words: list[str]) -> bool:
    """ "Lead data analyst for ..." opens with a title, not a verb."""
    return words[0].lower() == "lead" and any(w.lower() in TITLE_WORDS for w in words[1:4])


def _font_consistency(
    doc: ExtractedDocument, parsed: ParsedResume, blocks: dict[int, Block], bullets: list[Block]
) -> Iterable[Finding]:
    if doc.facts.format == "text":
        return
    headers = _header_blocks([r for r in parsed.roles if r.parent_ref is None], blocks)
    clients = _header_blocks([r for r in parsed.roles if r.parent_ref is not None], blocks)
    groups = (("Bullets", bullets), ("Role headings", headers), ("Client headings", clients))
    for label, group in groups:
        fonts = Counter(f for b in group for f in b.font_names)
        sizes = Counter(s for b in group for s in b.font_sizes)
        if len(fonts) > 1 or len(sizes) > 1:
            common_font = fonts.most_common(1)[0][0] if fonts else None
            common_size = sizes.most_common(1)[0][0] if sizes else None
            odd = [
                b
                for b in group
                if any(f != common_font for f in b.font_names)
                or any(s != common_size for s in b.font_sizes)
            ]
            mix = ", ".join([f"{f}" for f in fonts] + [f"{s:g} pt" for s in sorted(sizes)])
            yield _finding(
                "consistency.fonts",
                "improve",
                "consistency",
                f"{label} use mixed fonts or sizes",
                f"{label} use {mix}. Usually this comes from pasting text in from another "
                "document. Set them all to one font and size.",
                odd[:6],
            )
    for label, group in (("role headings", headers), ("client headings", clients)):
        looks = Counter((b.bold, b.style) for b in group)
        if len(looks) > 1:
            usual = looks.most_common(1)[0][0]
            odd = [b for b in group if (b.bold, b.style) != usual]
            yield _finding(
                "consistency.header_style",
                "improve",
                "consistency",
                f"Some {label} are formatted differently",
                f"{_plural(len(odd), 'heading')} differ from the rest in bold or paragraph "
                "style. Format every heading at the same level the same way; it also keeps "
                "the outline intact when the file is parsed.",
                odd[:6],
            )
    families = list(doc.facts.fonts)
    if len(families) > 2:
        yield _finding(
            "consistency.font_count",
            "improve",
            "consistency",
            f"{len(families)} fonts",
            "The resume uses " + ", ".join(families) + ". One font (two at most, for "
            "headings) looks deliberate.",
        )


def _tense(text: str) -> str | None:
    first = re.sub(r"[^A-Za-z\-]", "", text.split()[0]).lower() if text.split() else ""
    if not first:
        return None
    if first in PAST_IRREGULAR or (first.endswith("ed") and len(first) > 4):
        return "past"
    if first in PRESENT_BASE:
        return "present"
    if first.endswith("es") and first[:-2] in PRESENT_BASE:
        return "present"
    if first.endswith("s") and first[:-1] in PRESENT_BASE:
        return "present"
    return None


# --- Content --------------------------------------------------------------------


def _content(
    doc: ExtractedDocument, parsed: ParsedResume, blocks: dict[int, Block], today: date
) -> Iterable[Finding]:
    bullets = [(r, blocks[b.block]) for r in parsed.roles for b in r.bullets]

    weak = [b for _, b in bullets if WEAK_OPENERS.match(b.text)]
    if weak:
        yield _finding(
            "content.weak_openers",
            "improve",
            "content",
            f"{_plural(len(weak), 'bullet')} describe duties, not results",
            '"Responsible for" and "Helped with" say what you were assigned. Lead with '
            "what you did and what changed because of it.",
            weak,
        )

    first_person = [b for b in doc.blocks if b.where != "header" and FIRST_PERSON.search(b.text)]
    if first_person:
        yield _finding(
            "content.first_person",
            "improve",
            "content",
            "Written in the first person",
            'Resumes drop "I" and "my". Start lines with the action instead.',
            first_person[:6],
        )

    without_numbers = [
        r
        for r in parsed.roles
        if (len(r.bullets) >= 2 and not any(_NUMBER.search(b.text) for b in r.bullets))
        or (
            not r.bullets
            and r.description is not None
            and len(r.description.split()) >= 25
            and not _NUMBER.search(r.description)
        )
    ]
    if without_numbers:
        yield _finding(
            "content.no_numbers",
            "improve",
            "content",
            f"{_plural(len(without_numbers), 'role')} with no numbers",
            "Numbers (money, time saved, team size, volume) make results credible at a "
            "glance. Each of these roles has none. Plytos will ask for the evidence behind "
            "each card when you review it.",
            _header_blocks(without_numbers, blocks),
        )

    prose = [r for r in parsed.roles if r.description and not r.bullets]
    if prose:
        longest = max(len((r.description or "").split()) for r in prose)
        yield _finding(
            "content.paragraphs",
            "improve",
            "content",
            f"{_plural(len(prose), 'role')} written as paragraphs",
            "Recruiters skim. Results buried in a paragraph (the longest here runs "
            f"{longest} words) get missed. Break each into bullets that start with what you "
            "did and end with what changed. Plytos proposes one card per sentence to make "
            "that easier.",
            [blocks[r.description_blocks[0]] for r in prose if r.description_blocks][:8],
        )

    long = [b for _, b in bullets if len(b.text.split()) > 40]
    if long:
        yield _finding(
            "content.long_bullets",
            "improve",
            "content",
            f"{_plural(len(long), 'bullet')} over 40 words",
            "Long bullets get skimmed past. Keep each to one or two lines: the action, "
            "the result, the number.",
            long,
        )

    crowded = [r for r in parsed.roles if len(r.bullets) > 8]
    if crowded:
        yield _finding(
            "content.many_bullets",
            "improve",
            "content",
            f"{_plural(len(crowded), 'role')} with more than 8 bullets",
            "Recruiters read the first few. Keep the strongest five or six and move the "
            "rest into cards you can swap in for postings that need them.",
            _header_blocks(crowded, blocks),
        )

    parents = {r.parent_ref for r in parsed.roles if r.parent_ref}
    bare = [r for r in parsed.roles if not r.bullets and not r.description and r.ref not in parents]
    if bare:
        yield _finding(
            "content.no_bullets",
            "improve",
            "content",
            f"{_plural(len(bare), 'role')} with no description",
            "Add at least one line on what you achieved in each role.",
            _header_blocks(bare, blocks),
        )

    seen: dict[str, tuple[Block, str]] = {}
    duplicates: list[Location] = []
    skip = set(parsed.contact.blocks) | {
        s.heading_block for s in parsed.sections if s.heading_block is not None
    }
    for b in doc.blocks:
        if b.index in skip or b.where in ("header", "footer"):
            continue
        for sentence in sentences(b.text):
            key = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
            if len(key.split()) < 6:
                continue
            if key in seen and seen[key][0] is not b:
                first = _quote(*seen[key])
                if first not in duplicates:
                    duplicates.append(first)
                duplicates.append(_quote(b, sentence))
            else:
                seen.setdefault(key, (b, sentence))
    if duplicates:
        finding = _finding(
            "content.duplicates",
            "improve",
            "content",
            "The same sentence appears more than once",
            "Repeated lines look like copy and paste. Keep each in the one place it "
            "belongs, or reword it to show what was different.",
        )
        finding.locations = duplicates
        yield finding

    openers = Counter(b.text.split()[0].lower().strip(",.") for _, b in bullets if b.text.split())
    repeated = [(w, n) for w, n in openers.most_common() if n >= 3 and _tense(w) is not None]
    if repeated:
        yield _finding(
            "content.repeated_openers",
            "improve",
            "content",
            "Several bullets start with the same word",
            "; ".join(f'"{w.capitalize()}" starts {n} bullets' for w, n in repeated)
            + ". Varying the verb makes each line read as its own result.",
            [
                b
                for _, b in bullets
                if b.text.split()
                and b.text.split()[0].lower().strip(",.") in {w for w, _ in repeated}
            ][:8],
        )

    cliche_hits: list[Block] = []
    found_phrases: list[str] = []
    for b in doc.blocks:
        low = b.text.lower()
        hits = [c for c in CLICHES if c in low]
        if hits:
            cliche_hits.append(b)
            found_phrases += [h for h in hits if h not in found_phrases]
    if cliche_hits:
        yield _finding(
            "content.cliches",
            "improve",
            "content",
            "Stock phrases",
            "Phrases like " + ", ".join(f'"{p}"' for p in found_phrases[:5]) + " appear on "
            "most resumes and recruiters skip them. Show the quality with a result instead.",
            cliche_hits[:6],
        )

    personal = [b for b in doc.blocks if PERSONAL.search(b.text)]
    if personal:
        yield _finding(
            "content.personal_info",
            "fix",
            "content",
            "Personal details US employers avoid",
            "Birth date, age, marital status, religion and similar details invite bias and "
            "most US employers prefer not to receive them. Remove them.",
            personal,
        )

    cutoff = today.year - 15
    old = [
        r
        for r in parsed.roles
        if r.dates is not None
        and not r.dates.current
        and r.dates.end is not None
        and r.dates.end.year < cutoff
        and (len(r.bullets) > 3 or len((r.description or "").split()) > 40)
    ]
    if old:
        yield _finding(
            "content.old_detail",
            "note",
            "content",
            f"Detail on {_plural(len(old), 'role')} over 15 years old",
            "Recruiters weight recent work. Trim older roles to a line or two; the detail "
            "stays on your cards for when it's relevant.",
            _header_blocks(old, blocks),
        )

    skill_blocks = [i for indexes in parsed.skill_blocks.values() for i in indexes]
    fixes = spelling_fixes([skill for items in parsed.skills.values() for skill in items])
    if fixes:
        yield _finding(
            "content.skill_spelling",
            "improve",
            "content",
            f"{_plural(len(fixes), 'skill')} spelled differently from the usual form",
            "Recruiters search skills by name, and a misspelling never matches. Written "
            "here as "
            + "; ".join(f'"{wrong}" (usually "{right}")' for wrong, right in fixes)
            + ".",
            [blocks[i] for i in skill_blocks[:2]],
        )


# --- Length -------------------------------------------------------------------------


def _length(doc: ExtractedDocument, parsed: ParsedResume) -> Iterable[Finding]:
    facts = doc.facts
    if facts.pages and facts.pages > 2:
        yield _finding(
            "length.pages",
            "improve",
            "length",
            f"{facts.pages} pages",
            "Two pages is the usual limit in the US, even for senior roles. Cut older "
            "detail first.",
        )
    elif facts.pages is None and facts.word_count > 1100:
        yield _finding(
            "length.words",
            "improve",
            "length",
            f"About {facts.word_count} words",
            "That's likely more than two pages. Cut older detail first.",
        )
    if 0 < facts.word_count < 200:
        yield _finding(
            "length.short",
            "note",
            "length",
            f"Only {facts.word_count} words",
            "This is short for a professional resume. Each role can carry two to five results.",
        )
    if parsed.summary and len(parsed.summary.split()) > 90:
        yield _finding(
            "length.summary",
            "improve",
            "length",
            f"Summary runs {len(parsed.summary.split())} words",
            "Keep the summary to two or three lines (about 50 words): who you are, what "
            "you're best at, and one result.",
        )
