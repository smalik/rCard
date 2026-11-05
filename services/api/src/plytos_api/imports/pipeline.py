"""Runs an import end to end: read the file, split it, audit it, propose cards."""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from typing import Literal

from plytos_api.imports.accounting import account
from plytos_api.imports.ai import (
    AiFacts,
    AiProofread,
    FactReader,
    Metered,
    PictureReader,
    PlacementChecker,
    Proofreader,
    ResumeReader,
    to_parsed,
)
from plytos_api.imports.audit import audit
from plytos_api.imports.cards import propose_cards
from plytos_api.imports.career import group_employments, settle_employments
from plytos_api.imports.extract import UnsupportedFileError, extract
from plytos_api.imports.facts import add_result_facts, to_ask, words
from plytos_api.imports.model import ExtractedDocument, ImportResult, ParsedResume
from plytos_api.imports.pictures import add_picture_lines, mark_picture_cards
from plytos_api.imports.placement import check_placements
from plytos_api.imports.proofread import proofread_findings
from plytos_api.imports.segment import segment
from plytos_api.imports.usage import AiCall, AiUsage

log = logging.getLogger(__name__)

# Where a reading is, for whoever is waiting on it: reading the pictures, sorting
# the lines into jobs, then checking where each line goes and pulling out facts.
Stage = Literal["pictures", "structure", "checks"]


def import_resume(
    data: bytes,
    filename: str,
    *,
    today: date | None = None,
    reader: ResumeReader | None = None,
    on_stage: Callable[[Stage], None] | None = None,
) -> ImportResult:
    """Reads a resume. With a reader, Claude reads the words in its pictures, decides
    which line is which, checks where each line was filed, pulls facts out of each
    accomplishment and proofreads it; without one, or when it can't, the rule-based
    parser does the reading and the rest is left out. ``on_stage`` hears as each
    stage starts."""
    doc = extract(data, filename)
    calls: list[AiCall] | None = None
    if isinstance(reader, Metered):
        # Its own copy, so this import's calls are counted apart from any other's.
        reader = reader.metered()
        calls = reader.calls
    try:
        return _read(doc, reader, calls, today, on_stage or _quiet)
    except Exception as exc:
        # The calls made before it failed were billed: keep them with the error, for
        # whoever counts the spend.
        setattr(exc, "ai_calls", list(calls or []))  # noqa: B010 - an attribute of our own
        raise


def _read(
    doc: ExtractedDocument,
    reader: ResumeReader | None,
    calls: list[AiCall] | None,
    today: date | None,
    on_stage: Callable[[Stage], None],
) -> ImportResult:
    if isinstance(reader, PictureReader) and doc.images:
        on_stage("pictures")
        seen = reader.read_pictures(doc.images)
        if seen is not None:
            doc = add_picture_lines(doc, seen)
        if not doc.blocks:
            # The pictures were read and held no words that could be made out (a scan
            # too faint or too small): say so, rather than show an empty resume.
            raise UnsupportedFileError("No words could be read in this file.")

    on_stage("structure")
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Proofreading needs only the lines, so it runs while the structure is read.
        proofing: Future[AiProofread | None] | None = None
        if isinstance(reader, Proofreader) and doc.blocks:
            proofing = pool.submit(reader.proofread, doc)

        parsed: ParsedResume | None = None
        read_by: str | None = None
        if reader is not None:
            found = reader.read(doc)
            if found is not None:
                parsed, read_by = to_parsed(doc, found), reader.name
        if parsed is None:
            parsed = segment(doc)
        texts = {b.index: b.text for b in doc.blocks}
        if parsed.employments:
            # The reader said which titles belong to which employment.
            parsed.employments = settle_employments(parsed.employments, parsed.roles, texts)
        else:
            parsed.employments = group_employments(parsed.roles, texts)
        findings = audit(doc, parsed, today=today)
        cards = propose_cards(parsed, findings, texts)

        # Facts come out of each accomplishment while the placements are checked.
        on_stage("checks")
        asked = to_ask(cards)
        facts: Future[AiFacts | None] | None = None
        if isinstance(reader, FactReader) and read_by is not None and asked:
            items = [(ref, words(card)) for ref, card in asked.items()]
            facts = pool.submit(reader.read_facts, items)
        checker = reader if isinstance(reader, PlacementChecker) and read_by is not None else None
        check_placements(doc, parsed, cards, checker)

        got_facts = _result(facts)
        if got_facts is not None:
            add_result_facts(asked, got_facts)
        typos = _result(proofing)
        if typos is not None:
            findings += proofread_findings(doc, parsed, typos)

    lines = account(doc, parsed, cards, skipped=parsed.skipped)
    mark_picture_cards(doc.blocks, cards)
    return ImportResult(
        facts=doc.facts,
        contact=parsed.contact,
        sections=parsed.sections,
        roles=parsed.roles,
        employments=parsed.employments,
        cards=cards,
        findings=findings,
        blocks=doc.blocks,
        read_by=read_by,
        lines=lines,
        usage=AiUsage(calls=list(calls)) if calls is not None else None,
    )


def _quiet(stage: Stage) -> None:
    pass


def _result[T](future: Future[T | None] | None) -> T | None:
    """A side pass's answer, or None when it failed: the import goes on without it."""
    if future is None:
        return None
    try:
        return future.result()
    except Exception as exc:  # the passes log their own API errors; this is a backstop
        log.warning("A side pass of the import failed: %s", type(exc).__name__)
        return None
