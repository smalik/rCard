"""Resume content, schema version 1.

A resume is a selection over the person's cards (docs/data-model.md):

* entries: the employments it shows, in order. Each lists the
  accomplishments switched on under it, in order, from anywhere in that
  employment's branch of the career tree. Its positions and client work show
  as headings; ``fold_earlier`` folds every title but the latest into one line.
* context: cards outside the career tree that come along, such as a summary,
  education, credentials, skills and activities.

Each item names its wording: ``auto`` uses the wording made for the resume's
target, or for the target it was made from, and the card's own wording
otherwise; ``main`` always uses the card's own wording, and a target ID picks
that target's wording. When the person rewords a line inside the resume, the
item also pins the card version it was given (``version``), so that version
of the resume keeps that exact wording and restoring it brings the wording
back. Facts always come from the card as it is now: a corrected fact shows at
once in every resume.

An employment left out of ``entries`` is left out of the resume; the cards
stay in the person's library either way.

``header`` is the top of the page: name, contact details and a short summary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RESUME_SCHEMA_VERSION = 1

Wording = Literal["auto", "main"] | UUID

# Kinds that head an entry: an employment, or a flat role card from before
# the career tree.
ENTRY_KINDS = frozenset({"employment", "role"})
# Kinds switched on and off under an employment. Positions and client work
# are the employment's structure and show as headings instead.
ITEM_KINDS = frozenset({"accomplishment", "project"})
# Kinds that come along as context: anything outside the career tree.
CONTEXT_KINDS = frozenset(
    {"story", "skill", "education", "credential", "activity", "project", "accomplishment"}
)


class ResumeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: UUID
    wording: Wording = "auto"
    # The card version this resume pinned when the person reworded the line here.
    version: UUID | None = None


class ResumeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: UUID
    fold_earlier: bool = False
    items: list[ResumeItem] = Field(default_factory=list)


class ResumeHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=120)
    # A line under the name, such as "Operations manager · Logistics".
    headline: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=60)
    location: str = Field(default="", max_length=120)
    links: list[str] = Field(default_factory=list, max_length=5)
    summary: str = Field(default="", max_length=1500)


class ResumeContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: ResumeHeader = Field(default_factory=ResumeHeader)
    entries: list[ResumeEntry] = Field(default_factory=list)
    context: list[ResumeItem] = Field(default_factory=list)
    # What this version did that a list of changes can't show, such as
    # "Back to version 2".
    note: str | None = Field(default=None, max_length=200)


ChangeKind = Literal[
    "header",
    "entry_added",
    "entry_removed",
    "fold",
    "item_added",
    "item_removed",
    "wording",
    "context_added",
    "context_removed",
]


class ResumeChange(BaseModel):
    """One change in a parent resume that a resume made from it hasn't taken.
    ``key`` names it when the person takes it."""

    key: str
    kind: ChangeKind
    card: UUID
    # The employment an item or fold change is under; None for context.
    employment: UUID | None = None
    wording: Wording | None = None
    version: UUID | None = None
    fold_earlier: bool | None = None


def keep_wording(content: ResumeContent, target_id: UUID) -> ResumeContent:
    """The same content, with each line that followed its resume's target
    pinned to that target's wording, so a copy made for another target reads
    the same until the person changes it."""
    out = content.model_copy(deep=True)
    for item in [i for e in out.entries for i in e.items] + list(out.context):
        if item.wording == "auto" and item.version is None:
            item.wording = target_id
    return out


def _key(kind: str, card: UUID) -> str:
    return f"{kind}:{card}"


def diff(base: ResumeContent, head: ResumeContent) -> list[ResumeChange]:
    """What changed from ``base`` to ``head``, item by item. Reordering isn't
    reported: a branch keeps its own order."""
    changes: list[ResumeChange] = []
    if base.header != head.header:
        # The header has no card; the key just needs to be stable.
        changes.append(ResumeChange(key="header", kind="header", card=UUID(int=0)))
    before = {e.card: e for e in base.entries}
    after = {e.card: e for e in head.entries}
    for card, entry in after.items():
        old = before.get(card)
        if old is None:
            changes.append(
                ResumeChange(key=_key("entry_added", card), kind="entry_added", card=card)
            )
            continue
        if old.fold_earlier != entry.fold_earlier:
            changes.append(
                ResumeChange(
                    key=_key("fold", card),
                    kind="fold",
                    card=card,
                    employment=card,
                    fold_earlier=entry.fold_earlier,
                )
            )
        changes += _item_changes(old.items, entry.items, card)
    for card in before:
        if card not in after:
            changes.append(
                ResumeChange(key=_key("entry_removed", card), kind="entry_removed", card=card)
            )
    changes += _item_changes(base.context, head.context, None)
    return changes


def _item_changes(
    old: list[ResumeItem], new: list[ResumeItem], employment: UUID | None
) -> list[ResumeChange]:
    added, removed = (
        ("item_added", "item_removed") if employment else ("context_added", "context_removed")
    )
    was = {i.card: i for i in old}
    now = {i.card: i for i in new}
    out: list[ResumeChange] = []
    for card, item in now.items():
        if card not in was:
            out.append(
                ResumeChange(
                    key=_key(added, card),
                    kind=added,  # type: ignore[arg-type]
                    card=card,
                    employment=employment,
                    wording=item.wording,
                    version=item.version,
                )
            )
        elif (was[card].wording, was[card].version) != (item.wording, item.version):
            out.append(
                ResumeChange(
                    key=_key("wording", card),
                    kind="wording",
                    card=card,
                    employment=employment,
                    wording=item.wording,
                    version=item.version,
                )
            )
    for card in was:
        if card not in now:
            out.append(
                ResumeChange(
                    key=_key(removed, card),
                    kind=removed,  # type: ignore[arg-type]
                    card=card,
                    employment=employment,
                )
            )
    return out


def still_to_take(
    changes: list[ResumeChange], mine: ResumeContent, theirs: ResumeContent
) -> list[ResumeChange]:
    """Drops changes this resume already reflects, and changes inside an
    employment it leaves out. ``theirs`` is the parent's content now."""
    entries = {e.card: e for e in mine.entries}
    context = {i.card: i for i in mine.context}
    out: list[ResumeChange] = []
    for change in changes:
        if change.kind == "header":
            if mine.header != theirs.header:
                out.append(change)
            continue
        if change.kind == "entry_added" and change.card in entries:
            continue
        if change.kind == "entry_removed" and change.card not in entries:
            continue
        if change.employment is not None:
            entry = entries.get(change.employment)
            if entry is None:
                continue
            items = {i.card: i for i in entry.items}
            if change.kind == "fold" and entry.fold_earlier == change.fold_earlier:
                continue
            if change.kind == "item_added" and change.card in items:
                continue
            if change.kind == "item_removed" and change.card not in items:
                continue
            if change.kind == "wording" and (
                change.card not in items
                or (items[change.card].wording, items[change.card].version)
                == (change.wording, change.version)
            ):
                continue
        else:
            if change.kind == "context_added" and change.card in context:
                continue
            if change.kind == "context_removed" and change.card not in context:
                continue
            if change.kind == "wording" and (
                change.card not in context
                or (context[change.card].wording, context[change.card].version)
                == (change.wording, change.version)
            ):
                continue
        out.append(change)
    return out


