"""Runs an import end to end: read the file, split it, audit it, propose cards."""

from datetime import date

from plytos_api.imports.ai import ResumeReader, to_parsed
from plytos_api.imports.audit import audit
from plytos_api.imports.cards import propose_cards
from plytos_api.imports.career import group_employments
from plytos_api.imports.extract import extract
from plytos_api.imports.model import ImportResult, ParsedResume
from plytos_api.imports.segment import segment


def import_resume(
    data: bytes, filename: str, *, today: date | None = None, reader: ResumeReader | None = None
) -> ImportResult:
    """Reads a resume. With a reader, Claude decides which line is which; without one,
    or when it can't, the rule-based parser does."""
    doc = extract(data, filename)
    parsed: ParsedResume | None = None
    read_by: str | None = None
    if reader is not None:
        found = reader.read(doc)
        if found is not None:
            parsed, read_by = to_parsed(doc, found), reader.name
    if parsed is None:
        parsed = segment(doc)
    texts = {b.index: b.text for b in doc.blocks}
    parsed.employments = group_employments(parsed.roles, texts)
    findings = audit(doc, parsed, today=today)
    return ImportResult(
        facts=doc.facts,
        contact=parsed.contact,
        sections=parsed.sections,
        roles=parsed.roles,
        employments=parsed.employments,
        cards=propose_cards(parsed, findings, texts),
        findings=findings,
        blocks=doc.blocks,
        read_by=read_by,
    )
