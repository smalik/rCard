"""Reading a resume's structure with Claude (imports/ai.py), without calling Claude.

A fake reader stands in for the model and returns what a good reading looks like,
or a bad one, so these tests check what the code does with it: values are kept only
when the resume says them, and the rules take over when there's no reading.
"""

import json
from datetime import date
from typing import Any

import anthropic
import httpx2

from plytos_api.imports.ai import (
    INSTRUCTIONS,
    AiResume,
    ClaudeReader,
    reader_for,
    resume_lines,
    verbatim,
)
from plytos_api.imports.extract import extract
from plytos_api.imports.model import ExtractedDocument, ImportResult
from plytos_api.imports.pipeline import import_resume
from tests.resume_samples import promotions_text

TODAY = date(2026, 11, 4)


def _role(**fields: Any) -> dict[str, Any]:
    role: dict[str, Any] = {
        "section": "experience",
        "title": None,
        "employer": None,
        "client": None,
        "location": None,
        "employment_type": None,
        "dates": None,
        "header_lines": [],
        "employer_line": None,
        "engagement_of": None,
        "description_lines": [],
        "bullets": [],
        "unsure": False,
    }
    role.update(fields)
    return role


def _bullets(*lines: int) -> list[dict[str, Any]]:
    return [{"line": i, "group": None} for i in lines]


def good_reading() -> dict[str, Any]:
    """What Claude should return for promotions_text()."""
    return {
        "name": "Avery Quinn",
        "contact_lines": [0, 1],
        "sections": [
            {"kind": "contact", "heading_line": None, "lines": [0, 1]},
            {"kind": "experience", "heading_line": 2, "lines": list(range(3, 15))},
            {"kind": "education", "heading_line": 15, "lines": [16]},
        ],
        "summary_lines": [],
        "roles": [
            _role(
                title="Director, Supply Chain Operations",
                employer="Northwind Logistics",
                location="Chicago, IL",
                dates="Jan 2021 – Present",
                header_lines=[4],
                employer_line=3,
                bullets=_bullets(5, 6),
            ),
            _role(
                title="Senior Manager, Operations",
                employer="Northwind Logistics",
                location="Chicago, IL",
                dates="Jun 2017 – Dec 2020",
                header_lines=[7],
                employer_line=3,
                bullets=_bullets(8),
            ),
            _role(
                title="Operations Analyst",
                employer="Northwind Logistics",
                location="Chicago, IL",
                dates="Mar 2014 – May 2017",
                header_lines=[9],
                employer_line=3,
                bullets=_bullets(10),
            ),
            _role(
                title="Consultant",
                employer="Brightline Partners",
                location="Milwaukee, WI",
                dates="Jun 2010 – Feb 2014",
                header_lines=[11, 12],
            ),
            _role(
                employer="Brightline Partners",
                client="Fabrikam Foods",
                header_lines=[13],
                engagement_of=3,
                bullets=_bullets(14),
            ),
        ],
        "skills": [],
        "education": [{"lines": [16], "dates": "2010"}],
        "certifications": [],
        "projects": [],
        "awards": [],
        "highlights": [],
    }


class FakeReader:
    name = "fake-model"

    def __init__(self, reading: dict[str, Any] | None) -> None:
        self.reading = reading
        self.seen: list[ExtractedDocument] = []

    def read(self, doc: ExtractedDocument) -> AiResume | None:
        self.seen.append(doc)
        return AiResume.model_validate(self.reading) if self.reading is not None else None


def _import(reading: dict[str, Any] | None) -> ImportResult:
    return import_resume(
        promotions_text().encode(), "avery.txt", today=TODAY, reader=FakeReader(reading)
    )


def _role_cards(result: ImportResult) -> list[dict[str, Any]]:
    return [{**c.content.facts, "checks": c.needs_check} for c in result.cards if c.kind == "role"]


def test_rules_alone_misread_promotions_under_one_employer() -> None:
    """Why the reader exists: the rules turn the employer line into a titleless role."""
    result = import_resume(promotions_text().encode(), "avery.txt", today=TODAY)
    assert result.read_by is None
    first = _role_cards(result)[0]
    assert "title" not in first
    assert "What was the job title?" in first["checks"]


def test_promotions_become_one_role_each_at_the_same_employer() -> None:
    result = _import(good_reading())
    assert result.read_by == "fake-model"
    cards = _role_cards(result)
    northwind = [c for c in cards if c.get("employer") == "Northwind Logistics"]
    assert [(c["title"], c["start"], c["end"]) for c in northwind] == [
        ("Director, Supply Chain Operations", "2021-01", "present"),
        ("Senior Manager, Operations", "2017-06", "2020-12"),
        ("Operations Analyst", "2014-03", "2017-05"),
    ]
    assert all(c["checks"] == [] for c in northwind)
    # The employer's whole tenure isn't a role of its own.
    assert not any(c.get("start") == "2014-03" and c.get("end") == "present" for c in cards)