def apply(mine: ResumeContent, theirs: ResumeContent, take: list[ResumeChange]) -> ResumeContent:
    """Applies the taken changes from the parent's content ``theirs`` to this
    resume's content. Added things land next to where the parent has them."""
    result = mine.model_copy(deep=True)
    for change in take:
        if change.kind == "header":
            result.header = theirs.header.model_copy(deep=True)
        elif change.kind == "entry_added":
            entry = next(e for e in theirs.entries if e.card == change.card)
            order = [e.card for e in theirs.entries]
            _insert(result.entries, entry.model_copy(deep=True), order, lambda e: e.card)
        elif change.kind == "entry_removed":
            result.entries = [e for e in result.entries if e.card != change.card]
        elif change.employment is not None:
            entry = next(e for e in result.entries if e.card == change.employment)
            source = next((e for e in theirs.entries if e.card == change.employment), None)
            order = [i.card for i in source.items] if source else []
            _change_items(entry.items, change, order)
            if change.kind == "fold" and change.fold_earlier is not None:
                entry.fold_earlier = change.fold_earlier
        else:
            _change_items(result.context, change, [i.card for i in theirs.context])
    return result


def _change_items(items: list[ResumeItem], change: ResumeChange, order: list[UUID]) -> None:
    if change.kind in ("item_added", "context_added"):
        item = ResumeItem(
            card=change.card, wording=change.wording or "auto", version=change.version
        )
        _insert(items, item, order, lambda i: i.card)
    elif change.kind in ("item_removed", "context_removed"):
        items[:] = [i for i in items if i.card != change.card]
    elif change.kind == "wording" and change.wording is not None:
        for item in items:
            if item.card == change.card:
                item.wording = change.wording
                item.version = change.version


def _insert[T](items: list[T], new: T, order: list[UUID], card_of: Callable[[T], UUID]) -> None:
    """Puts ``new`` after the nearest item that comes before it in ``order``."""
    target = card_of(new)
    ahead = set(order[: order.index(target)]) if target in order else set()
    position = 0
    for i, item in enumerate(items):
        if card_of(item) in ahead:
            position = i + 1
    items.insert(position, new)
