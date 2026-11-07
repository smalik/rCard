"""Claude's answers kept by what was asked, for the bench.

A change to what happens after Claude reads a resume (how its answer becomes cards)
can then be scored again on the same answers without asking twice: a question asked
before is answered from the tape at no cost, and one that changed is asked and kept.
Scores of a taped run aren't a fresh sample of Claude's answers, and its cost is only
what was asked anew. A tape holds a real person's words, so it's written readable by
its owner only and stays on that machine.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from anthropic.types import MessageContentParam
from pydantic import BaseModel, ValidationError

from plytos_api.imports.ai import ClaudeReader, Effort
from plytos_api.imports.fidelity.real import write_private


def asked(model: str, effort: str, system: str, content: object, schema: str) -> str:
    """What identifies a question: the same words to the same model, the same way."""
    question = json.dumps([model, effort, system, content, schema], sort_keys=True, default=str)
    return hashlib.sha256(question.encode()).hexdigest()


class TapedReader(ClaudeReader):
    """A Claude reader that answers a question asked before from the tape."""

    def __init__(self, reader: ClaudeReader, tape: Path) -> None:
        super().__init__(reader._client, reader._model, reader._effort)
        self.step_efforts = reader.step_efforts
        self.skip_steps = reader.skip_steps
        self.tape = tape

    def metered(self) -> TapedReader:
        return TapedReader(self, self.tape)

    def ask[T: BaseModel](
        self,
        system: str,
        content: MessageContentParam,
        schema: type[T],
        *,
        step: str,
        effort: Effort | None = None,
        _attempt: int = 1,
    ) -> T | None:
        # A second try is part of the first question's answer.
        if _attempt != 1 or step in self.skip_steps:
            return super().ask(system, content, schema, step=step, effort=effort, _attempt=_attempt)
        how = self.step_efforts.get(step) or effort or self._effort
        kept = self.tape / f"{asked(self._model, how, system, content, schema.__name__)}.json"
        if kept.exists():
            try:
                return schema.model_validate_json(kept.read_text())
            except ValidationError:
                pass  # kept by an older schema: ask again
        answer = super().ask(system, content, schema, step=step, effort=effort)
        if answer is not None:
            write_private(kept, answer.model_dump_json())
        return answer
