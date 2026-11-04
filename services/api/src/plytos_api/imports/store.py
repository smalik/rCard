"""Keeps a person's resume imports.

An import holds the original file, untouched, what the import read from it,
and the person's progress checking it: which questions they settled and what
they decided about each proposed card. Every part is encrypted with the
person's own data key, like card content.

A proposed card is not a card. It becomes one only when the person approves
it, and then it's saved through CardRepository like any card they write.

The connection passed in must already be scoped to the person
(Database.as_user), so row-level security limits every query to their rows.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel, Field

from plytos_api.cards.model import MainContent, may_sit_under
from plytos_api.cards.repository import Author, CardDetail, CardRepository
from plytos_api.ids import uuid7
from plytos_api.imports.model import DocFormat, Finding, ImportResult, ProposedCard
from plytos_api.keys import UserCipher

# Findings that question a fact (a date, a number, a repeated line). The
# person settles these before approving cards. Wording findings travel with
# the cards instead, as tips while they review.
SETTLE_RULES = frozenset(
    {
        "consistency.figures",
        "content.duplicates",
        "dates.end_before_start",
        "dates.future",
        "dates.gap",
        "dates.many_current",
        "dates.missing",
        "dates.overlap",
        "dates.undated_engagements",
        "dates.year_only",
    }
)


class ImportNotFoundError(Exception):
    pass


class ImportConflictError(Exception):
    """The request doesn't fit the import as it stands, such as approving a card twice."""


class Settlement(BaseModel):
    # chosen: the person picked one of the figures; as_is: it's right as it
    # stands; on_card: they'll fix it on the card; later: not sure yet.
    answer: Literal["chosen", "as_is", "on_card", "later"]
    value: str | None = None
    # Proposed cards whose wording changed because of the answer.
    changed: list[str] = Field(default_factory=list)


class CardDecision(BaseModel):
    state: Literal["approved", "later", "dropped"]
    card_id: UUID | None = None


class ImportProgress(BaseModel):
    # Keyed by the finding's position in the import's list of findings.
    settled: dict[str, Settlement] = Field(default_factory=dict)
    # Keyed by the proposed card's ref.
    cards: dict[str, CardDecision] = Field(default_factory=dict)
    # Proposed wording after the person's answers, by card ref. The import's
    # own reading stays as it was.
    edits: dict[str, MainContent] = Field(default_factory=dict)
    # Where the person says a card belongs, by card ref: the proposed card it
    # sits under, or None for the top of the tree.
    moves: dict[str, str | None] = Field(default_factory=dict)


class ImportFile(BaseModel):
    format: DocFormat
    size: int
    name: str


