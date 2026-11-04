"""Splits a resume's lines into contact details, sections, roles and entries."""

import re

from plytos_api.imports.dates import find_range, strip_range
from plytos_api.imports.model import (
    Block,
    Bullet,
    Contact,
    Entry,
    ExtractedDocument,
    ParsedResume,
    Role,
    Section,
    SectionKind,
    SkipReason,
)

# Standard headings an applicant tracking system expects, by what they hold.
HEADINGS: dict[str, SectionKind] = {
    "contact": "contact",
    "contact information": "contact",
    "contact info": "contact",
    "summary": "summary",
    "professional summary": "summary",
    "career summary": "summary",
    "executive summary": "summary",
    "profile": "summary",
    "professional profile": "summary",
    "career profile": "summary",
    "about": "summary",
    "about me": "summary",
    "overview": "summary",
    "summary of qualifications": "summary",
    "qualifications summary": "summary",
    "qualifications": "summary",
    "objective": "objective",
    "career objective": "objective",
    "professional objective": "objective",
    "highlights": "highlights",
    "career highlights": "highlights",
    "key achievements": "highlights",
    "achievements": "highlights",
    "key accomplishments": "highlights",
    "accomplishments": "highlights",
    "selected accomplishments": "highlights",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "relevant experience": "experience",
    "employment": "experience",
    "employment history": "experience",
    "work history": "experience",
    "career history": "experience",
    "professional history": "experience",
    "career experience": "experience",
    "education": "education",
    "academic background": "education",
    "education and training": "education",
    "education and certifications": "education",
    "academic credentials": "education",
    "skills": "skills",
    "technical skills": "skills",
    "core competencies": "skills",
    "competencies": "skills",
    "areas of expertise": "skills",
    "expertise": "skills",
    "key skills": "skills",
    "core skills": "skills",
    "skills and tools": "skills",
    "tools": "skills",
    "technologies": "skills",
    "technical proficiencies": "skills",
    "proficiencies": "skills",
    "skills summary": "skills",
    "skills and expertise": "skills",
    "skills and certifications": "skills",
    "certifications": "certifications",
    "certificates": "certifications",
    "licenses": "certifications",
    "licenses and certifications": "certifications",
    "certifications and licenses": "certifications",
    "credentials": "certifications",
    "professional development": "certifications",
    "training": "certifications",
    "projects": "projects",
    "key projects": "projects",
    "selected projects": "projects",
    "awards": "awards",
    "honors": "awards",
    "honors and awards": "awards",
    "awards and honors": "awards",
    "awards and recognition": "awards",
    "recognition": "awards",
    "publications": "publications",
    "presentations": "publications",
    "publications and presentations": "publications",
    "volunteer": "volunteer",
    "volunteering": "volunteer",
    "volunteer experience": "volunteer",
    "community involvement": "volunteer",
    "community service": "volunteer",
    "leadership and community": "volunteer",
    "affiliations": "affiliations",
    "professional affiliations": "affiliations",
    "memberships": "affiliations",
    "professional memberships": "affiliations",
    "languages": "languages",
    "interests": "interests",
    "hobbies": "interests",
    "personal interests": "interests",
    "interests and hobbies": "interests",
    "references": "references",
}
# Words that place a non-standard heading, such as "Experience Highlights".
_HEADING_KEYWORDS: list[tuple[str, SectionKind]] = [
    ("experience", "experience"),
    ("employment", "experience"),
    ("education", "education"),
    ("skill", "skills"),
    ("competenc", "skills"),
    ("expertise", "skills"),
    ("certif", "certifications"),
    ("license", "certifications"),
    ("project", "projects"),
    ("award", "awards"),
    ("honor", "awards"),
    ("summary", "summary"),
    ("profile", "summary"),
    ("objective", "objective"),
    ("achievement", "highlights"),
    ("accomplishment", "highlights"),
    ("highlight", "highlights"),
    ("volunteer", "volunteer"),
    ("publication", "publications"),
    ("affiliation", "affiliations"),
    ("membership", "affiliations"),
    ("reference", "references"),
]
# Inline headings ("Certifications: CPA") that start their own section.
_INLINE_SECTION_KINDS = {
    "summary",
    "objective",
    "education",
    "certifications",
    "awards",
    "projects",
    "volunteer",
    "affiliations",
    "interests",
    "references",
}


