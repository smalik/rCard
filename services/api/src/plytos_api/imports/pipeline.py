"""Runs an import end to end: read the file, split it, audit it, propose cards."""

from datetime import date

from plytos_api.imports.audit import audit
from plytos_api.imports.cards import propose_cards
from plytos_api.imports.extract import extract
from plytos_api.imports.model import ImportResult
from plytos_api.imports.segment import segment


def import_resume(data: bytes, filename: str, *, today: date | None = None) -> ImportResult:
    doc = extract(data, filename)
    parsed = segment(doc)
    findings = audit(doc, parsed, today=today)
    return ImportResult(
        facts=doc.facts,
        contact=parsed.contact,
        sections=parsed.sections,
        roles=parsed.roles,
        cards=propose_cards(parsed, findings, {b.index: b.text for b in doc.blocks}),
        findings=findings,
        blocks=doc.blocks,
    )
