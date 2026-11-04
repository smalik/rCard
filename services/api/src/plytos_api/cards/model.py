"""Card content, schema version 1.

A card has two kinds of content (docs/data-model.md):

* Facts: what happened. Employer, client and agency, title, dates, numbers,
  scope, evidence links and skill codes. Facts live only on the main line.
* Framing: how it's told. Wording, which facts to show, and their order.
  Variants carry framing only, so they can't change or add a fact.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION = 1

CardKind = Literal["role", "accomplishment", "skill", "project", "education", "credential", "story"]
TargetKind = Literal["industry", "company", "role", "application", "custom"]
AuthorKind = Literal["person", "ai", "reviewer"]

FactKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
FactValue = str | int | float | list[str]


class Framing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=5000)
    # Fact keys to show, in order. None shows every fact.
    shown_facts: list[FactKey] | None = None


class MainContent(BaseModel):
    """Content of a main-line version: the facts and the default framing.

    Conventional fact keys: employer, client, agency, title, plain_title,
    start, end (YYYY-MM), location, scope, skills, evidence. Numbers that
    framing text may cite go in facts too, for example revenue_growth: "18%".
    """

    model_config = ConfigDict(extra="forbid")

    facts: dict[FactKey, FactValue] = Field(default_factory=dict)
    framing: Framing


class VariantContent(BaseModel):
    """Content of a variant version: framing only."""

    model_config = ConfigDict(extra="forbid")

    framing: Framing
