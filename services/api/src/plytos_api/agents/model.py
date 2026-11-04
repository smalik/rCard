"""What the agents read and write.

The conversation is made of messages. Work news in a message becomes a
tidbit, which the Listener reads once and files under the job it belongs to.
Agents offer what they make as proposals; Plytos's message offering one
points at it, so the conversation shows it in place.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from plytos_api.cards.model import CardKind, MainContent

AgentName = Literal[
    "check_in",
    "listener",
    "stitcher",
    "fact_checker",
    "connector",
    "strategist",
    "scout",
    "assembler",
    "critic",
]
ProposalKind = Literal["new_card", "card_version", "variant", "resume", "question", "insight"]
ProposalState = Literal["open", "kept", "edited", "dismissed", "superseded"]
TriggerKind = Literal["message", "tidbit", "card", "schedule"]
RunState = Literal["queued", "running", "done", "failed"]
Channel = Literal["app", "text_message", "email"]
TidbitKind = Literal["text", "voice", "photo"]

MAX_MESSAGE = 4000


class Reading(BaseModel):
    """What the Listener found in a tidbit, beside the original."""

    model_config = ConfigDict(extra="forbid")

    # One line in the person's own terms, for lists and for other agents.
    summary: str = Field(max_length=300)
    projects: list[str] = Field(default_factory=list, max_length=10)
    # Figures exactly as the person wrote them ("12", "18%", "$1.2M").
    figures: list[str] = Field(default_factory=list, max_length=20)
    # Whether it says how things turned out, not only what was done.
    has_outcome: bool = False


class NewCard(BaseModel):
    """A card an agent proposes. It sits where `content.parent` says."""

    model_config = ConfigDict(extra="forbid")

    kind: CardKind
    content: MainContent
    # What it still needs from the person, if anything ("did late shipments drop?").
    missing: str | None = Field(default=None, max_length=300)


class ProposalBody(BaseModel):
    """A proposal's encrypted content."""

    model_config = ConfigDict(extra="forbid")

    # What Plytos says when it offers this, in the conversation.
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)
    card: NewCard | None = None


class ProposalView(BaseModel):
    id: UUID
    agent: AgentName
    kind: ProposalKind
    state: ProposalState
    card_id: UUID | None
    cites: list[UUID]
    body: ProposalBody
    created_at: datetime
    decided_at: datetime | None
    result_version_id: UUID | None


class MessageView(BaseModel):
    id: UUID
    author: Literal["person", "plytos"]
    channel: Channel
    text: str
    created_at: datetime
    proposal: ProposalView | None = None
    # A resume shared in the conversation, while its import is kept.
    import_id: UUID | None = None


class TidbitView(BaseModel):
    id: UUID
    kind: TidbitKind
    said_at: datetime
    text: str
    message_id: UUID | None
    card_id: UUID | None
    reading: Reading | None
    read_at: datetime | None
    created_at: datetime


class RunView(BaseModel):
    """One agent run, for "how I got here". Never content."""

    id: UUID
    agent: AgentName
    trigger_kind: TriggerKind
    trigger_id: UUID | None
    state: RunState
    attempts: int
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
