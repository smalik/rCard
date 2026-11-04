"""Shapes passed between the import stages."""

from typing import Literal

from pydantic import BaseModel, Field

from plytos_api.cards.model import CardKind, MainContent
from plytos_api.imports.usage import AiUsage

DocFormat = Literal["docx", "pdf", "text"]
Severity = Literal["fix", "improve", "note"]
Category = Literal["ats", "layout", "consistency", "dates", "content", "contact", "length", "file"]
# Why a line of the resume was left off every card on purpose.
SkipReason = Literal["page_number", "page_header", "decoration", "references", "marking"]


class Block(BaseModel):
    """One line or paragraph of the resume, in reading order."""

    index: int
    text: str
    is_bullet: bool = False
    bullet_char: str | None = None
    style: str | None = None
    bold: bool = False
    all_caps: bool = False
    font_names: list[str] = Field(default_factory=list)
    font_sizes: list[float] = Field(default_factory=list)
    # "image": read from a picture in the file (a scanned page, a screenshot of bullets).
    where: Literal["body", "table", "text_box", "header", "footer", "image"] = "body"
    page: int | None = None
    links: list[str] = Field(default_factory=list)


class Picture(BaseModel):
    """An image placed in the document, and the line it follows."""

    after_block: int | None
    width_in: float
    height_in: float
    where: Literal["body", "table", "text_box", "header", "footer"] = "body"
    # How many lines of text were read from it.
    lines_read: int = 0


class PictureImage(BaseModel):
    """A picture's pixels, kept only while the import reads the words in it. Never
    stored or logged."""

    after_block: int | None
    page: int | None = None
    # Its place in DocumentFacts.pictures, or None for a whole scanned page.
    picture: int | None = None
    media_type: Literal["image/png", "image/jpeg"]
    data: bytes = Field(repr=False)


class DocumentFacts(BaseModel):
    format: DocFormat
    filename: str
    pages: int | None = None
    word_count: int = 0
    tables: int = 0
    table_words: int = 0
    text_boxes: int = 0
    images: int = 0
    columns: int = 1
    fonts: dict[str, int] = Field(default_factory=dict)
    font_sizes: dict[str, int] = Field(default_factory=dict)
    has_text_layer: bool = True
    # PDF pages with no text layer (scans), read from their picture when Claude reads.
    scanned_pages: list[int] = Field(default_factory=list)
    # Sensitivity or classification markings an organization's labelling tool added.
    markings: list[str] = Field(default_factory=list)
    pictures: list[Picture] = Field(default_factory=list)
    text_width_in: float | None = None


class ExtractedDocument(BaseModel):
    facts: DocumentFacts
    blocks: list[Block]
    # Pictures that may hold words, to be read before the lines are. Never serialized.
    images: list[PictureImage] = Field(default_factory=list, exclude=True, repr=False)


class YearMonth(BaseModel):
    year: int
    month: int | None = None

    def ordinal(self, *, end: bool = False) -> int:
        """Months since year 0; a year-only date counts as Jan (start) or Dec (end)."""
        month = self.month if self.month is not None else (12 if end else 1)
        return self.year * 12 + (month - 1)

    def iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}" if self.month else f"{self.year:04d}"


class DateRange(BaseModel):
    raw: str
    start: YearMonth | None
    end: YearMonth | None
    current: bool
    start_format: str | None
    end_format: str | None
    separator: str | None
    current_word: str | None = None


class Contact(BaseModel):
    name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    location: str | None = None
    street_address: bool = False
    blocks: list[int] = Field(default_factory=list)


class Bullet(BaseModel):
    block: int
    text: str
    bullet_char: str | None
    # A workstream or project label the bullet sits under inside its role.
    group: str | None = None


class Role(BaseModel):
    ref: str
    section: Literal["experience", "volunteer"] = "experience"
    title: str | None = None
    organization: str | None = None
    organization_inferred: bool = False
    # Set on a client engagement listed under a consulting or agency role.
    client: str | None = None
    parent_ref: str | None = None
    location: str | None = None
    employment_type: str | None = None
    dates: DateRange | None = None
    header_blocks: list[int] = Field(default_factory=list)
    header_text: str = ""
    # The employer's own line when it sits above one or more titles
    # ("Northwind Logistics, Mar 2014 - Present"). Also in header_blocks.
    employer_block: int | None = None
    # The employment this role is a position (or engagement) in.
    employment_ref: str | None = None
    # Which employment the reader put this role in, when it said; roles that
    # share a key are one employment.
    employment_key: str | None = None
    # Lines about the employer written under its name, before the first title
    # ("A $2B regional grocer with 140 stores"). They describe the employment.
    employer_description_blocks: list[int] = Field(default_factory=list)
    title_first: bool | None = None
    # "low" when the title and the organization couldn't be told apart.
    confidence: Literal["high", "low"] = "high"
    description: str | None = None
    description_blocks: list[int] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)
    # Lines inside the role naming a workstream or project its bullets sit under
    # ("Enterprise AI"). They label the bullets below them, like a heading.
    subheading_blocks: list[int] = Field(default_factory=list)


