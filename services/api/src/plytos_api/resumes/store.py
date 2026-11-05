"""Reads and writes one person's resumes and their versions.

The connection passed in must already be scoped to that person
(Database.as_user), so row-level security limits every query to their rows.

Every save is a new numbered version. Like a card's line, a save names the
version it started from and fails with StaleResumeError if the resume has
moved on since, so an agent and the person can't overwrite each other.
Restoring an old version is a new version with that version's content.

A resume made from another (its parent) records, on each version, which of
the parent's versions it has caught up with. What changed in the parent since
is offered change by change; taking some, or none, catches it up.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors
from pydantic import BaseModel

from plytos_api.cards.hashing import canonical_json, content_hash
from plytos_api.cards.repository import Author, target_aad
from plytos_api.ids import uuid7
from plytos_api.keys import UserCipher
from plytos_api.resumes.model import (
    RESUME_SCHEMA_VERSION,
    ResumeChange,
    ResumeContent,
    ResumeHeader,
    apply,
    diff,
    still_to_take,
)

_ZERO = bytes(32)


class ResumeNotFoundError(Exception):
    pass


class StaleResumeError(Exception):
    """The resume moved on since the version the save started from."""

    def __init__(self, current_head_id: UUID | None) -> None:
        super().__init__("This resume changed since you opened it.")
        self.current_head_id = current_head_id


class ResumeVersionView(BaseModel):
    id: UUID
    number: int
    author_kind: str
    author_ref: str | None
    created_at: datetime
    # The parent resume's version this one has caught up with.
    synced_parent_version_id: UUID | None
    content_hash: str
    chain_hash: str
    redacted: bool
    # Names the person gave it, newest first.
    names: list[str] = []
    note: str | None = None


class ResumeSummary(BaseModel):
    id: UUID
    name: str
    target_id: UUID | None
    target_name: str | None
    parent_id: UUID | None
    import_id: UUID | None
    head_number: int
    created_at: datetime
    updated_at: datetime


class ResumeDetail(ResumeSummary):
    parent_name: str | None
    head: ResumeVersionView
    content: ResumeContent
    versions: list[ResumeVersionView]
    # How many changes in the parent resume this one hasn't taken or passed on.
    parent_changes: int


class ResumeContact(BaseModel):
    """The contact details at the top of a resume, and the version they're from."""

    resume_id: UUID
    resume_name: str
    base_version_id: UUID
    header: ResumeHeader


def resume_chain_hash(
    *,
    resume_id: UUID,
    number: int,
    schema_version: int,
    parent_chain_hash: bytes | None,
    synced_parent_version_id: UUID | None,
    content_hash: bytes,
) -> bytes:
    h = hashlib.sha256(b"plytos.resume_version.v1\n")
    h.update(resume_id.bytes)
    h.update(number.to_bytes(8, "big"))
    h.update(schema_version.to_bytes(2, "big"))
    h.update(parent_chain_hash or _ZERO)
    h.update(synced_parent_version_id.bytes if synced_parent_version_id else _ZERO[:16])
    h.update(content_hash)
    return h.digest()


def _name_aad(resume_id: UUID) -> bytes:
    return b"plytos.resume.name:" + resume_id.bytes


def _version_aad(version_id: UUID) -> bytes:
    return b"plytos.resume_version:" + version_id.bytes


def _version_name_aad(name_id: UUID) -> bytes:
    return b"plytos.resume_version_name:" + name_id.bytes


_VERSION_COLUMNS = (
    "id, number, author_kind, author_ref, created_at, synced_parent_version_id,"
    " content_hash, chain_hash, redacted_at is not null, content_ciphertext, resume_id"
)