def _wordset(text: str) -> frozenset[str]:
    return frozenset(text.split())


TITLE_WORDS = _wordset(
    """
    manager director analyst engineer lead leader head vp vice president consultant
    specialist coordinator associate intern internship officer administrator developer
    architect scientist designer accountant controller supervisor advisor adviser
    partner principal owner founder co-founder cofounder executive representative
    strategist planner assistant technician chief ceo cfo coo cto cio cmo cpo svp evp
    avp treasurer auditor economist researcher fellow teacher professor instructor
    lecturer nurse physician attorney counsel paralegal editor writer recruiter
    generalist buyer agent operator programmer senior sr sr. junior jr jr. staff trainee
    apprentice member contractor freelancer volunteer secretary clerk bookkeeper
    underwriter actuary investigator producer therapist pharmacist mechanic
    superintendent foreman estimator inspector dispatcher ambassador advocate organizer
    chair chairman chairperson trustee deputy resident postdoc tutor mentor coach
    captain lieutenant sergeant owner/operator administrative product program project rep sdr bdr
    """
)
ORG_WORDS = _wordset(
    """
    inc inc. llc llc. llp lp ltd ltd. corp corp. corporation company co co. group bank
    university college school hospital health healthcare motors motor technologies
    technology solutions partners consulting consultants plc gmbh ag foundation
    institute association agency systems services america americas international global
    labs laboratories industries holdings capital insurance logistics manufacturing
    pharmaceuticals enterprises networks media studios department dept ministry council
    authority commission army navy marines federal county city trust fund ventures
    energy airlines communications software clinic medical center centre church n.a. n.a usa
    us north south east west pacific atlantic
    """
)
_EMPLOYMENT_TYPES = re.compile(
    r"\(?\b(contract(?:or)?|freelance|part[- ]time|full[- ]time|internship|"
    r"temporary|temp|seasonal|interim)\b\)?",
    re.IGNORECASE,
)
_US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|"
    "NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"
)
_STATE_NAMES = (
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|"
    "Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|"
    "Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|"
    "New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    "Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|"
    "West Virginia|Wisconsin|Wyoming"
)
LOCATION = re.compile(
    rf"(?:\b[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){{0,3}},\s*(?:(?:{_US_STATES})\b|"
    rf"(?:{_STATE_NAMES})\b)(?:\s+\d{{5}}(?:-\d{{4}})?)?)"
    r"|\b(?:Remote|Hybrid)\b",
)
EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]*)?\(?\d{3}\)?[\s.\-]*\d{3}\s*[\s.\-]\s*\d{4}(?!\d)")
# Markings that an employer's labelling tool stamps on documents.
MARKING = re.compile(
    r"^[\W_]*(?:highly confidential|confidential|protected|internal(?: use)?(?: only)?|"
    r"restricted|proprietary)\b|関係者外秘|社外秘|極秘|機密|部外秘",
    re.IGNORECASE,
)
LINK = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in/[\w\-%]+/?|github\.com/[\w\-]+/?)"
    r"|https?://[^\s|,;]+",
    re.IGNORECASE,
)
STREET = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z0-9][a-z0-9]*\s+){1,4}"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|Pl|Place|"
    r"Cir|Circle|Pkwy|Parkway|Ter|Terrace|Hwy|Highway|Trl|Trail|Loop)\b\.?"
)
_SPLIT_PIECES = re.compile(r"\t+|\s+\|\s+|\s+[—–]\s+|\s+-\s+|,\s+|\s+at\s+|\s+@\s+|\s{3,}")
_SKILL_SPLIT = re.compile(r"\s*(?:[,;|•·▪◦\t]|\s{3,})\s*")


_REFERENCES_LINE = re.compile(r"^references?\b.*\b(?:request|available)\b", re.IGNORECASE)