class Employment(BaseModel):
    """One continuous stretch with one employer, holding the titles held there.

    A resume with promotions often writes the employer and the whole tenure
    once, with each title and its own dates under it. The tenure is kept here
    and each title becomes a position inside it."""

    ref: str
    section: Literal["experience", "volunteer"] = "experience"
    organization: str | None = None
    organization_inferred: bool = False
    location: str | None = None
    employment_type: str | None = None
    # The tenure: as written on the employer's line when there is one,
    # otherwise the span of its positions.
    dates: DateRange | None = None
    tenure_written: bool = False
    header_blocks: list[int] = Field(default_factory=list)
    # What the resume says about the employer or the whole stint.
    description: str | None = None
    description_blocks: list[int] = Field(default_factory=list)
    # Positions and engagements, in resume order.
    role_refs: list[str] = Field(default_factory=list)


class Entry(BaseModel):
    """An education, certification, project or award line, with its details."""

    text: str
    blocks: list[int] = Field(default_factory=list)
    dates: DateRange | None = None
    details: list[str] = Field(default_factory=list)


SectionKind = Literal[
    "contact",
    "summary",
    "objective",
    "highlights",
    "experience",
    "education",
    "skills",
    "certifications",
    "projects",
    "awards",
    "publications",
    "volunteer",
    "affiliations",
    "languages",
    "interests",
    "references",
    "other",
]


class Section(BaseModel):
    kind: SectionKind
    # What the section actually holds, when that differs from its heading.
    holds: SectionKind | None = None
    heading: str | None
    heading_block: int | None
    heading_recognized: bool = True
    blocks: list[int] = Field(default_factory=list)


class ParsedResume(BaseModel):
    contact: Contact
    sections: list[Section]
    roles: list[Role]
    employments: list[Employment] = Field(default_factory=list)
    summary: str | None = None
    summary_blocks: list[int] = Field(default_factory=list)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    skill_blocks: dict[str, list[int]] = Field(default_factory=dict)
    education: list[Entry] = Field(default_factory=list)
    certifications: list[Entry] = Field(default_factory=list)
    projects: list[Entry] = Field(default_factory=list)
    awards: list[Entry] = Field(default_factory=list)
    highlights: list[Entry] = Field(default_factory=list)
    # Talks, publications, boards, memberships, volunteering and interests.
    activities: list[Entry] = Field(default_factory=list)
    # Lines the reader left out on purpose, and why.
    skipped: dict[int, SkipReason] = Field(default_factory=dict)


class Location(BaseModel):
    block: int | None = None
    excerpt: str
    # The figure this place quotes, when the finding is two places disagreeing
    # about a number. The person settles it by picking one.
    figure: str | None = None


class Finding(BaseModel):
    rule: str
    severity: Severity
    category: Category
    # "cards" when the problem is in the words or facts that become cards, so
    # it travels with them; "document" when it's about how this file is laid
    # out or formatted, which goes away once the content lives in cards.
    about: Literal["cards", "document"] = "document"
    title: str
    detail: str
    locations: list[Location] = Field(default_factory=list)


class PlaceChoice(BaseModel):
    # The proposed card it would sit under; None for the top of the tree.
    parent_ref: str | None
    label: str


class Placement(BaseModel):
    """A question about where a card belongs, when the checks disagree with the
    reading. The person answers before the card is saved."""

    question: str
    reason: str
    # Where it sits now comes first.
    choices: list[PlaceChoice]
    # Where the reading put it, when the checks agreed it belongs elsewhere and
    # Plytos moved it.
    moved_from: str | None = None


class ProposedCard(BaseModel):
    ref: str
    kind: CardKind
    content: MainContent
    # The proposed card this one sits under (an accomplishment under its
    # position, a position under its employment). On approval it becomes
    # content.parent, pointing at the parent's saved card.
    parent_ref: str | None = None
    role_ref: str | None = None
    # Set on an employment card: the employment it stands for.
    employment_ref: str | None = None
    source_blocks: list[int] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    # Questions for the person where the import had to guess.
    needs_check: list[str] = Field(default_factory=list)
    placement: Placement | None = None


class SkippedLine(BaseModel):
    block: int
    reason: SkipReason


class LineAccount(BaseModel):
    """Where each line of the resume went."""

    lines: int
    on_cards: int
    contact: list[int] = Field(default_factory=list)
    headings: list[int] = Field(default_factory=list)
    skipped: list[SkippedLine] = Field(default_factory=list)
    # Lines nothing claimed. Each is now on a card of its own, marked to check.
    guessed: list[int] = Field(default_factory=list)


class ImportResult(BaseModel):
    """What the person reviews. It holds their resume text, so it's never logged, and it's
    stored only encrypted with the person's own data key (imports/store.py)."""

    facts: DocumentFacts
    contact: Contact
    sections: list[Section]
    roles: list[Role]
    employments: list[Employment] = Field(default_factory=list)
    cards: list[ProposedCard]
    findings: list[Finding]
    blocks: list[Block]
    # The model that decided which line is which, or None when the rules did.
    read_by: str | None = None
    # Where every line of the resume went. None on imports from before it was kept.
    lines: LineAccount | None = None
    # What each Claude call cost (imports/usage.py). None when Claude didn't read it.
    usage: AiUsage | None = None
