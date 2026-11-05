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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg import errors
from pydantic import BaseModel

from plytos_api.cards.hashing import canonical_json, chain_hash, content_hash
from plytos_api.cards.model import (
    SCHEMA_VERSION,
    AuthorKind,
    CardKind,
    Framing,
    MainContent,
    TargetKind,
    VariantContent,
    may_sit_under,
)
from plytos_api.cards.rules import (
    SUMMARIZER_REF,
    facts_changed,
    has_headline,
    honest_marks,
    unsupported_claims,
)
from plytos_api.ids import uuid7
from plytos_api.keys import UserCipher

CardStatus = Literal["draft", "approved"]

# Kinds whose changes can change what a job's headline and stories sum up:
# what was done, whenever it changes, and the job and its titles when made.
_SUMMED_UP = frozenset({"accomplishment", "project"})
_HOLDERS = frozenset({"employment", "position", "engagement"})


def _handed_back(kind: str, before: MainContent | None, after: MainContent) -> bool:
    """Whether a save emptied the part Plytos writes on this card: a job's
    headline, or a title's story."""
    if before is None:
        return False
    if kind == "employment":
        return has_headline(before) and not has_headline(after)
    return bool(before.framing.body.strip()) and not after.framing.body.strip()


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


class ParentError(Exception):
    """The card can't sit where it was put: the parent is missing or of a kind
    that can't hold it (an accomplishment under a skill, say)."""


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
    parent_id: UUID | None
    main: LineView
    variants: list[LineView]


class CardSummary(BaseModel):
    id: UUID
    kind: CardKind
    status: str
    parent_id: UUID | None
    headline: str | None
    main_version: int
    variants: int
    variants_behind: int


class LibraryCard(BaseModel):
    """One card as the library shows it: where it sits, its current main
    content, and how fresh it is. Content is None once redacted."""

    id: UUID
    kind: CardKind
    status: str
    parent_id: UUID | None
    # The person's own order among the card's siblings; None sorts last.
    sort_key: int | None
    created_at: datetime
    content: MainContent | None
    # The main line's head: what an edit saves on top of.
    version_id: UUID
    version: int
    version_author: AuthorKind
    updated_at: datetime
    variants: int
    variants_behind: int
    # A job Plytos is about to sum up, or summing up now: its headline and
    # stories may change in a moment.
    writing: bool = False


class CardOrderError(Exception):
    """The cards to order aren't exactly the person's cards under one parent."""


@dataclass(frozen=True)
class CardText:
    """A card's kind, place and current main content."""

    kind: CardKind
    parent_id: UUID | None
    content: MainContent


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


def version_aad(version_id: UUID) -> bytes:
    return b"plytos.card_version:" + version_id.bytes


def target_aad(target_id: UUID) -> bytes:
    return b"plytos.target:" + target_id.bytes