def normalize_heading(text: str) -> str:
    text = text.lower().replace("&", " and ").replace("/", " and ")
    text = re.sub(r"[^a-z ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def heading_kind(block: Block) -> tuple[SectionKind, bool] | None:
    """Whether a line is a section heading: its kind, and whether it's a standard one."""
    if block.is_bullet or block.where in ("header", "footer"):
        return None
    text = block.text.strip().rstrip(":").strip()
    norm = normalize_heading(text)
    if not norm or len(norm.split()) > 5 or len(text) > 48:
        return None
    if norm in HEADINGS:
        return HEADINGS[norm], True
    if _REFERENCES_LINE.match(text):
        return "references", True
    if find_range(text) or EMAIL.search(text) or PHONE.search(text) or text.endswith("."):
        return None
    styled = (block.style or "").lower().startswith(("heading", "title")) or block.all_caps
    keyword = next((kind for key, kind in _HEADING_KEYWORDS if key in norm), None)
    if keyword is not None and (styled or block.bold) and len(norm.split()) <= 4:
        return keyword, False
    if styled and block.all_caps and not _looks_like_role_line(text):
        return "other", False
    return None


def _looks_like_role_line(text: str) -> bool:
    words = {w.strip(",.()").lower() for w in text.split()}
    return bool(words & TITLE_WORDS) or bool(words & ORG_WORDS)


def _inline_heading(block: Block) -> tuple[SectionKind, str] | None:
    """A "Heading: content" line, such as "Certifications: CPA (Ohio)"."""
    if ":" not in block.text:
        return None
    head, rest = block.text.split(":", 1)
    norm = normalize_heading(head)
    if norm in HEADINGS and rest.strip():
        return HEADINGS[norm], rest.strip()
    return None


_PAGE_NUMBER = re.compile(r"^(page\s*)?\d{1,2}(\s*(of|/)\s*\d{1,2})?$", re.I)
_REFERENCES = re.compile(
    r"^references?\s*(are\s*)?(available\s*)?(up)?on\s*request\.?$|^references?\s*available\.?$",
    re.I,
)


def plain_skip(text: str) -> SkipReason | None:
    """Why a line holds nothing to keep, when that's plain from the line alone."""
    text = text.strip()
    if _PAGE_NUMBER.match(text):
        return "page_number"
    if not re.search(r"[^\W_]", text):
        return "decoration"
    if _REFERENCES.match(text):
        return "references"
    return None


def is_marking(block: Block, markings: list[str]) -> bool:
    if block.where not in ("header", "footer", "text_box"):
        return False
    text = block.text.strip()
    return any(m.strip() and m.strip() in text for m in markings) or bool(MARKING.search(text))


def _contact_like(block: Block) -> bool:
    text = block.text
    return bool(
        EMAIL.search(text)
        or PHONE.search(text)
        or STREET.search(text)
        or LINK.search(text)
        or (LOCATION.fullmatch(text.strip()) is not None)
    )


def segment(doc: ExtractedDocument) -> ParsedResume:
    blocks = doc.blocks
    markings = {b.index for b in blocks if is_marking(b, doc.facts.markings)}
    # Contact details drawn in text boxes, wherever they're anchored, plus a name
    # in a text box set larger than the body text.
    size = body_size(blocks)
    boxed_contact = {
        b.index
        for b in blocks
        if b.where == "text_box"
        and b.index not in markings
        and (
            _contact_like(b)
            or (_name(b.text) is not None and max(b.font_sizes, default=0) > size + 4)
        )
    }
    sections: list[Section] = []
    current = Section(kind="contact", heading=None, heading_block=None)
    for block in blocks:
        if block.where in ("header", "footer") or block.index in markings | boxed_contact:
            continue
        found = heading_kind(block)
        if found is None and plain_skip(block.text) is not None:
            continue  # A page number, a rule or "References available on request".
        if found is not None:
            sections.append(current)
            kind, standard = found
            current = Section(
                kind=kind,
                heading=block.text.strip(),
                heading_block=block.index,
                heading_recognized=standard,
            )
            continue
        inline = _inline_heading(block)
        if (
            inline is not None
            and inline[0] in _INLINE_SECTION_KINDS
            and inline[0] != current.kind
            and current.kind != "contact"
        ):
            sections.append(current)
            current = Section(
                kind=inline[0],
                heading=block.text.split(":", 1)[0].strip(),
                heading_block=block.index,
                heading_recognized=True,
            )
        current.blocks.append(block.index)
    sections.append(current)
    sections = [s for s in sections if s.blocks or s.heading is not None]

    by_index = {b.index: b for b in blocks}
    # An experience heading over nothing but prose is a summary under the wrong name.
    for section in sections:
        if section.kind == "experience" and section.blocks:
            content = [by_index[i] for i in section.blocks]
            if all(not b.is_bullet and _is_description(b) for b in content):
                section.holds = "summary"

    contact_blocks = [
        b
        for b in blocks
        if (b.where in ("header", "footer") or b.index in boxed_contact) and b.index not in markings
    ]
    for section in sections:
        if section.kind == "contact":
            contact_blocks += [by_index[i] for i in section.blocks]
    parsed = ParsedResume(contact=parse_contact(contact_blocks), sections=sections, roles=[])

    role_count = 0
    for section in sections:
        section_blocks = [by_index[i] for i in section.blocks]
        kind = section.holds or section.kind
        if kind in ("experience", "volunteer"):
            roles = parse_roles(section_blocks, kind, start=role_count)
            role_count += len(roles)
            parsed.roles.extend(roles)
        elif kind in ("summary", "objective"):
            text = " ".join(_strip_inline(b.text) for b in section_blocks)
            parsed.summary = f"{parsed.summary} {text}".strip() if parsed.summary else text
            parsed.summary_blocks += section.blocks
        elif kind == "skills":
            for category, items, indexes in parse_skills(section_blocks):
                parsed.skills.setdefault(category, []).extend(items)
                parsed.skill_blocks.setdefault(category, []).extend(indexes)
        elif kind == "education":
            parsed.education += parse_entries(section_blocks, grouped=True)
        elif kind == "certifications":
            parsed.certifications += parse_entries(section_blocks, grouped=False)
        elif kind == "projects":
            parsed.projects += parse_entries(section_blocks, grouped=True)
        elif kind == "awards":
            parsed.awards += parse_entries(section_blocks, grouped=False)
        elif kind == "highlights":
            parsed.highlights += parse_entries(section_blocks, grouped=False)
    return parsed


def body_size(blocks: list[Block]) -> float:
    sizes: dict[float, int] = {}
    for b in blocks:
        for size in b.font_sizes:
            sizes[size] = sizes.get(size, 0) + len(b.text.split())
    return max(sizes, key=lambda k: sizes[k]) if sizes else 11.0


_ABBREVIATIONS = re.compile(
    r"(?:\b(?:e\.g|i\.e|etc|vs|Sr|Jr|Mr|Ms|Mrs|Dr|St|Inc|Co|Corp|Ltd|No|approx)|\b[A-Z](?:\.[A-Z])*)\.$"
)


def sentences(text: str) -> list[str]:
    """Splits prose into sentences, leaving abbreviations such as "U.S." and "e.g." alone."""
    out: list[str] = []
    buffer = ""
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"‘'(])", text.strip()):
        buffer = f"{buffer} {part}".strip() if buffer else part
        if not _ABBREVIATIONS.search(buffer):
            out.append(buffer)
            buffer = ""
    if buffer:
        out.append(buffer)
    return [s.strip() for s in out if s.strip()]