class ImportSummary(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    file: ImportFile
    cards: int
    approved: int
    later: int
    dropped: int
    to_settle: int


class ImportView(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    file: ImportFile
    result: ImportResult
    progress: ImportProgress
    # Positions in result.findings of the things to settle before approving.
    to_settle: list[int]


def to_settle(result: ImportResult) -> list[int]:
    """Positions of the findings the person settles before approving cards."""
    return [
        i
        for i, f in enumerate(result.findings)
        if f.about == "cards" and f.rule in SETTLE_RULES and f.locations
    ]


def _aad(field: str, import_id: UUID) -> bytes:
    return b"plytos.resume_import." + field.encode() + b":" + import_id.bytes


class ImportStore:
    def __init__(self, conn: psycopg.Connection, user_id: UUID, cipher: UserCipher) -> None:
        self._conn = conn
        self._user_id = user_id
        self._cipher = cipher

    # -- writing -------------------------------------------------------------

    def create(self, data: bytes, filename: str, result: ImportResult) -> ImportView:
        import_id = uuid7()
        progress = ImportProgress()
        row = self._conn.execute(
            "insert into plytos.resume_import (id, owner_id, file_format, file_size,"
            " file_ciphertext, name_ciphertext, result_ciphertext, progress_ciphertext)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s) returning created_at, updated_at",
            (
                import_id,
                self._user_id,
                result.facts.format,
                len(data),
                self._seal("file", import_id, data),
                self._seal("name", import_id, filename.encode()),
                self._seal("result", import_id, result.model_dump_json().encode()),
                self._seal("progress", import_id, progress.model_dump_json().encode()),
            ),
        ).fetchone()
        assert row is not None
        self._event("import.created", import_id)
        return ImportView(
            id=import_id,
            created_at=row[0],
            updated_at=row[1],
            file=ImportFile(format=result.facts.format, size=len(data), name=filename),
            result=result,
            progress=progress,
            to_settle=to_settle(result),
        )

    def delete(self, import_id: UUID) -> None:
        """Deletes the import: the original file, what was read, and progress.
        Cards the person already approved stay."""
        gone = self._conn.execute(
            "delete from plytos.resume_import where id = %s", (import_id,)
        ).rowcount
        if gone != 1:
            raise ImportNotFoundError(str(import_id))
        self._event("import.deleted", import_id)

    def settle(
        self,
        import_id: UUID,
        finding: int,
        answer: Literal["chosen", "as_is", "on_card", "later"],
        value: str | None,
    ) -> ImportProgress:
        result, progress = self._load(import_id)
        if finding not in to_settle(result):
            raise ImportConflictError("That isn't one of the things to settle.")
        if answer == "chosen":
            figures = [loc.figure for loc in result.findings[finding].locations if loc.figure]
            if value is None or value not in figures:
                raise ImportConflictError("Pick one of the numbers your resume uses.")
        else:
            value = None
        progress.settled[str(finding)] = Settlement(answer=answer, value=value)
        _rebuild_edits(result, progress)
        self._save_progress(import_id, progress)
        return progress

    def decide(
        self, import_id: UUID, ref: str, state: Literal["later", "dropped", "pending"]
    ) -> ImportProgress:
        result, progress = self._load(import_id)
        _proposal(result, ref)
        current = progress.cards.get(ref)
        if current is not None and current.state == "approved":
            raise ImportConflictError("That card is already approved.")
        if state == "pending":
            progress.cards.pop(ref, None)
        else:
            progress.cards[ref] = CardDecision(state=state)
        self._save_progress(import_id, progress)
        return progress

    def place(self, import_id: UUID, ref: str, parent_ref: str | None) -> ImportProgress:
        """Records where a card belongs, answering its placement question."""
        result, progress = self._load(import_id)
        proposal = _proposal(result, ref)
        current = progress.cards.get(ref)
        if current is not None and current.state == "approved":
            raise ImportConflictError("That card is already approved.")
        if parent_ref is not None:
            parent = _proposal(result, parent_ref)
            # Every parent kind ranks above its child, so this can't make a loop.
            if not may_sit_under(proposal.kind, parent.kind):
                raise ImportConflictError("That card can't sit there.")
        elif proposal.kind in ("position", "engagement"):
            raise ImportConflictError("A title needs an employer.")
        progress.moves[ref] = parent_ref
        self._save_progress(import_id, progress)
        return progress

    def approve(
        self,
        import_id: UUID,
        ref: str,
        content: MainContent | None,
        cards: CardRepository,
        author: Author,
    ) -> tuple[CardDetail, ImportProgress]:
        """Saves one proposed card as an approved card, in the person's own words
        or the wording they edited it to."""
        result, progress = self._load(import_id)
        proposal = _proposal(result, ref)
        current = progress.cards.get(ref)
        if current is not None and current.state == "approved":
            raise ImportConflictError("That card is already approved.")
        if proposal.placement is not None and ref not in progress.moves:
            raise ImportConflictError(f"{proposal.placement.question} Answer that first.")
        chosen = content or progress.edits.get(ref) or proposal.content
        # It sits under the saved card of its nearest approved parent.
        chosen = chosen.model_copy(update={"parent": _saved_parent(result, progress, proposal)})
        card = cards.create_card(proposal.kind, chosen, author, status="approved")
        progress.cards[ref] = CardDecision(state="approved", card_id=card.id)
        self._save_progress(import_id, progress)
        return card, progress

    # -- reading -------------------------------------------------------------

    def summaries(self) -> list[ImportSummary]:
        rows = self._conn.execute(
            "select id, created_at, updated_at, file_format, file_size, name_ciphertext,"
            " result_ciphertext, progress_ciphertext from plytos.resume_import"
            " order by created_at desc"
        ).fetchall()
        return [self._summary(r) for r in rows]

    def summary(self, import_id: UUID) -> ImportSummary:
        row = self._conn.execute(
            "select id, created_at, updated_at, file_format, file_size, name_ciphertext,"
            " result_ciphertext, progress_ciphertext from plytos.resume_import where id = %s",
            (import_id,),
        ).fetchone()
        if row is None:
            raise ImportNotFoundError(str(import_id))
        return self._summary(row)

    def _summary(self, r: Sequence[Any]) -> ImportSummary:
        import_id: UUID = r[0]
        result = ImportResult.model_validate_json(self._open("result", import_id, r[6]))
        progress = ImportProgress.model_validate_json(self._open("progress", import_id, r[7]))
        states = [d.state for d in progress.cards.values()]
        unsettled = [
            i
            for i in to_settle(result)
            if (s := progress.settled.get(str(i))) is None or s.answer == "later"
        ]
        return ImportSummary(
            id=import_id,
            created_at=r[1],
            updated_at=r[2],
            file=ImportFile(
                format=r[3], size=r[4], name=self._open("name", import_id, r[5]).decode()
            ),
            cards=len(result.cards),
            approved=states.count("approved"),
            later=states.count("later"),
            dropped=states.count("dropped"),
            to_settle=len(unsettled),
        )

    def get(self, import_id: UUID) -> ImportView:
        row = self._conn.execute(
            "select created_at, updated_at, file_format, file_size, name_ciphertext,"
            " result_ciphertext, progress_ciphertext from plytos.resume_import where id = %s",
            (import_id,),
        ).fetchone()
        if row is None:
            raise ImportNotFoundError(str(import_id))
        result = ImportResult.model_validate_json(self._open("result", import_id, row[5]))
        return ImportView(
            id=import_id,
            created_at=row[0],
            updated_at=row[1],
            file=ImportFile(
                format=row[2], size=row[3], name=self._open("name", import_id, row[4]).decode()
            ),
            result=result,
            progress=ImportProgress.model_validate_json(self._open("progress", import_id, row[6])),
            to_settle=to_settle(result),
        )

    def original(self, import_id: UUID) -> tuple[ImportFile, bytes]:
        row = self._conn.execute(
            "select file_format, file_size, name_ciphertext, file_ciphertext"
            " from plytos.resume_import where id = %s",
            (import_id,),
        ).fetchone()
        if row is None:
            raise ImportNotFoundError(str(import_id))
        name = self._open("name", import_id, row[2]).decode()
        return ImportFile(format=row[0], size=row[1], name=name), self._open(
            "file", import_id, row[3]
        )

    # -- internals -----------------------------------------------------------

    def _load(self, import_id: UUID) -> tuple[ImportResult, ImportProgress]:
        """Reads an import to change its progress, locking the row until the
        transaction ends so two tabs can't overwrite each other's answers."""
        row = self._conn.execute(
            "select result_ciphertext, progress_ciphertext from plytos.resume_import"
            " where id = %s for update",
            (import_id,),
        ).fetchone()
        if row is None:
            raise ImportNotFoundError(str(import_id))
        return (
            ImportResult.model_validate_json(self._open("result", import_id, row[0])),
            ImportProgress.model_validate_json(self._open("progress", import_id, row[1])),
        )

    def _save_progress(self, import_id: UUID, progress: ImportProgress) -> None:
        self._conn.execute(
            "update plytos.resume_import set progress_ciphertext = %s, updated_at = now()"
            " where id = %s",
            (self._seal("progress", import_id, progress.model_dump_json().encode()), import_id),
        )

    def _seal(self, field: str, import_id: UUID, plaintext: bytes) -> bytes:
        return self._cipher.encrypt(plaintext, _aad(field, import_id))

    def _open(self, field: str, import_id: UUID, blob: bytes | memoryview) -> bytes:
        return self._cipher.decrypt(bytes(blob), _aad(field, import_id))

    def _event(self, action: str, import_id: UUID) -> None:
        self._conn.execute(
            "insert into plytos.event (owner_id, actor_kind, actor_ref, action, record_type,"
            " record_id) values (%s, 'person', %s, %s, 'resume_import', %s)",
            (self._user_id, str(self._user_id), action, import_id),
        )


def _proposal(result: ImportResult, ref: str) -> ProposedCard:
    for card in result.cards:
        if card.ref == ref:
            return card
    raise ImportNotFoundError(ref)


def _saved_parent(
    result: ImportResult, progress: ImportProgress, proposal: ProposedCard
) -> UUID | None:
    """The saved card a proposal sits under once approved. A dropped parent passes
    its children up to its own parent; one still undecided must be approved first."""
    ref = _parent_ref(progress, proposal)
    while ref is not None:
        parent = _proposal(result, ref)
        decision = progress.cards.get(ref)
        if decision is not None and decision.state == "approved":
            return decision.card_id
        if decision is not None and decision.state == "dropped":
            ref = _parent_ref(progress, parent)
            continue
        raise ImportConflictError(
            f"Approve “{parent.content.framing.headline}” first. This card sits under it."
        )
    return None


def _parent_ref(progress: ImportProgress, proposal: ProposedCard) -> str | None:
    """Where a proposed card sits: where the person put it, or where the import did."""
    if proposal.ref in progress.moves:
        return progress.moves[proposal.ref]
    return proposal.parent_ref


def _rebuild_edits(result: ImportResult, progress: ImportProgress) -> None:
    """Replays every figure the person picked over the import's own wording, so
    changing an answer never leaves the old one behind."""
    progress.edits = {}
    for key in sorted(progress.settled, key=int):
        settlement = progress.settled[key]
        settlement.changed = []
        if settlement.answer == "chosen" and settlement.value is not None:
            finding = result.findings[int(key)]
            settlement.changed = _use_figure(result.cards, finding, settlement.value, progress)


def _use_figure(
    cards: list[ProposedCard], finding: Finding, value: str, progress: ImportProgress
) -> list[str]:
    """Rewrites the proposed cards that quote the other figure to use the chosen one."""
    changed: list[str] = []
    for loc in finding.locations:
        if loc.figure is None or loc.figure == value or loc.block is None:
            continue
        quoted = loc.excerpt.rstrip("…").strip()
        for card in cards:
            if loc.block not in card.source_blocks:
                continue
            content = progress.edits.get(card.ref) or card.content
            text = content.framing.headline + " " + content.framing.body
            if quoted[:40] not in text and content.framing.headline[:40] not in quoted:
                continue  # another sentence from the same line
            updated = _replace_figure(content, loc.figure, value)
            if updated != content:
                progress.edits[card.ref] = updated
                changed.append(card.ref)
    return changed


def _replace_figure(content: MainContent, old: str, new: str) -> MainContent:
    pattern = re.compile(r"(?<![\d.,])" + re.escape(old) + r"(?![\d%])")
    framing = content.framing.model_copy(
        update={
            "headline": pattern.sub(new, content.framing.headline),
            "body": pattern.sub(new, content.framing.body),
        }
    )
    facts = dict(content.facts)
    figures = facts.get("figures")
    if isinstance(figures, list):
        facts["figures"] = list(dict.fromkeys(new if _same(f, old) else f for f in figures))
    return MainContent(facts=facts, framing=framing)


def _same(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return re.sub(r"[\s$,~≈]", "", s).lower().rstrip(".")

    return norm(a) == norm(b)