class CardRepository:
    def __init__(
        self,
        conn: psycopg.Connection,
        user_id: UUID,
        cipher: UserCipher,
        *,
        on_job_changed: Callable[[UUID], None] | None = None,
    ) -> None:
        self._conn = conn
        self._user_id = user_id
        self._cipher = cipher
        # Told the employment whenever what its headline and stories sum up
        # may have changed, so they can be written again.
        self._on_job_changed = on_job_changed

    # -- cards and main line -------------------------------------------------

    def create_card(
        self,
        kind: CardKind,
        content: MainContent,
        author: Author,
        *,
        status: CardStatus = "draft",
    ) -> CardDetail:
        self._check_parent(kind, content.parent)
        content = honest_marks(None, content, by_summarizer=False)
        card_id = uuid7()
        line_id = uuid7()
        self._conn.execute(
            "insert into plytos.card (id, owner_id, kind, status, parent_id)"
            " values (%s, %s, %s, %s, %s)",
            (card_id, self._user_id, kind, status, content.parent),
        )
        self._conn.execute(
            "insert into plytos.card_line (id, owner_id, card_id) values (%s, %s, %s)",
            (line_id, self._user_id, card_id),
        )
        line = _Line(line_id, card_id, None, None, "current")
        self._append(line, None, content, None, author)
        self._event(author, "card.created", "card", card_id)
        if kind in _SUMMED_UP or kind in _HOLDERS:
            self._job_changed(card_id)
        return self.card_detail(card_id)

    def save_main_version(
        self, card_id: UUID, base_version_id: UUID, content: MainContent, author: Author
    ) -> SaveResult:
        line = self._line(card_id, None)
        self._check_head(line, base_version_id)
        parent = self._version(base_version_id)
        before = None if parent.redacted else self._main_content(parent)
        kind, sits_under = self._card_place(card_id)
        moved = content.parent != sits_under
        if moved:
            self._check_parent(kind, content.parent)
        by_summarizer = author.kind == "ai" and author.ref == SUMMARIZER_REF
        content = honest_marks(before, content, by_summarizer=by_summarizer)
        version = self._append(line, parent, content, None, author)
        if moved:
            # The version above records the move; this keeps the clear mirror in step.
            self._conn.execute(
                "update plytos.card set parent_id = %s where id = %s", (content.parent, card_id)
            )
            self._event(author, "card.moved", "card", card_id)
            if sits_under is not None:
                # What it sat under lost it, so a summary written there may be out of date.
                self._event(author, "card.moved_out", "card", sits_under)

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
        if not by_summarizer and kind in _SUMMED_UP:
            self._job_changed(card_id)
            if moved and sits_under is not None:
                self._job_changed(sits_under)
        elif not by_summarizer and kind in _HOLDERS and _handed_back(kind, before, content):
            # The person emptied a headline or story: Plytos writes it again.
            self._job_changed(card_id)
        return SaveResult(version=version, variants_marked_behind=behind)

    def last_moved_out(self, card_ids: list[UUID]) -> dict[UUID, datetime]:
        """When each of these cards last lost something that sat under it."""
        if not card_ids:
            return {}
        rows = self._conn.execute(
            "select record_id, max(occurred_at) from plytos.event"
            " where action = 'card.moved_out' and record_type = 'card' and record_id = any(%s)"
            " group by record_id",
            (card_ids,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def employment_of(self, card_id: UUID) -> UUID | None:
        """The employment a card sits under, or is, if any."""
        row = self._conn.execute(
            "with recursive up (id, kind, parent_id, depth) as ("
            "  select id, kind, parent_id, 0 from plytos.card where id = %s"
            "  union all"
            "  select c.id, c.kind, c.parent_id, up.depth + 1 from plytos.card c"
            "  join up on c.id = up.parent_id where up.depth < 8"
            ") select id from up where kind = 'employment' order by depth limit 1",
            (card_id,),
        ).fetchone()
        return row[0] if row else None

    def _job_changed(self, card_id: UUID) -> None:
        if self._on_job_changed is None:
            return
        employment = self.employment_of(card_id)
        if employment is not None:
            self._on_job_changed(employment)

    # -- targets and variants ------------------------------------------------

    def create_target(self, kind: TargetKind, name: str, parent_id: UUID | None) -> TargetView:
        if parent_id is not None:
            parent = self._conn.execute(
                "select 1 from plytos.target where id = %s", (parent_id,)
            ).fetchone()
            if parent is None:
                raise CardNotFoundError(str(parent_id))
        target_id = uuid7()
        ciphertext = self._cipher.encrypt(name.encode(), target_aad(target_id))
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
                name=self._cipher.decrypt(bytes(r[3]), target_aad(r[0])).decode(),
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
            "    where x.card_id = c.id and x.state = 'behind'),"
            "  c.parent_id"
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
                    self._cipher.decrypt(bytes(r[5]), version_aad(r[3]))
                )
                headline = content.framing.headline
            summaries.append(
                CardSummary(
                    id=r[0],
                    kind=r[1],
                    status=r[2],
                    parent_id=r[8],
                    headline=headline,
                    main_version=r[4],
                    variants=r[6],
                    variants_behind=r[7],
                )
            )
        return summaries

    def library(self) -> list[LibraryCard]:
        """Every card the person keeps, with its current main content, in one
        query, ordered as the person placed them among their siblings."""
        rows = self._conn.execute(
            "select c.id, c.kind, c.status, c.parent_id, c.sort_key, c.created_at,"
            "  v.id, v.number, v.author_kind, v.created_at, v.content_ciphertext,"
            "  (select count(*) from plytos.card_line x"
            "    where x.card_id = c.id and x.target_id is not null),"
            "  (select count(*) from plytos.card_line x"
            "    where x.card_id = c.id and x.state = 'behind')"
            " from plytos.card c"
            " join plytos.card_line l on l.card_id = c.id and l.target_id is null"
            " join plytos.card_version v on v.id = l.head_version_id"
            " where c.status <> 'archived'"
            " order by c.sort_key nulls last, c.created_at, c.id"
        ).fetchall()
        return [
            LibraryCard(
                id=r[0],
                kind=r[1],
                status=r[2],
                parent_id=r[3],
                sort_key=r[4],
                created_at=r[5],
                content=None
                if r[10] is None
                else MainContent.model_validate_json(
                    self._cipher.decrypt(bytes(r[10]), version_aad(r[6]))
                ),
                version_id=r[6],
                version=r[7],
                version_author=r[8],
                updated_at=r[9],
                variants=r[11],
                variants_behind=r[12],
            )
            for r in rows
        ]

    def reorder(self, parent_id: UUID | None, card_ids: Sequence[UUID], author: Author) -> None:
        """Puts some of the person's cards under one parent (or at the top of
        the tree) in the given order, each named once. Siblings left out keep
        their places."""
        rows = self._conn.execute(
            "select id from plytos.card"
            " where parent_id is not distinct from %s and status <> 'archived'"
            "   and id = any(%s)",
            (parent_id, list(card_ids)),
        ).fetchall()
        if len(set(card_ids)) != len(card_ids) or {r[0] for r in rows} != set(card_ids):
            raise CardOrderError("Those cards don't all sit in that place any more.")
        for position, card_id in enumerate(card_ids):
            self._conn.execute(
                "update plytos.card set sort_key = %s where id = %s", (position, card_id)
            )
        if card_ids:
            self._event(author, "cards.reordered", "card", card_ids[0])

    def main_contents(self) -> dict[UUID, CardText]:
        """Every card's kind, place and current main content, in one query. For
        building a whole resume at once."""
        rows = self._conn.execute(
            "select c.id, c.kind, c.parent_id, v.id, v.content_ciphertext"
            " from plytos.card c"
            " join plytos.card_line l on l.card_id = c.id and l.target_id is null"
            " join plytos.card_version v on v.id = l.head_version_id"
            " where c.status <> 'archived' and v.content_ciphertext is not null"
        ).fetchall()
        return {
            r[0]: CardText(
                kind=r[1],
                parent_id=r[2],
                content=MainContent.model_validate_json(
                    self._cipher.decrypt(bytes(r[4]), version_aad(r[3]))
                ),
            )
            for r in rows
        }

    def variant_framings(self, target_id: UUID) -> dict[UUID, Framing]:
        """The current wording each card has for one target, by card."""
        rows = self._conn.execute(
            "select l.card_id, v.id, v.content_ciphertext from plytos.card_line l"
            " join plytos.card_version v on v.id = l.head_version_id"
            " where l.target_id = %s and v.content_ciphertext is not null",
            (target_id,),
        ).fetchall()
        return {
            r[0]: VariantContent.model_validate_json(
                self._cipher.decrypt(bytes(r[2]), version_aad(r[1]))
            ).framing
            for r in rows
        }

    def version_framings(self, version_ids: Sequence[UUID]) -> dict[UUID, Framing]:
        """The wording of particular card versions, main or variant, by version."""
        if not version_ids:
            return {}
        rows = self._conn.execute(
            "select v.id, l.target_id, v.content_ciphertext from plytos.card_version v"
            " join plytos.card_line l on l.id = v.line_id"
            " where v.id = any(%s) and v.content_ciphertext is not null",
            (list(version_ids),),
        ).fetchall()
        out: dict[UUID, Framing] = {}
        for version_id, target_id, blob in rows:
            raw = self._cipher.decrypt(bytes(blob), version_aad(version_id))
            out[version_id] = (
                MainContent.model_validate_json(raw).framing
                if target_id is None
                else VariantContent.model_validate_json(raw).framing
            )
        return out

    def card_detail(self, card_id: UUID) -> CardDetail:
        card = self._conn.execute(
            "select kind, status, trust_level, created_at, parent_id from plytos.card"
            " where id = %s",
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
            parent_id=card[4],
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
                    raw = self._cipher.decrypt(bytes(ct), version_aad(vid))
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
        return self._cipher.decrypt(bytes(row[0]), version_aad(version.id))

    def _main_content(self, version: VersionView) -> MainContent:
        return MainContent.model_validate_json(self._decrypt(version))

    def _card_place(self, card_id: UUID) -> tuple[str, UUID | None]:
        row = self._conn.execute(
            "select kind, parent_id from plytos.card where id = %s", (card_id,)
        ).fetchone()
        if row is None:
            raise CardNotFoundError(str(card_id))
        return row[0], row[1]

    def _check_parent(self, kind: str, parent_id: UUID | None) -> None:
        """Explains a bad placement before the database refuses it."""
        if parent_id is None:
            return
        row = self._conn.execute(
            "select kind from plytos.card where id = %s", (parent_id,)
        ).fetchone()
        if row is None:
            raise ParentError("The card it should sit under doesn't exist.")
        if not may_sit_under(kind, row[0]):
            raise ParentError(f"A {kind} card can't sit under a {row[0]} card.")

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
        ciphertext = self._cipher.encrypt(canonical_json(content), version_aad(version_id))
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