def _strip_inline(text: str) -> str:
    if ":" in text:
        head, rest = text.split(":", 1)
        if normalize_heading(head) in HEADINGS:
            return rest.strip()
    return text.strip()


# --- Contact ------------------------------------------------------------------


def parse_contact(blocks: list[Block]) -> Contact:
    contact = Contact(blocks=[b.index for b in blocks])
    names: list[tuple[float, int, str]] = []
    for block in blocks:
        text = block.text
        for email in EMAIL.findall(text):
            if email not in contact.emails:
                contact.emails.append(email)
        for phone in PHONE.findall(text):
            if phone.strip() not in contact.phones:
                contact.phones.append(phone.strip())
        for link in [*block.links, *LINK.findall(text)]:
            link = link.rstrip("/")
            if link.startswith("mailto:") or EMAIL.fullmatch(link):
                continue
            if link not in contact.links:
                contact.links.append(link)
        if STREET.search(text):
            contact.street_address = True
        if contact.location is None:
            m = LOCATION.search(EMAIL.sub(" ", text))
            if m:
                contact.location = m.group(0).strip()
        name = _name(text)
        if name is not None:
            names.append((-max(block.font_sizes, default=0.0), block.index, name))
    if names:
        contact.name = sorted(names)[0][2]
    return contact


