"""Card content, schema version 2.

A card has two kinds of content (docs/data-model.md):

* Facts: what happened. Employer, client, title, dates, numbers, scope,
  evidence links and skill codes. Facts live only on the main line.
* Framing: how it's told. Wording, which facts to show, and their order.
  Variants carry framing only, so they can't change or add a fact.

Cards nest into a career tree. An employment holds its positions, a position
holds its accomplishments, and agency or consulting work puts an engagement
per client in between. Each fact lives at one level and the levels below show
it without copying it. Where a card sits (its parent) is a main-line fact too.

Version 2 added the parent. Version 1 content reads as version 2 with no parent.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION = 2

CardKind = Literal[
    "employment",
    "position",
    "engagement",
    "project",
    "accomplishment",
    "story",
    "skill",
    "education",
    "credential",
    # The flat kind from before the tree. Old cards keep it; new cards don't use it.
    "role",
]
TargetKind = Literal["industry", "company", "role", "application", "custom"]
AuthorKind = Literal["person", "ai", "reviewer"]

# Which kinds a card may sit under. Kinds left out take no parent. Every
# parent ranks above its child, so the tree can't loop. The database enforces
# the same rule (migrations/0003_career_tree.sql).
PARENT_KINDS: dict[str, frozenset[str]] = {
    "position": frozenset({"employment"}),
    "engagement": frozenset({"employment", "position"}),
    "project": frozenset({"employment", "position", "engagement"}),
    "accomplishment": frozenset({"employment", "position", "engagement", "project"}),
    "story": frozenset({"accomplishment"}),
}

FactKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
FactValue = str | int | float | list[str]


def may_sit_under(kind: str, parent_kind: str) -> bool:
    return parent_kind in PARENT_KINDS.get(kind, frozenset())


class Framing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=5000)
    # Fact keys to show, in order. None shows every fact.
    shown_facts: list[FactKey] | None = None


class MainContent(BaseModel):
    """Content of a main-line version: where the card sits, its facts and the
    default framing.

    Conventional fact keys by kind:

    * employment: employer, former_employer (its name before a rename or
      acquisition), employment_type, start, end, location, role_type
    * position: title, plain_title (shown beside the title, never instead),
      start, end, team, location, scope
    * engagement: client, title, start, end
    * accomplishment: figures, workstream, skills, evidence, date

    Dates are YYYY-MM or YYYY, as precise as the person wrote them; an open
    end is "present". Numbers that framing text may cite go in facts too.
    """

    model_config = ConfigDict(extra="forbid")

    parent: UUID | None = None
    facts: dict[FactKey, FactValue] = Field(default_factory=dict)
    framing: Framing


class VariantContent(BaseModel):
    """Content of a variant version: framing only."""

    model_config = ConfigDict(extra="forbid")

    framing: Framing
