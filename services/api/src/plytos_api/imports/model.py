"""Shapes passed between the import stages."""

from typing import Literal

from pydantic import BaseModel, Field

from plytos_api.cards.model import CardKind, MainContent

DocFormat = Literal["docx", "pdf", "text"]
Severity = Literal["fix", "improve", "note"]
Category = Literal["ats", "layout", "consistency", "dates", "content", "contact", "length", "file"]


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
    where: Literal["body", "table", "text_box", "header", "footer"] = "body"
    page: int | None = None
    links: list[str] = Field(default_factory=list)


class Picture(BaseModel):
    """An image placed in the document, and the line it follows."""

    after_block: int | None
    width_in: float
    height_in: float
    where: Literal["body", "table", "text_box", "header", "footer"] = "body"


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
    # Sensitivity or classification markings an organization's labelling tool added.
    markings: list[str] = Field(default_factory=list)
    pictures: list[Picture] = Field(default_factory=list)
    text_width_in: float | None = None


class ExtractedDocument(BaseModel):
    facts: DocumentFacts
    blocks: list[Block]


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
    title_first: bool | None = None
    # "low" when the title and the organization couldn't be told apart.
    confidence: Literal["high", "low"] = "high"
    description: str | None = None
    description_blocks: list[int] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)


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
    summary: str | None = None
    summary_blocks: list[int] = Field(default_factory=list)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    skill_blocks: dict[str, list[int]] = Field(default_factory=dict)
    education: list[Entry] = Field(default_factory=list)
    certifications: list[Entry] = Field(default_factory=list)
    projects: list[Entry] = Field(default_factory=list)
    awards: list[Entry] = Field(default_factory=list)
    highlights: list[Entry] = Field(default_factory=list)


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


class ProposedCard(BaseModel):
    ref: str
    kind: CardKind
    content: MainContent
    role_ref: str | None = None
    source_blocks: list[int] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    # Questions for the person where the import had to guess.
    needs_check: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    """What the person reviews. It holds their resume text, so it's never logged, and it's
    stored only encrypted with the person's own data key (imports/store.py)."""

    facts: DocumentFacts
    contact: Contact
    sections: list[Section]
    roles: list[Role]
    cards: list[ProposedCard]
    findings: list[Finding]
    blocks: list[Block]