def _name(text: str) -> str | None:
    first = re.split(r"\s*[|•·,\t]\s*|\s{3,}", text.strip())[0].strip()
    words = first.split()
    if not 2 <= len(words) <= 5 or any(c.isdigit() or c == "@" for c in first):
        return None
    if all(w[0].isupper() or w[0] in "'’(" for w in words if w[0].isalpha() or w[0] in "'’("):
        if normalize_heading(first) in HEADINGS:
            return None
        return first.title() if first.isupper() else first
    return None


# --- Roles --------------------------------------------------------------------

_SENTENCE = re.compile(r"[.!?]$")


def _is_description(block: Block) -> bool:
    words = len(block.text.split())
    found = find_range(block.text)
    if found is not None and found.separator is not None:
        return False
    return words >= 14 or (words >= 8 and bool(_SENTENCE.search(block.text.strip())))


class _Group:
    def __init__(self) -> None:
        self.header: list[Block] = []
        self.description: list[Block] = []
        self.bullets: list[Block] = []

    def dated(self) -> bool:
        return any(find_range(b.text) for b in self.header)

    def mentions_clients(self) -> bool:
        return any(re.search(r"\bclients?\b", b.text, re.IGNORECASE) for b in self.header)


def _pieces(text: str) -> list[str]:
    return [p for p in (_tidy(p) for p in _SPLIT_PIECES.split(text)) if p]


def _starts_engagement(group: _Group, block: Block) -> bool:
    """A line under a dated role that names another organization (a client, say)."""
    if not group.dated() or find_range(block.text) is not None:
        return False
    pieces = _pieces(block.text)
    if len(pieces) >= 2 and any(_looks_like_role_line(p) for p in pieces):
        return True
    return len(pieces) == 1 and (_score(pieces[0]) < 0 or group.mentions_clients())


def parse_roles(blocks: list[Block], section: SectionKind, *, start: int = 0) -> list[Role]:
    groups: list[_Group] = []
    current: _Group | None = None
    for block in blocks:
        if block.is_bullet:
            if current is None:
                current = _Group()
                groups.append(current)
            current.bullets.append(block)
            continue
        if current is not None and _is_description(block):
            (current.bullets if current.bullets else current.description).append(block)
            continue
        line_range = find_range(block.text)
        starts_new = (
            current is None
            or bool(current.bullets)
            or bool(current.description)
            or (
                line_range is not None
                and current.dated()
                and bool(strip_range(block.text, line_range))
            )
            or _starts_engagement(current, block)
        )
        if starts_new:
            current = _Group()
            groups.append(current)
        assert current is not None
        current.header.append(block)

    roles: list[Role] = []
    for group in groups:
        role, label = _parse_header(group.header)
        role.section = "volunteer" if section == "volunteer" else "experience"
        role.bullets = [
            Bullet(block=b.index, text=b.text, bullet_char=b.bullet_char, group=label)
            for b in group.bullets
        ]
        if group.description:
            role.description = " ".join(b.text for b in group.description)
            role.description_blocks = [b.index for b in group.description]
        roles.append(role)

    result: list[Role] = []
    parents: dict[int, Role] = {}
    parent: Role | None = None
    # The role that opened the current employer line, while titles follow it.
    employer: Role | None = None
    for role in roles:
        prev = result[-1] if result else None
        label = role.title if role.organization is None else None
        # A short undated label over bullets ("Workforce Strategies") is a
        # workstream inside the role above, not a role of its own.
        if (
            prev is not None
            and role.dates is None
            and label is not None
            and _score(label) <= 0
            and len(label.split()) <= 5
            and role.bullets
            and not role.description
        ):
            for bullet in role.bullets:
                bullet.group = label
            prev.bullets += role.bullets
            continue
        # An undated organization under a dated role is a client engagement.
        if role.dates is None and parent is not None:
            client = role.organization
            if client is None and label is not None and _score(label) <= 0:
                client, role.title = label, None
            if client is not None:
                role.client = client
                role.organization = parent.organization
                role.organization_inferred = True
                role.confidence = "high"
                parents[id(role)] = parent
                result.append(role)
                continue
        # An employer line followed by a title line: "Acme Corp" then "Analyst 2019-2021".
        if (
            prev is not None
            and role.organization is None
            and role.title is not None
            and prev.organization is not None
            and prev.title is None
            and not prev.bullets
            and not prev.description
        ):
            role.organization = prev.organization
            role.organization_inferred = True
            result.pop()
            role.employer_block = prev.header_blocks[0] if prev.header_blocks else None
            role.header_blocks = prev.header_blocks + role.header_blocks
            role.header_text = f"{prev.header_text}\n{role.header_text}"
            role.location = role.location or prev.location
            role.dates = role.dates or prev.dates
            employer = role
        # A later dated title under the same employer line: a promotion.
        elif (
            employer is not None
            and prev is not None
            and prev.employer_block == employer.employer_block
            and role.organization is None
            and role.title is not None
            and role.dates is not None
            and _score(role.title) > 0
        ):
            role.organization = employer.organization
            role.organization_inferred = True
            role.employer_block = employer.employer_block
            role.location = role.location or employer.location
        else:
            employer = None
        if role.dates is not None:
            parent = role
        result.append(role)
    for i, role in enumerate(result, start=start + 1):
        role.ref = f"role-{i}"
    for role in result:
        if id(role) in parents:
            role.parent_ref = parents[id(role)].ref
    return result


