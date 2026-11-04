"""How agents ask a model for structured answers.

An agent hands over instructions, the slice of the person's data it needs,
and the shape of the answer, and gets back a checked answer or None. The
person's words go to the model provider, so nothing here logs them: failures
are logged by error class only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

Effort = Literal["low", "medium", "high", "xhigh", "max"]
T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    """What a run spent, added up across its calls."""

    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class Thinker(Protocol):
    def think(self, system: str, prompt: str, answer: type[T], usage: Usage) -> T | None: ...


class ClaudeThinker:
    """Asks Claude for JSON that matches the answer model."""

    def __init__(
        self,
        client: anthropic.Anthropic | anthropic.AnthropicVertex,
        model: str,
        effort: Effort,
        max_tokens: int = 8000,
    ) -> None:
        self._client = client
        self._model = model
        self._effort: Effort = effort
        self._max_tokens = max_tokens

    def think(self, system: str, prompt: str, answer: type[T], usage: Usage) -> T | None:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=answer,
                output_config={"effort": self._effort},
            )
        except anthropic.APIError as exc:
            log.warning("An agent's call to Claude failed: %s", type(exc).__name__)
            return None
        except ValidationError as exc:
            log.warning("Claude's answer didn't match the schema: %s", type(exc).__name__)
            return None
        usage.model = self._model
        usage.input_tokens += response.usage.input_tokens
        usage.output_tokens += response.usage.output_tokens
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            log.warning("Claude stopped without an answer: %s", response.stop_reason)
            return None
        return response.parsed_output


def thinker_for(
    provider: str, model: str, effort: Effort, vertex_project: str, vertex_region: str
) -> Thinker | None:
    """The thinker the settings ask for, or None when AI is off."""
    if provider == "off":
        return None
    if provider == "anthropic":
        return ClaudeThinker(anthropic.Anthropic(timeout=90, max_retries=1), model, effort)
    if provider == "vertex":
        client = anthropic.AnthropicVertex(
            project_id=vertex_project, region=vertex_region, timeout=90, max_retries=1
        )
        return ClaudeThinker(client, model, effort)
    raise ValueError("PLYTOS_AI_PROVIDER must be off, anthropic or vertex")