class ResumeStore:
    def __init__(
        self,
        conn: psycopg.Connection,
        user_id: UUID,
        cipher: UserCipher,
    ) -> None:
        self._conn = conn
        self._user_id = user_id
        self._cipher = cipher

    # -- writing ---------------------------------------------------------------

    def create(
        self,
        name: str,
        content: ResumeContent,
        author: Author,
        *,
        target_id: UUID | None = None,
        parent_id: UUID | None = None,
        synced_parent_version_id: UUID | None = None,
        import_id: UUID | None = None,
    ) -> ResumeDetail:
        resume_id = uuid7()
        self._conn.execute(
            "insert into plytos.resume (id, owner_id, name_ciphertext, target_id, parent_id,"
            " import_id) values (%s, %s, %s, %s, %s, %s)",
            (
                resume_id,
                self._user_id,
                self._cipher.encrypt(name.encode(), _name_aad(resume_id)),
                target_id,
                parent_id,
                import_id,
            ),
        )
        self._event(author, "resume.created", "resume", resume_id)
        self._append(resume_id, None, content, author, synced_parent_version_id)
        return self.detail(resume_id)

    def save(
        self,
        resume_id: UUID,
        content: ResumeContent,
        base_version_id: UUID,
        author: Author,
    ) -> ResumeDetail:
        """A new version from the person's or an agent's edit. It keeps the
        parent it had caught up with."""
        base = self._head_for_update(resume_id, base_version_id)
        self._append(resume_id, base, content, author, base.synced_parent_version_id)
        return self.detail(resume_id)

    def restore(
        self, resume_id: UUID, number: int, base_version_id: UUID, author: Author
    ) -> ResumeDetail:
        """Brings an earlier version back as a new version. Nothing is lost:
        the versions in between stay in the history."""
        base = self._head_for_update(resume_id, base_version_id)
        old, content = self.version(resume_id, number)
        if old.redacted:
            raise ResumeNotFoundError(f"{resume_id} v{number}")
        restored = content.model_copy(update={"note": f"Back to version {number}"})
        self._append(resume_id, base, restored, author, base.synced_parent_version_id)
        return self.detail(resume_id)

    def name_version(self, resume_id: UUID, number: int, name: str) -> ResumeDetail:
        version, _ = self.version(resume_id, number)
        name_id = uuid7()
        self._conn.execute(
            "insert into plytos.resume_version_name (id, owner_id, version_id, name_ciphertext)"
            " values (%s, %s, %s, %s)",
            (
                name_id,
                self._user_id,
                version.id,
                self._cipher.encrypt(name.encode(), _version_name_aad(name_id)),
            ),
        )
        self._event(Author("person", str(self._user_id)), "resume.named", "resume", resume_id)
        return self.detail(resume_id)

    def rename(self, resume_id: UUID, name: str) -> ResumeDetail:
        moved = self._conn.execute(
            "update plytos.resume set name_ciphertext = %s where id = %s and archived_at is null",
            (self._cipher.encrypt(name.encode(), _name_aad(resume_id)), resume_id),
        )
        if moved.rowcount != 1:
            raise ResumeNotFoundError(str(resume_id))
        return self.detail(resume_id)

    def parent_changes(
        self, resume_id: UUID, parent_version_id: UUID | None = None
    ) -> list[ResumeChange]:
        """What changed in the parent resume since this one last caught up,
        leaving out what this one already reflects. Against the parent as it
        is now, or as it was at `parent_version_id`."""
        theirs = self._parent_at(resume_id, parent_version_id)
        if theirs is None:
            return []
        _, their_content = theirs
        head, mine = self._head_content(resume_id)
        base = (
            self._content(head.synced_parent_version_id)
            if head.synced_parent_version_id
            else ResumeContent()
        )
        return still_to_take(diff(base, their_content), mine, their_content)

    def take(
        self,
        resume_id: UUID,
        keys: Sequence[str],
        base_version_id: UUID,
        author: Author,
        parent_version_id: UUID | None = None,
    ) -> ResumeDetail:
        """Takes the named changes from the parent and catches up with it. With
        no keys, it catches up without taking anything ("not these").

        `parent_version_id` names the parent version the person reviewed. It
        catches up with that version only, so a change made in the parent
        while they were deciding still shows afterwards."""
        theirs = self._parent_at(resume_id, parent_version_id)
        if theirs is None:
            raise ResumeNotFoundError(f"{resume_id} has no parent")
        their_head, their_content = theirs
        base = self._head_for_update(resume_id, base_version_id)
        if base.synced_parent_version_id is not None:
            synced = self._version_view(self._version_row(base.synced_parent_version_id))
            if their_head.number < synced.number:
                raise StaleResumeError(base.id)
        mine = self._content(base.id)
        wanted = set(keys)
        chosen = [c for c in self.parent_changes(resume_id, their_head.id) if c.key in wanted]
        content = apply(mine, their_content, chosen)
        content.note = (
            f"Took {len(chosen)} change{'s' if len(chosen) != 1 else ''} from the resume"
            " it was made from"
            if chosen
            else "Passed on changes in the resume it was made from"
        )
        self._append(resume_id, base, content, author, their_head.id)
        return self.detail(resume_id)

    # -- reading ---------------------------------------------------------------

    def summaries(self) -> list[ResumeSummary]:
        rows = self._conn.execute(
            "select r.id, r.name_ciphertext, r.target_id, r.parent_id, r.import_id,"
            " v.number, r.created_at, v.created_at, t.name_ciphertext"
            " from plytos.resume r join plytos.resume_version v on v.id = r.head_version_id"
            " left join plytos.target t on t.id = r.target_id"
            " where r.archived_at is null order by v.created_at desc"
        ).fetchall()
        return [self._summary(r) for r in rows]

    def latest_contact(self) -> ResumeContact | None:
        """The top of the resume changed most recently, read in one query, for
        the contact card. None when the person has no resume yet."""
        row = self._conn.execute(
            "select r.id, r.name_ciphertext, v.id, v.content_ciphertext"
            " from plytos.resume r join plytos.resume_version v on v.id = r.head_version_id"
            " where r.archived_at is null order by v.created_at desc limit 1"
        ).fetchone()
        if row is None:
            return None
        resume_id, version_id = row[0], row[2]
        content = ResumeContent() if row[3] is None else self._decrypt_content(version_id, row[3])
        return ResumeContact(
            resume_id=resume_id,
            resume_name=self._cipher.decrypt(bytes(row[1]), _name_aad(resume_id)).decode(),
            base_version_id=version_id,
            header=content.header,
        )

    def detail(self, resume_id: UUID) -> ResumeDetail:
        # One trip for the resume, its versions and their names.
        with self._conn.pipeline():
            found = self._conn.execute(
                "select r.id, r.name_ciphertext, r.target_id, r.parent_id, r.import_id,"
                " v.number, r.created_at, v.created_at, t.name_ciphertext"
                " from plytos.resume r join plytos.resume_version v on v.id = r.head_version_id"
                " left join plytos.target t on t.id = r.target_id"
                " where r.id = %s and r.archived_at is null",
                (resume_id,),
            )
            sent = self._send_versions(resume_id)
        row = found.fetchone()
        if row is None:
            raise ResumeNotFoundError(str(resume_id))
        summary = self._summary(row)
        versions, contents = self._version_views(resume_id, *sent)
        head = versions[-1]
        content = contents.get(head.id, ResumeContent())
        parent_name = None
        if summary.parent_id is not None:
            parent = self._conn.execute(
                "select name_ciphertext from plytos.resume where id = %s", (summary.parent_id,)
            ).fetchone()
            if parent is not None:
                parent_name = self._cipher.decrypt(
                    bytes(parent[0]), _name_aad(summary.parent_id)
                ).decode()
        return ResumeDetail(
            **summary.model_dump(),
            parent_name=parent_name,
            head=head,
            content=content,
            versions=versions,
            parent_changes=len(self.parent_changes(resume_id)) if summary.parent_id else 0,
        )

    def version(self, resume_id: UUID, number: int) -> tuple[ResumeVersionView, ResumeContent]:
        for v in self._versions(resume_id):
            if v.number == number:
                content = ResumeContent() if v.redacted else self._content(v.id)
                return v, content
        raise ResumeNotFoundError(f"{resume_id} v{number}")

    def head_version_id(self, resume_id: UUID) -> UUID:
        row = self._conn.execute(
            "select head_version_id from plytos.resume where id = %s and archived_at is null",
            (resume_id,),
        ).fetchone()
        if row is None or row[0] is None:
            raise ResumeNotFoundError(str(resume_id))
        return UUID(str(row[0]))

    def imported(self) -> set[UUID]:
        """The imports a resume was already made from."""
        rows = self._conn.execute(
            "select import_id from plytos.resume where import_id is not null"
            " and archived_at is null"
        ).fetchall()
        return {r[0] for r in rows}

    def verify(self, resume_id: UUID) -> list[str]:
        """Recomputes every version's hashes. Returns the problems found."""
        problems: list[str] = []
        previous: bytes | None = None
        for v in self._versions(resume_id):
            if not v.redacted:
                actual = content_hash(self._content(v.id)).hex()
                if actual != v.content_hash:
                    problems.append(f"version {v.number}: content hash mismatch")
            expected = resume_chain_hash(
                resume_id=resume_id,
                number=v.number,
                schema_version=RESUME_SCHEMA_VERSION,
                parent_chain_hash=previous,
                synced_parent_version_id=v.synced_parent_version_id,
                content_hash=bytes.fromhex(v.content_hash),
            )
            if expected.hex() != v.chain_hash:
                problems.append(f"version {v.number}: chain hash mismatch")
            previous = bytes.fromhex(v.chain_hash)
        return problems

    # -- inside ----------------------------------------------------------------

    def _append(
        self,
        resume_id: UUID,
        parent: ResumeVersionView | None,
        content: ResumeContent,
        author: Author,
        synced_parent_version_id: UUID | None,
    ) -> UUID:
        version_id = uuid7()
        number = 1 if parent is None else parent.number + 1
        c_hash = content_hash(content)
        ch_hash = resume_chain_hash(
            resume_id=resume_id,
            number=number,
            schema_version=RESUME_SCHEMA_VERSION,
            parent_chain_hash=bytes.fromhex(parent.chain_hash) if parent else None,
            synced_parent_version_id=synced_parent_version_id,
            content_hash=c_hash,
        )
        try:
            self._conn.execute(
                "insert into plytos.resume_version (id, owner_id, resume_id, number, parent_id,"
                " synced_parent_version_id, schema_version, author_kind, author_ref,"
                " content_ciphertext, content_hash, chain_hash)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    version_id,
                    self._user_id,
                    resume_id,
                    number,
                    parent.id if parent else None,
                    synced_parent_version_id,
                    RESUME_SCHEMA_VERSION,
                    author.kind,
                    author.ref,
                    self._cipher.encrypt(canonical_json(content), _version_aad(version_id)),
                    c_hash,
                    ch_hash,
                ),
            )
        except errors.UniqueViolation as exc:
            raise StaleResumeError(None) from exc
        moved = self._conn.execute(
            "update plytos.resume set head_version_id = %s"
            " where id = %s and head_version_id is not distinct from %s",
            (version_id, resume_id, parent.id if parent else None),
        )
        if moved.rowcount != 1:
            raise StaleResumeError(None)
        self._event(author, "resume.version_saved", "resume_version", version_id)
        return version_id

    def _head_for_update(self, resume_id: UUID, base_version_id: UUID) -> ResumeVersionView:
        row = self._conn.execute(
            "select head_version_id from plytos.resume where id = %s and archived_at is null"
            " for update",
            (resume_id,),
        ).fetchone()
        if row is None:
            raise ResumeNotFoundError(str(resume_id))
        if row[0] != base_version_id:
            raise StaleResumeError(row[0])
        return self._version_view(self._version_row(base_version_id))

    def _head_content(self, resume_id: UUID) -> tuple[ResumeVersionView, ResumeContent]:
        head = self._version_view(self._version_row(self.head_version_id(resume_id)))
        return head, self._content(head.id)

    def _parent_now(self, resume_id: UUID) -> tuple[ResumeVersionView, ResumeContent] | None:
        row = self._conn.execute(
            "select p.id from plytos.resume r join plytos.resume p on p.id = r.parent_id"
            " where r.id = %s and p.head_version_id is not null",
            (resume_id,),
        ).fetchone()
        if row is None:
            return None
        return self._head_content(row[0])

    def _parent_at(
        self, resume_id: UUID, parent_version_id: UUID | None
    ) -> tuple[ResumeVersionView, ResumeContent] | None:
        """The parent at the version named, or as it is now."""
        if parent_version_id is None:
            return self._parent_now(resume_id)
        row = self._conn.execute(
            "select parent_id from plytos.resume where id = %s", (resume_id,)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        version = self._version_view(self._version_row(parent_version_id))
        if self._version_row(parent_version_id)[10] != row[0]:
            raise ResumeNotFoundError(f"{parent_version_id} isn't a version of the parent")
        return version, self._content(version.id)

    def _versions(self, resume_id: UUID) -> list[ResumeVersionView]:
        with self._conn.pipeline():
            sent = self._send_versions(resume_id)
        return self._version_views(resume_id, *sent)[0]

    def _send_versions(self, resume_id: UUID) -> tuple[psycopg.Cursor[Any], psycopg.Cursor[Any]]:
        """Sends the queries for a resume's versions and their names, so they
        can share a trip; `_version_views` reads them."""
        versions = self._conn.execute(
            f"select {_VERSION_COLUMNS} from plytos.resume_version"  # noqa: S608
            " where resume_id = %s order by number",
            (resume_id,),
        )
        names = self._conn.execute(
            "select n.id, n.version_id, n.name_ciphertext from plytos.resume_version_name n"
            " join plytos.resume_version v on v.id = n.version_id"
            " where v.resume_id = %s order by n.created_at desc",
            (resume_id,),
        )
        return versions, names

    def _version_views(
        self,
        resume_id: UUID,
        versions: psycopg.Cursor[Any],
        names: psycopg.Cursor[Any],
    ) -> tuple[list[ResumeVersionView], dict[UUID, ResumeContent]]:
        """A resume's versions, oldest first, and the content of each one not
        redacted."""
        rows = versions.fetchall()
        if not rows:
            raise ResumeNotFoundError(str(resume_id))
        named: dict[UUID, list[str]] = {}
        for name_id, version_id, blob in names.fetchall():
            named.setdefault(version_id, []).append(
                self._cipher.decrypt(bytes(blob), _version_name_aad(name_id)).decode()
            )
        views = []
        contents: dict[UUID, ResumeContent] = {}
        for r in rows:
            view = self._version_view(r)
            view.names = named.get(view.id, [])
            if not view.redacted and r[9] is not None:
                contents[view.id] = self._decrypt_content(r[0], r[9])
                view.note = contents[view.id].note
            views.append(view)
        return views, contents

    def _version_row(self, version_id: UUID) -> Sequence[Any]:
        row = self._conn.execute(
            f"select {_VERSION_COLUMNS} from plytos.resume_version where id = %s",  # noqa: S608
            (version_id,),
        ).fetchone()
        if row is None:
            raise ResumeNotFoundError(str(version_id))
        return row

    def _content(self, version_id: UUID) -> ResumeContent:
        row = self._version_row(version_id)
        if row[9] is None:
            return ResumeContent()
        return self._decrypt_content(version_id, row[9])

    def _decrypt_content(self, version_id: UUID, blob: Any) -> ResumeContent:
        return ResumeContent.model_validate_json(
            self._cipher.decrypt(bytes(blob), _version_aad(version_id))
        )

    @staticmethod
    def _version_view(r: Sequence[Any]) -> ResumeVersionView:
        return ResumeVersionView(
            id=r[0],
            number=r[1],
            author_kind=r[2],
            author_ref=r[3],
            created_at=r[4],
            synced_parent_version_id=r[5],
            content_hash=bytes(r[6]).hex(),
            chain_hash=bytes(r[7]).hex(),
            redacted=bool(r[8]),
        )

    def _summary(self, r: Sequence[Any]) -> ResumeSummary:
        return ResumeSummary(
            id=r[0],
            name=self._cipher.decrypt(bytes(r[1]), _name_aad(r[0])).decode(),
            target_id=r[2],
            target_name=(
                self._cipher.decrypt(bytes(r[8]), target_aad(r[2])).decode()
                if r[2] and r[8] is not None
                else None
            ),
            parent_id=r[3],
            import_id=r[4],
            head_number=r[5],
            created_at=r[6],
            updated_at=r[7],
        )

    def _event(self, author: Author, action: str, record_type: str, record_id: UUID) -> None:
        self._conn.execute(
            "insert into plytos.event (owner_id, actor_kind, actor_ref, action, record_type,"
            " record_id) values (%s, %s, %s, %s, %s, %s)",
            (self._user_id, author.kind, author.ref, action, record_type, record_id),
        )