def _score(piece: str) -> int:
    words = [w.strip(",.()&").lower() for w in piece.split()]
    title = sum(1 for w in words if w in TITLE_WORDS)
    org = sum(1 for w in words if w in ORG_WORDS or w.rstrip(".") in ORG_WORDS)
    return title - org


_NOTE = re.compile(
    r"\s*\((?=[^)]*\b(?:client|clients|list|formerly|acquired|now|part of)\b)[^)]*\)",
    re.IGNORECASE,
)


def _tidy(piece: str) -> str:
    """Trims separators and notes like "(partial client list)", keeping "(TMNA)"."""
    piece = _NOTE.sub("", piece).strip(" |,;:-–—")
    if piece.startswith("(") and piece.endswith(")") and piece.count("(") == 1:
        piece = piece[1:-1]
    while piece.endswith(")") and piece.count(")") > piece.count("("):
        piece = piece[:-1].rstrip()
    while piece.startswith("(") and piece.count("(") > piece.count(")"):
        piece = piece[1:].lstrip()
    piece = piece.strip(" |,;:-–—")
    return piece if any(c.isalpha() for c in piece) else ""


def _parse_header(header: list[Block]) -> tuple[Role, str | None]:
    """The role a header describes, and a workstream label under it if there is one."""
    role = Role(ref="", header_blocks=[b.index for b in header])
    role.header_text = "\n".join(b.text for b in header)
    pieces: list[tuple[int, str]] = []  # (line number, text) in reading order
    for line_no, block in enumerate(header):
        text = block.text
        found = find_range(text)
        if found is not None and (role.dates is None or found.separator is not None):
            role.dates = found
            text = strip_range(text, found)
        m = _EMPLOYMENT_TYPES.search(text)
        if m:
            role.employment_type = m.group(1).lower()
            if m.group(0).startswith("("):
                text = text.replace(m.group(0), " ")
        loc = LOCATION.search(text)
        if loc:
            role.location = role.location or loc.group(0).strip()
            text = text.replace(loc.group(0), " ")
        pieces += [(line_no, p) for p in _pieces(text)]

    label: str | None = None
    if len(header) > 1 and pieces and pieces[-1][0] == len(header) - 1:
        last_line = [p for line, p in pieces if line == len(header) - 1]
        earlier = [p for line, p in pieces if line < len(header) - 1]
        if len(last_line) == 1 and len(earlier) >= 2 and _score(last_line[0]) == 0:
            label = last_line[0]
            pieces = pieces[:-1]

    if not pieces:
        role.confidence = "low"
        return role, label
    if len(pieces) == 1:
        piece = pieces[0][1]
        if _score(piece) > 0:
            role.title = piece
        elif _score(piece) < 0:
            role.organization = piece
        else:
            role.title = piece
            role.confidence = "low"
        return role, label

    scores = [_score(p) for _, p in pieces]
    ranked = sorted(range(len(pieces)), key=lambda i: scores[i], reverse=True)
    title_i, org_i = ranked[0], ranked[-1]
    if scores[title_i] == scores[org_i]:
        role.confidence = "low"
        same_line = pieces[0][0] == pieces[1][0]
        # One line reads "Title, Company"; stacked lines usually put the company first.
        title_i, org_i = (0, 1) if same_line else (1, 0)
    title_end, org_end = title_i, org_i
    # Keep "Manager, Data Science" and "HSBC Bank USA, N.A." whole.
    while (
        title_end + 1 < len(pieces)
        and title_end + 1 != org_i
        and scores[title_end + 1] >= 0
        and pieces[title_end + 1][0] == pieces[title_i][0]
        and title_i < org_i
    ):
        title_end += 1
    while (
        org_end + 1 < len(pieces)
        and org_end + 1 != title_i
        and scores[org_end + 1] < 0
        and pieces[org_end + 1][0] == pieces[org_i][0]
    ):
        org_end += 1
    role.title = ", ".join(p for _, p in pieces[title_i : title_end + 1])
    role.organization = ", ".join(p for _, p in pieces[org_i : org_end + 1])
    role.title_first = title_i < org_i
    return role, label


