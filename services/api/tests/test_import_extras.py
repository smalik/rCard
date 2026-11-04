"""Facts pulled out of each accomplishment (imports/facts.py) and proofreading
(imports/proofread.py), without calling Claude. The resumes are made up
(tests/resume_samples.py), and a fake reader stands in for Claude."""

import json
from datetime import date
from typing import Any

import anthropic
import httpx2

from plytos_api.imports.ai import (
    FACTS_INSTRUCTIONS,
    AiFacts,
    AiProofread,
    AiResume,
    ClaudeReader,
)
from plytos_api.imports.extract import extract
from plytos_api.imports.model import ExtractedDocument, ImportResult
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.proofread import proofread_findings
from plytos_api.imports.segment import segment
from tests.resume_samples import stint_text
from tests.test_import_lines import reading

TODAY = date(2026, 11, 4)


class FakeReader:
    """Reads the structure from a fixed reading, and answers the side passes as told."""

    name = "fake-model"

    def __init__(
        self,
        found: dict[str, Any] | None,
        facts: Any = None,
        typos: list[dict[str, Any]] | None = None,
    ) -> None:
        self.found = found
        self.facts = facts
        self.typos = typos
        self.asked: list[list[tuple[str, str]]] = []

    def read(self, doc: ExtractedDocument) -> AiResume | None:
        return AiResume.model_validate(self.found) if self.found is not None else None

    def read_facts(self, results: list[tuple[str, str]]) -> AiFacts | None:
        self.asked.append(results)
        if isinstance(self.facts, Exception):
            raise self.facts
        if self.facts is None:
            return None
        return AiFacts.model_validate({"results": self.facts(results)})

    def proofread(self, doc: ExtractedDocument) -> AiProofread | None:
        if self.typos is None:
            return None
        return AiProofread.model_validate({"typos": self.typos})


def _ref(results: list[tuple[str, str]], words: str) -> str:
    return next(ref for ref, text in results if words in text)


def _facts(results: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """What a reader might say: some facts in the words, some not."""
    return [
        {
            "result": _ref(results, "ER wait"),
            "skills": ["patient access", "Epic"],  # neither is in the words
            "scope": ["across 4 sites"],
            "outcome": "Cut average ER wait times by 18%",
        },
        {
            "result": _ref(results, "billing").lower(),
            "skills": ["billing", "Billing"],
            "scope": ["3 clinics", "$2.4M a year"],
            "outcome": "",
        },
        {"result": "R99", "skills": ["Python"], "scope": [], "outcome": ""},
    ]


def _import(reader: FakeReader) -> ImportResult:
    return import_resume(stint_text().encode(), "jordan.txt", today=TODAY, reader=reader)


def _card(result: ImportResult, words: str) -> Any:
    return next(c for c in result.cards if words in c.content.framing.headline)


def test_facts_are_kept_only_when_the_accomplishment_says_them() -> None:
    reader = FakeReader(reading(), facts=_facts)
    result = _import(reader)

    sent = reader.asked[0]
    assert [text for _, text in sent] == [
        "Cut average ER wait times by 18% across 4 sites.",
        "Rebuilt the scheduling team and hired 14 coordinators.",
        "Trained 30 registrars on the new intake system.",
        "Ran billing for 3 clinics, collecting $2.4M a year.",
    ]
    er = _card(result, "ER wait").content.facts
    assert "skills" not in er
    assert er["scope"] == ["across 4 sites"]
    assert er["outcome"] == "Cut average ER wait times by 18%"
    assert er["figures"] == ["18%", "4"]
    billing = _card(result, "billing").content.facts
    assert billing["skills"] == ["billing"]
    assert billing["scope"] == ["3 clinics", "$2.4M a year"]
    assert "outcome" not in billing
    assert "skills" not in _card(result, "registrars").content.facts


def test_the_import_goes_on_when_a_side_pass_fails() -> None:
    result = _import(FakeReader(reading(), facts=RuntimeError("boom")))
    assert result.read_by == "fake-model"
    assert "scope" not in _card(result, "billing").content.facts


def test_no_facts_are_asked_for_when_the_rules_read_the_resume() -> None:
    reader = FakeReader(None, facts=_facts)
    _import(reader)
    assert reader.asked == []


def test_typos_are_kept_only_when_quoted_from_their_line() -> None:
    typo = {"line": 13, "kind": "grammar", "quote": "Ran billing", "suggestion": "Ran the billing"}
    typos = [
        typo,
        dict(typo),  # the same typo twice
        {**typo, "quote": "Ran bilING"},  # not on the line as written
        {**typo, "line": 99},  # no such line
        {**typo, "suggestion": "Ran billing"},  # no change
        {**typo, "quote": "x" * 200},
    ]
    result = _import(FakeReader(reading(), typos=typos))
    found = [f for f in result.findings if f.rule == "content.proofread"]
    assert len(found) == 1
    assert found[0].about == "cards" and found[0].severity == "improve"
    assert found[0].title == "Check the grammar in “Ran billing”"
    assert found[0].detail.startswith("Did you mean “Ran the billing”?")
    assert [(loc.block, loc.excerpt) for loc in found[0].locations] == [(13, "Ran billing")]


def test_proofreading_runs_without_a_structure_reading_too() -> None:
    typos = [{"line": 13, "kind": "spelling", "quote": "billing", "suggestion": "billings"}]
    result = _import(FakeReader(None, typos=typos))
    assert result.read_by is None
    assert [f.rule for f in result.findings].count("content.proofread") == 1


def test_skill_names_the_audit_flags_arent_flagged_again() -> None:
    doc = extract(
        b"Avery Chen\nEXPERIENCE\nLed a team of 5 analyst.\nSKILLS\nPython, Tableu, SQL\n",
        "a.txt",
    )
    parsed = segment(doc)
    found = AiProofread.model_validate(
        {
            "typos": [
                {"line": 4, "kind": "spelling", "quote": "Tableu", "suggestion": "Tableau"},
                {"line": 2, "kind": "grammar", "quote": "5 analyst", "suggestion": "5 analysts"},
            ]
        }
    )
    kept = proofread_findings(doc, parsed, found)
    assert [loc.excerpt for f in kept for loc in f.locations] == ["5 analyst"]


def test_claude_is_asked_for_facts_at_low_effort() -> None:
    sent: list[dict[str, Any]] = []
    answer = {"results": [{"result": "R1", "skills": [], "scope": [], "outcome": ""}]}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": json.dumps(answer)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = anthropic.Anthropic(
        api_key="test",
        base_url="https://api.test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    reader = ClaudeReader(client, "claude-haiku-5-5", "medium")
    found = reader.read_facts([("R1", "Ran  billing\nfor 3 clinics.")])
    assert found is not None and found.results[0].result == "R1"
    assert sent[0]["system"] == FACTS_INSTRUCTIONS
    assert sent[0]["output_config"]["effort"] == "low"
    assert sent[0]["messages"][0]["content"] == "Accomplishments:\n[R1] Ran billing for 3 clinics."