def test_accomplishments_keep_their_role_and_employer() -> None:
    result = _import(good_reading())
    led = next(c for c in result.cards if c.content.framing.headline.startswith("Led a 40-person"))
    assert led.content.facts["employer"] == "Northwind Logistics"
    assert led.content.facts["title"] == "Director, Supply Chain Operations"
    assert led.content.framing.headline == (
        "Led a 40-person team across three distribution centers, cutting late shipments by 22%."
    )


def test_promotions_dont_read_as_overlaps_or_missing_employers() -> None:
    by_rules = {f.rule for f in import_resume(promotions_text().encode(), "a.txt").findings}
    assert "ats.unclear_roles" in by_rules
    rules = {f.rule for f in _import(good_reading()).findings}
    assert "dates.overlap" not in rules
    assert "ats.unclear_roles" not in rules


def test_client_engagements_sit_under_the_agency_role() -> None:
    result = _import(good_reading())
    agency = next(r for r in result.roles if r.title == "Consultant")
    client = next(r for r in result.roles if r.client == "Fabrikam Foods")
    assert client.parent_ref == agency.ref
    assert client.organization == "Brightline Partners"


def test_values_the_resume_doesnt_say_are_dropped() -> None:
    reading = good_reading()
    reading["roles"][0]["employer"] = "Northwind Logistics Inc."
    reading["roles"][0]["title"] = "VP, Supply Chain"
    reading["roles"][0]["dates"] = "January 2021 – Present"
    first = _role_cards(_import(reading))[0]
    assert "employer" not in first and "title" not in first and "start" not in first
    assert "Who was the employer?" in first["checks"]
    assert "What was the job title?" in first["checks"]


def test_values_keep_the_resumes_own_spelling() -> None:
    assert verbatim("northwind  logistics", ["Northwind Logistics, Chicago"]) == (
        "Northwind Logistics"
    )
    assert verbatim("Contoso", ["Northwind Logistics"]) is None
    assert verbatim(None, ["anything"]) is None


def test_line_numbers_that_dont_exist_are_ignored() -> None:
    reading = good_reading()
    reading["roles"][0]["bullets"] = _bullets(5, 6, 999)
    reading["roles"][0]["header_lines"] = [4, -3]
    result = _import(reading)
    role = result.roles[0]
    assert [b.block for b in role.bullets] == [5, 6]
    assert role.header_blocks == [4, 3]


def test_a_line_belongs_to_one_role_only() -> None:
    reading = good_reading()
    reading["roles"][1]["bullets"] = _bullets(6, 8)
    result = _import(reading)
    assert [b.block for b in result.roles[0].bullets] == [5, 6]
    assert [b.block for b in result.roles[1].bullets] == [8]


def test_lines_left_out_stay_with_the_role_above() -> None:
    reading = good_reading()
    reading["roles"][0]["bullets"] = _bullets(5)
    result = _import(reading)
    assert [b.block for b in result.roles[0].bullets] == [5, 6]


def test_the_rules_take_over_when_there_is_no_reading() -> None:
    result = _import(None)
    assert result.read_by is None
    assert result.cards


def test_resume_lines_number_every_line_with_layout_hints() -> None:
    doc = extract(promotions_text().encode(), "avery.txt")
    lines = resume_lines(doc).splitlines()
    assert lines[2] == "[2] EXPERIENCE  (caps)"
    assert lines[5].startswith("[5] Led a 40-person team") and lines[5].endswith("(bullet)")


def test_reader_is_off_unless_asked_for() -> None:
    assert reader_for("off", "claude-haiku-5-5", "medium", "", "global") is None


def test_claude_reader_asks_haiku_at_medium_effort_for_json() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": json.dumps(good_reading())}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = anthropic.Anthropic(
        api_key="test",
        base_url="https://api.test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    reader = ClaudeReader(client, "claude-haiku-5-5", "medium")
    doc = extract(promotions_text().encode(), "avery.txt")
    reading = reader.read(doc)

    assert reading is not None and len(reading.roles) == 5
    body = sent[0]
    assert body["model"] == "claude-haiku-5-5"
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"] == INSTRUCTIONS
    assert "[4] Director, Supply Chain Operations" in body["messages"][0]["content"]
    assert "temperature" not in body


def test_claude_reader_gives_up_quietly_on_errors_and_refusals() -> None:
    def failing(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"type": "error", "error": {"type": "api_error"}})

    def refusing(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [],
                "stop_reason": "refusal",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
        )

    doc = extract(promotions_text().encode(), "avery.txt")
    for handler in (failing, refusing):
        client = anthropic.Anthropic(
            api_key="test",
            base_url="https://api.test",
            max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        assert ClaudeReader(client, "claude-haiku-5-5", "medium").read(doc) is None
