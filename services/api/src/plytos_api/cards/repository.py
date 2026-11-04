"""Reads and writes cards, lines and versions for one person.

The connection passed in must already be scoped to that person
(Database.as_user), so row-level security limits every query to their rows.

Saving a version is a compare-and-swap on the line's head: the caller names
the version its edit started from, and the save fails with StaleHeadError if
the line has moved on since. That way an AI job and the person editing the
same card can't silently overwrite each other.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors
from pydantic import BaseModel

from plytos_api.cards.hashing import canonical_json, chain_hash, content_hash
from plytos_api.cards.model import (
    SCHEMA_VERSION,
    AuthorKind,
    CardKind,
    MainContent,
    TargetKind,
    VariantContent,
)
from plytos_api.cards.rules import facts_changed, unsupported_claims
from plytos_api.ids import uuid7
from plytos_api.keys import UserCipher


class CardNotFoundError(Exception):
    pass


class StaleHeadError(Exception):
    def __init__(self, current_head_id: UUID | None) -> None:
        super().__init__("the card changed since this edit started")
        self.current_head_id = current_head_id


class UnsupportedClaimsError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class VariantExistsError(Exception):
    pass


@dataclass(frozen=True)
class Author:
    kind: AuthorKind
    ref: str | None = None


class VersionView(BaseModel):
    id: UUID
    line_id: UUID
    number: int
    parent_id: UUID | None
    based_on_main_version_id: UUID | None
    schema_version: int
    author_kind: AuthorKind
    created_at: datetime
    content_hash: str
    chain_hash: str
    redacted: bool


class LineView(BaseModel):
    id: UUID
    target_id: UUID | None
    state: str
    head: VersionView
    based_on_main_number: int | None
    content: MainContent | VariantContent | None


class CardDetail(BaseModel):
    id: UUID
    kind: CardKind
    status: str
    trust_level: int
    created_at: datetime
    main: LineView
    variants: list[LineView]


class CardSummary(BaseModel):
    id: UUID
    kind: CardKind
    status: str
    headline: str | None
    main_version: int
    variants: int
    variants_behind: int


class TargetView(BaseModel):
    id: UUID
    kind: TargetKind
    name: str
    parent_id: UUID | None


class SaveResult(BaseModel):
    version: VersionView
    variants_marked_behind: list[UUID]


@dataclass(frozen=True)
class _Line:
    id: UUID
    card_id: UUID
    target_id: UUID | None
    head_version_id: UUID | None
    state: str


def _version_view(row: Sequence[Any]) -> VersionView:
    return VersionView(
        id=row[0],
        line_id=row[1],
        number=row[2],
        parent_id=row[3],
        based_on_main_version_id=row[4],
        schema_version=row[5],
        author_kind=row[6],
        created_at=row[7],
        content_hash=bytes(row[8]).hex(),
        chain_hash=bytes(row[9]).hex(),
        redacted=bool(row[10]),
    )


def _version_aad(version_id: UUID) -> bytes:
    return b"plytos.card_version:" + version_id.bytes


def _target_aad(target_id: UUID) -> bytes:
    return b"plytos.target:" + target_id.bytes


class CardRepository:
    def __init__(self, conn: psycopg.Connection, user_id: UUID, cipher: UserCipher) -> None:
        self._conn = conn
        self._user_id = user_id
        self._cipher = cipher

    # -- cards and main line -------------------------------------------------

    def create_card(self, kind: CardKind, content: MainContent, author: Author) -> CardDetail:
        card_id = uuid7()
        line_id = uuid7()
        self._conn.execute(
            "insert into plytos.card (id, owner_id, kind) values (%s, %s, %s)",
            (card_id, self._user_id, kind),
        )
        self._conn.execute(
            "insert into plytos.card_line (id, owner_id, card_id) values (%s, %s, %s)",
            (line_id, self._user_id, card_id),
        )
        line = _Line(line_id, card_id, None, None, "current")
        self._append(line, None, content, None, author)
        self._event(author, "card.created", "card", card_id)
        return self.card_detail(card_id)

    def save_main_version(
        self, card_id: UUID, base_version_id: UUID, content: MainContent, author: Author
    ) -> SaveResult:
        line = self._line(card_id, None)
        self._check_head(line, base_version_id)
        parent = self._version(base_version_id)
        before = None if parent.redacted else self._main_content(parent)
        version = self._append(line, parent, content, None, author)

        behind: list[UUID] = []
        if facts_changed(before, content):
            rows = self._conn.execute(
                "update plytos.card_line set state = 'behind'"
                " where card_id = %s and target_id is not null and state = 'current'"
                " returning id",
                (card_id,),
            ).fetchall()
            behind = [r[0] for r in rows]
            for line_id in behind:
                self._event(author, "variant.marked_behind", "card_line", line_id)
        return SaveResult(version=version, variants_marked_behind=behind)

    # -- targets and variants ------------------------------------------------

    def create_target(self, kind: TargetKind, name: str, parent_id: UUID | None) -> TargetView:
        if parent_id is not None:
            parent = self._conn.execute(
                "select 1 from plytos.target where id = %s", (parent_id,)
            ).fetchone()
            if parent is None:
                raise CardNotFoundError(str(parent_id))
        target_id = uuid7()
        ciphertext = self._cipher.encrypt(name.encode(), _target_aad(target_id))
        self._conn.execute(
            "insert into plytos.target (id, owner_id, kind, parent_id, name_ciphertext)"
            " values (%s, %s, %s, %s, %s)",
            (target_id, self._user_id, kind, parent_id, ciphertext),
        )
        return TargetView(id=target_id, kind=kind, name=name, parent_id=parent_id)

    def list_targets(self) -> list[TargetView]:
        rows = self._conn.execute(
            "select id, kind, parent_id, name_ciphertext from plytos.target"
            " where archived_at is null order by created_at"
        ).fetchall()
        return [
            TargetView(
                id=r[0],
                kind=r[1],
                parent_id=r[2],
                name=self._cipher.decrypt(bytes(r[3]), _target_aad(r[0])).decode(),
            )
            for r in rows
        ]

    def create_variant(
        self, card_id: UUID, target_id: UUID, content: VariantContent, author: Author
    ) -> CardDetail:
        main_head = self._main_head(card_id)
        self._check_claims(content, main_head)
        exists = self._conn.execute(
            "select 1 from plytos.card_line where card_id = %s and target_id = %s",
            (card_id, target_id),
        ).fetchone()
        if exists:
            raise VariantExistsError(str(target_id))
        line_id = uuid7()
        self._conn.execute(
            "insert into plytos.card_line (id, owner_id, card_id, target_id)"
            " values (%s, %s, %s, %s)",
            (line_id, self._user_id, card_id, target_id),
        )
        line = _Line(line_id, card_id, target_id, None, "current")
        self._append(line, None, content, main_head.id, author)
        self._event(author, "variant.created", "card_line", line_id)
        return self.card_detail(card_id)

    def save_variant_version(
        self,
        card_id: UUID,
        target_id: UUID,
        base_version_id: UUID,
        content: VariantContent,
        author: Author,
    ) -> SaveResult:
        line = self._line(card_id, target_id)
        self._check_head(line, base_version_id)
        parent = self._version(base_version_id)
        main_head = self._main_head(card_id)
        self._check_claims(content, main_head)
        version = self._append(line, parent, content, main_head.id, author)
        if line.state == "behind":
            self._conn.execute(
                "update plytos.card_line set state = 'current' where id = %s", (line.id,)
            )
            self._event(author, "variant.refreshed", "card_line", line.id)
        return SaveResult(version=version, variants_marked_behind=[])

    # -- reading -------------------------------------------------------------

    def list_cards(self) -> list[CardSummary]:
        rows = self._conn.execute(
            "select c.id, c.kind, c.status, v.id, v.number, v.content_ciphertext,"
            "  (select count(*) from plytos.card_line x"
            "    where x.card_id = c.id and x.target_id is not null),"
            "  (select count(*) from plytos.card_line x"
            "    where x.card_id = c.id and x.state = 'behind')"
            " from plytos.card c"
            " join plytos.card_line l on l.card_id = c.id and l.target_id is null"
            " join plytos.card_version v on v.id = l.head_version_id"
            " where c.status <> 'archived'"
            " order by c.created_at desc"
        ).fetchall()
        summaries = []
        for r in rows:
            headline = None
            if r[5] is not None:
                content = MainContent.model_validate_json(
                    self._cipher.decrypt(bytes(r[5]), _version_aad(r[3]))
                )
                headline = content.framing.headline
            summaries.append(
                CardSummary(
                    id=r[0],
                    kind=r[1],
                    status=r[2],
                    headline=headline,
                    main_version=r[4],
                    variants=r[6],
                    variants_behind=r[7],
                )
            )
        return summaries

    def card_detail(self, card_id: UUID) -> CardDetail:
        card = self._conn.execute(
            "select kind, status, trust_level, created_at from plytos.card where id = %s",
            (card_id,),
        ).fetchone()
        if card is None:
            raise CardNotFoundError(str(card_id))
        lines = self._conn.execute(
            "select id, card_id, target_id, head_version_id, state from plytos.card_line"
            " where card_id = %s order by created_at",
            (card_id,),
        ).fetchall()
        main: LineView | None = None
        variants: list[LineView] = []
        for row in lines:
            line = _Line(*row)
            if line.head_version_id is None:
                continue
            head = self._version(line.head_version_id)
            based_on_number = None
            if head.based_on_main_version_id is not None:
                based_on_number = self._version(head.based_on_main_version_id).number
            content: MainContent | VariantContent | None = None
            if not head.redacted:
                raw = self._decrypt(head)
                content = (
                    MainContent.model_validate_json(raw)
                    if line.target_id is None
                    else VariantContent.model_validate_json(raw)
                )
            view = LineView(
                id=line.id,
                target_id=line.target_id,
                state=line.state,
                head=head,
                based_on_main_number=based_on_number,
                content=content,
            )
            if line.target_id is None:
                main = view
            else:
                variants.append(view)
        if main is None:
            raise CardNotFoundError(str(card_id))
        return CardDetail(
            id=card_id,
            kind=card[0],
            status=card[1],
            trust_level=card[2],
            created_at=card[3],
            main=main,
            variants=variants,
        )

    def history(self, card_id: UUID, target_id: UUID | None) -> list[VersionView]:
        line = self._line(card_id, target_id)
        rows = self._conn.execute(
            "select id, line_id, number, parent_id, based_on_main_version_id, schema_version,"
            " author_kind, created_at, content_hash, chain_hash, redacted_at is not null"
            " from plytos.card_version where line_id = %s order by number",
            (line.id,),
        ).fetchall()
        return [_version_view(r) for r in rows]

    def verify(self, card_id: UUID) -> list[str]:
        """Recomputes every hash on every line of a card. Returns problems found."""
        problems: list[str] = []
        lines = self._conn.execute(
            "select id from plytos.card_line where card_id = %s", (card_id,)
        ).fetchall()
        if not lines:
            raise CardNotFoundError(str(card_id))
        for (line_id,) in lines:
            previous_chain: bytes | None = None
            rows = self._conn.execute(
                "select id, number, schema_version, based_on_main_version_id, content_hash,"
                " chain_hash, content_ciphertext from plytos.card_version"
                " where line_id = %s order by number",
                (line_id,),
            ).fetchall()
            for vid, number, schema, based_on, stored_content, stored_chain, ct in rows:
                expected = chain_hash(
                    card_id=card_id,
                    line_id=line_id,
                    number=number,
                    schema_version=schema,
                    parent_chain_hash=previous_chain,
                    based_on_main_version_id=based_on,
                    content_hash=bytes(stored_content),
                )
                if expected != bytes(stored_chain):
                    problems.append(f"version {vid} chain hash does not match")
                if ct is not None:
                    raw = self._cipher.decrypt(bytes(ct), _version_aad(vid))
                    if hashlib.sha256(raw).digest() != bytes(stored_content):
                        problems.append(f"version {vid} content hash does not match")
                previous_chain = bytes(stored_chain)
        return problems

    # -- internals -----------------------------------------------------------

    def _line(self, card_id: UUID, target_id: UUID | None) -> _Line:
        row = self._conn.execute(
            "select id, card_id, target_id, head_version_id, state from plytos.card_line"
            " where card_id = %s and target_id is not distinct from %s",
            (card_id, target_id),
        ).fetchone()
        if row is None:
            raise CardNotFoundError(str(card_id))
        return _Line(*row)

    def _version(self, version_id: UUID | None) -> VersionView:
        row = (
            self._conn.execute(
                "select id, line_id, number, parent_id, based_on_main_version_id,"
                " schema_version, author_kind, created_at, content_hash, chain_hash,"
                " redacted_at is not null from plytos.card_version where id = %s",
                (version_id,),
            ).fetchone()
            if version_id
            else None
        )
        if row is None:
            raise CardNotFoundError(str(version_id))
        return _version_view(row)

    def _decrypt(self, version: VersionView) -> bytes:
        row = self._conn.execute(
            "select content_ciphertext from plytos.card_version where id = %s", (version.id,)
        ).fetchone()
        if row is None or row[0] is None:
            raise CardNotFoundError(str(version.id))
        return self._cipher.decrypt(bytes(row[0]), _version_aad(version.id))

    def _main_content(self, version: VersionView) -> MainContent:
        return MainContent.model_validate_json(self._decrypt(version))

    def _main_head(self, card_id: UUID) -> VersionView:
        return self._version(self._line(card_id, None).head_version_id)

    def _check_head(self, line: _Line, base_version_id: UUID) -> None:
        if line.head_version_id != base_version_id:
            raise StaleHeadError(line.head_version_id)

    def _check_claims(self, content: VariantContent, main_head: VersionView) -> None:
        if main_head.redacted:
            raise UnsupportedClaimsError(["the main card's current version was redacted"])
        problems = unsupported_claims(content, self._main_content(main_head))
        if problems:
            raise UnsupportedClaimsError(problems)

    def _append(
        self,
        line: _Line,
        parent: VersionView | None,
        content: MainContent | VariantContent,
        based_on_main_version_id: UUID | None,
        author: Author,
    ) -> VersionView:
        version_id = uuid7()
        number = 1 if parent is None else parent.number + 1
        c_hash = content_hash(content)
        ch_hash = chain_hash(
            card_id=line.card_id,
            line_id=line.id,
            number=number,
            schema_version=SCHEMA_VERSION,
            parent_chain_hash=bytes.fromhex(parent.chain_hash) if parent else None,
            based_on_main_version_id=based_on_main_version_id,
            content_hash=c_hash,
        )
        ciphertext = self._cipher.encrypt(canonical_json(content), _version_aad(version_id))
        try:
            row = self._conn.execute(
                "insert into plytos.card_version (id, owner_id, card_id, line_id, number,"
                " parent_id, based_on_main_version_id, schema_version, author_kind, author_ref,"
                " content_ciphertext, content_hash, chain_hash)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " returning id, line_id, number, parent_id, based_on_main_version_id,"
                " schema_version, author_kind, created_at, content_hash, chain_hash,"
                " redacted_at is not null",
                (
                    version_id,
                    self._user_id,
                    line.card_id,
                    line.id,
                    number,
                    parent.id if parent else None,
                    based_on_main_version_id,
                    SCHEMA_VERSION,
                    author.kind,
                    author.ref,
                    ciphertext,
                    c_hash,
                    ch_hash,
                ),
            ).fetchone()
        except errors.UniqueViolation as exc:
            raise StaleHeadError(None) from exc
        assert row is not None
        moved = self._conn.execute(
            "update plytos.card_line set head_version_id = %s"
            " where id = %s and head_version_id is not distinct from %s",
            (version_id, line.id, parent.id if parent else None),
        )
        if moved.rowcount != 1:
            raise StaleHeadError(None)
        self._event(author, "version.saved", "card_version", version_id)
        return _version_view(row)

    def _event(self, author: Author, action: str, record_type: str, record_id: UUID) -> None:
        self._conn.execute(
            "insert into plytos.event (owner_id, actor_kind, actor_ref, action, record_type,"
            " record_id) values (%s, %s, %s, %s, %s, %s)",
            (self._user_id, author.kind, author.ref, action, record_type, record_id),
        )