# --- Skills and entries -----------------------------------------------------------


def parse_skills(blocks: list[Block]) -> list[tuple[str, list[str], list[int]]]:
    groups: list[tuple[str, list[str], list[int]]] = []
    for block in blocks:
        category = "Skills"
        text = block.text
        if ":" in text:
            head, rest = text.split(":", 1)
            if 0 < len(head.split()) <= 5 and rest.strip():
                category, text = head.strip(), rest
        items = [
            re.sub(r"^(?:and|&)\s+", "", item).strip(" .") for item in _SKILL_SPLIT.split(text)
        ]
        items = [i for i in items if i and len(i) <= 60]
        if items:
            groups.append((category, items, [block.index]))
    return groups


_DEGREE = re.compile(
    r"\b(?:B\.?\s?[AS]\.?|B\.?\s?Sc|BBA|M\.?\s?[AS]\.?|MBA|M\.?\s?Sc|MPA|MPH|MFA|J\.?D\.?|"
    r"Ph\.?\s?D\.?|Ed\.?D|M\.?D\.?|Associate|Bachelor|Master|Doctor|Doctorate|Diploma|"
    r"Certificate|High School|GED)\b",
    re.IGNORECASE,
)
_SCHOOL = re.compile(r"\b(?:University|College|Institute|School|Academy|Polytechnic)\b")


def parse_entries(blocks: list[Block], *, grouped: bool) -> list[Entry]:
    entries: list[Entry] = []
    for block in blocks:
        text = _strip_inline(block.text)
        starts = (
            not grouped
            or not entries
            or (
                not block.is_bullet
                and (_DEGREE.search(text) or _SCHOOL.search(text) or not entries[-1].details)
                and not _continues(entries[-1], text)
            )
        )
        if starts:
            entries.append(Entry(text=text, blocks=[block.index], dates=find_range(text)))
        else:
            entries[-1].details.append(text)
            entries[-1].blocks.append(block.index)
            if entries[-1].dates is None:
                entries[-1].dates = find_range(text)
    return entries


def _continues(entry: Entry, text: str) -> bool:
    """A school line after a degree line (or the reverse) belongs to the same entry."""
    if entry.details:
        return False
    first_degree = bool(_DEGREE.search(entry.text))
    first_school = bool(_SCHOOL.search(entry.text))
    if first_degree and first_school:
        return False
    return (
        (first_degree and bool(_SCHOOL.search(text)) and not _DEGREE.search(text))
        or (first_school and bool(_DEGREE.search(text)) and not _SCHOOL.search(text))
        or (find_range(text) is not None and len(text.split()) <= 4)
    )
