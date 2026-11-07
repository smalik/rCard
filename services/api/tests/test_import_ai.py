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
        "employment": -1,
        "volunteer": False,
        "title": "",
        "employer": "",
        "client": "",
        "location": "",
        "employment_type": "",
        "dates": "",
        "header_lines": [],
        "engagement_of": -1,
        "subheading_lines": [],
        "bullet_lines": [],
        "description_lines": [],
        "unsure": False,
    }
    role.update(fields)
    return role


def good_reading() -> dict[str, Any]:
    """What Claude should return for promotions_text()."""
    return {
        "name": "Avery Quinn",
        "contact_lines": [0, 1],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0, 1]},
            {"kind": "experience", "heading_line": 2, "lines": list(range(3, 15))},
            {"kind": "education", "heading_line": 15, "lines": [16]},
        ],
        "summary_lines": [],
        "employments": [
            {
                "employer": "Northwind Logistics",
                "location": "Chicago, IL",
                "dates": "Mar 2014 – Present",
                "header_lines": [3],
                "description_lines": [],
            },
            {
                "employer": "Brightline Partners",
                "location": "Milwaukee, WI",
                "dates": "Jun 2010 – Feb 2014",
                "header_lines": [11],
                "description_lines": [],
            },
        ],
        "roles": [
            _role(
                title="Director, Supply Chain Operations",
                employer="Northwind Logistics",
                location="Chicago, IL",
                dates="Jan 2021 – Present",
                header_lines=[4],
                employment=0,
                bullet_lines=[5, 6],
            ),
            _role(
                title="Senior Manager, Operations",
                employer="Northwind Logistics",
                location="Chicago, IL",
                dates="Jun 2017 – Dec 2020",
                header_lines=[7],
                employment=0,
                bullet_lines=[8],
            ),
            _role(
                title="Operations Analyst",
                employer="Northwind Logistics",
                location="Chicago, IL",
                dates="Mar 2014 – May 2017",
                header_lines=[9],
                employment=0,
                bullet_lines=[10],
            ),
            _role(
                title="Consultant",
                employer="Brightline Partners",
                location="Milwaukee, WI",
                dates="Jun 2010 – Feb 2014",
                header_lines=[12],
                employment=1,
            ),
            _role(
                employment=1,
                employer="Brightline Partners",
                client="Fabrikam Foods",
                header_lines=[13],
                engagement_of=3,
                bullet_lines=[14],
            ),
        ],
        "skills": [],
        "entries": [
            {"kind": "education", "lines": [16], "dates": "2010", "school": "", "degree": ""}
        ],
        "skipped": [],
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


def _tree(result: ImportResult) -> list[tuple[int, str, str]]:
    """Each proposed card as (depth, kind, headline), in order."""
    by_ref = {c.ref: c for c in result.cards}

    def depth(ref: str | None) -> int:
        return 0 if ref is None else 1 + depth(by_ref[ref].parent_ref)

    return [(depth(c.parent_ref), c.kind, c.content.framing.headline) for c in result.cards]


def _positions(result: ImportResult) -> list[dict[str, Any]]:
    return [
        {**c.content.facts, "checks": c.needs_check} for c in result.cards if c.kind == "position"
    ]


def test_rules_alone_misread_promotions_under_one_employer() -> None:
    """Why the reader exists: the rules turn the employer line into a titleless role."""
    result = import_resume(promotions_text().encode(), "avery.txt", today=TODAY)
    assert result.read_by is None
    first = _positions(result)[0]
    assert "title" not in first
    assert "What was the job title?" in first["checks"]


def test_promotions_sit_inside_one_employment() -> None:
    result = _import(good_reading())
    assert result.read_by == "fake-model"
    assert _tree(result)[:12] == [
        (0, "employment", "Northwind Logistics"),
        (1, "position", "Director, Supply Chain Operations"),
        (
            2,
            "accomplishment",
            "Led a 40-person team across three distribution centers, "
            "cutting late shipments by 22%.",
        ),
        (
            2,
            "accomplishment",
            "Built the first network-wide demand forecast, saving $3.1M in carrying costs.",
        ),
        (1, "position", "Senior Manager, Operations"),
        (2, "accomplishment", "Rolled out warehouse software to 6 sites in 9 months."),
        (1, "position", "Operations Analyst"),
        (2, "accomplishment", "Automated weekly inventory reporting, saving 10 hours a week."),
        (0, "employment", "Brightline Partners"),
        (1, "position", "Consultant"),
        (2, "engagement", "Fabrikam Foods"),
        (3, "accomplishment", "Mapped inbound freight for 120 suppliers."),
    ]
    northwind = next(c for c in result.cards if c.kind == "employment")
    # The tenure written once on the employer line is the employment's.
    assert northwind.content.facts == {
        "employer": "Northwind Logistics",
        "location": "Chicago, IL",
        "start": "2014-03",
        "end": "present",
    }
    assert northwind.needs_check == []
    positions = [p for p in _positions(result) if p.get("title") != "Consultant"]
    assert [(p["title"], p["start"], p["end"], p["checks"]) for p in positions] == [
        ("Director, Supply Chain Operations", "2021-01", "present", []),
        ("Senior Manager, Operations", "2017-06", "2020-12", []),
        ("Operations Analyst", "2014-03", "2017-05", []),
    ]
    assert [(e.organization, e.tenure_written) for e in result.employments] == [
        ("Northwind Logistics", True),
        ("Brightline Partners", True),
    ]


def test_accomplishments_hold_only_their_own_facts() -> None:
    result = _import(good_reading())
    led = next(c for c in result.cards if c.content.framing.headline.startswith("Led a 40-person"))
    assert led.content.facts == {}
    director = next(c for c in result.cards if c.ref == led.parent_ref)
    assert director.content.facts["title"] == "Director, Supply Chain Operations"


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


def test_an_engagement_finds_its_agency_role_when_not_pointed_at_it() -> None:
    reading = good_reading()
    reading["roles"][4]["engagement_of"] = -1
    result = _import(reading)
    client = next(r for r in result.roles if r.client == "Fabrikam Foods")
    assert client.parent_ref == next(r.ref for r in result.roles if r.title == "Consultant")
    checks = next(c.needs_check for c in result.cards if c.role_ref == client.ref)
    assert "What was your title on the Fabrikam Foods work?" in checks


def test_values_the_resume_doesnt_say_are_dropped() -> None:
    reading = good_reading()
    reading["roles"][0]["employer"] = "Northwind Logistics Inc."
    reading["roles"][0]["title"] = "VP, Supply Chain"
    reading["roles"][0]["dates"] = "January 2021 – Present"
    result = _import(reading)
    first = _positions(result)[0]
    assert "title" not in first
    assert "What was the job title?" in first["checks"]
    # The made-up dates are dropped; the range written on the title's own line is used.
    assert (first["start"], first["end"]) == ("2021-01", "present")
    # The shared employer line still names the employer for it.
    employer = next(c for c in result.cards if c.kind == "employment")
    assert employer.content.facts["employer"] == "Northwind Logistics"


def test_values_keep_the_resumes_own_spelling() -> None:
    assert verbatim("northwind  logistics", ["Northwind Logistics, Chicago"]) == (
        "Northwind Logistics"
    )
    assert verbatim("Contoso", ["Northwind Logistics"]) is None
    assert verbatim(None, ["anything"]) is None


def test_line_numbers_that_dont_exist_are_ignored() -> None:
    reading = good_reading()
    reading["roles"][0]["bullet_lines"] = [5, 6, 999]
    reading["roles"][0]["header_lines"] = [4, -3]
    result = _import(reading)
    role = result.roles[0]
    assert [b.block for b in role.bullets] == [5, 6]
    assert role.header_blocks == [4, 3]


def test_a_line_belongs_to_one_role_only() -> None:
    reading = good_reading()
    reading["roles"][1]["bullet_lines"] = [6, 8]
    result = _import(reading)
    assert [b.block for b in result.roles[0].bullets] == [5, 6]
    assert [b.block for b in result.roles[1].bullets] == [8]


def test_lines_left_out_stay_with_the_role_above() -> None:
    reading = good_reading()
    reading["roles"][0]["bullet_lines"] = [5]
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


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _client(handler: Any) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="test",
        base_url="https://api.test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def test_the_schema_has_no_optional_or_nullable_fields() -> None:
    """The API compiles the schema into a grammar with a size cap; unions blow it up."""
    schema = json.dumps(AiResume.model_json_schema())
    assert "anyOf" not in schema and "null" not in schema


def test_a_step_left_out_makes_no_call() -> None:
    sent: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content)["system"])
        return httpx2.Response(200, json=_message(json.dumps(good_reading())))

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium")
    reader.skip_steps = frozenset({"proofread"})
    metered = reader.metered()
    doc = extract(promotions_text().encode(), "avery.txt")
    assert metered.proofread(doc) is None
    assert metered.read(doc) is not None
    assert sent == [INSTRUCTIONS]
    assert [c.step for c in metered.calls] == ["structure"]


def test_claude_reader_asks_haiku_at_medium_effort_for_json() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=_message(json.dumps(good_reading())))

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium")
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


def test_claude_reader_asks_for_plain_json_when_the_schema_is_refused() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        sent.append(body)
        if "format" in body.get("output_config", {}):
            error = {"type": "invalid_request_error", "message": "grammar is too large"}
            return httpx2.Response(400, json={"type": "error", "error": error})
        return httpx2.Response(
            200, json=_message("```json\n" + json.dumps(good_reading()) + "\n```")
        )

    doc = extract(promotions_text().encode(), "avery.txt")
    reading = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium").read(doc)

    assert reading is not None and len(reading.roles) == 5
    assert len(sent) == 2
    assert sent[1]["output_config"] == {"effort": "medium"}
    assert "Reply with only a JSON object" in sent[1]["system"]


def test_a_plain_answer_cut_off_for_length_is_asked_again_at_low_effort() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        sent.append(body["output_config"])
        if "format" in body["output_config"]:
            error = {"type": "invalid_request_error", "message": "grammar is too large"}
            return httpx2.Response(400, json={"type": "error", "error": error})
        if len(sent) == 2:
            return httpx2.Response(200, json=_message('{"name": "Av', stop_reason="max_tokens"))
        return httpx2.Response(200, json=_message(json.dumps(good_reading())))

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium")
    reading = reader.read(extract(promotions_text().encode(), "avery.txt"))
    assert reading is not None
    assert [c.get("effort") for c in sent] == ["medium", "medium", "low"]
    assert [c.error for c in reader.calls] == ["BadRequestError", "max_tokens", None]


def test_claude_reader_gives_up_quietly_on_errors_refusals_and_bad_json() -> None:
    def failing(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"type": "error", "error": {"type": "api_error"}})

    def refusing(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_message("", stop_reason="refusal"))

    def refused_then_garbled(request: httpx2.Request) -> httpx2.Response:
        if "format" in json.loads(request.content).get("output_config", {}):
            error = {"type": "invalid_request_error", "message": "no"}
            return httpx2.Response(400, json={"type": "error", "error": error})
        return httpx2.Response(200, json=_message('{"name": "Avery Quinn"}'))

    doc = extract(promotions_text().encode(), "avery.txt")
    for handler in (failing, refusing, refused_then_garbled):
        assert ClaudeReader(_client(handler), "claude-haiku-5-5", "medium").read(doc) is None


def test_bullets_under_a_subheading_carry_it_as_their_workstream() -> None:
    reading = good_reading()
    reading["roles"][0]["subheading_lines"] = [4]
    reading["roles"][0]["header_lines"] = []
    reading["roles"][0]["title"] = ""
    result = _import(reading)
    assert {b.group for b in result.roles[0].bullets} == {
        "Director, Supply Chain Operations (Jan 2021 – Present)"
    }


def test_a_title_outside_the_employer_tenure_is_flagged() -> None:
    text = promotions_text().replace(
        "Operations Analyst (Mar 2014 – May 2017)", "Operations Analyst (Mar 2013 – May 2017)"
    )
    reading = good_reading()
    reading["roles"][2]["dates"] = "Mar 2013 – May 2017"
    result = import_resume(text.encode(), "a.txt", today=TODAY, reader=FakeReader(reading))
    [finding] = [f for f in result.findings if f.rule == "dates.outside_tenure"]
    assert "Operations Analyst" in finding.detail
    assert "Mar 2014 – Present" in finding.detail
    # The moved date now overlaps the job before; titles inside Northwind never count.
    [overlap] = [f for f in result.findings if f.rule == "dates.overlap"]
    assert "Brightline Partners" in overlap.detail


SCHOOLED = (
    "Pat Lee\n"
    "Experience\n"
    "Store Manager, Fabrikam Retail, 2019 - 2021\n"
    "Grew sales 12% in two years by reworking the floor plan.\n"
    "Leadership\n"
    "• Led a team of 40.\n"
    "• Opened the store on weekends.\n"
    "Education\n"
    "Bachelor of Science : Business Administration , 2015 Lakeshore College Springfield , IL\n"
)


def _schooled(school: str, degree: str) -> dict[str, Any]:
    return {
        "name": "Pat Lee",
        "contact_lines": [0],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0]},
            {"kind": "experience", "heading_line": 1, "lines": [2, 3, 4, 5, 6]},
            {"kind": "education", "heading_line": 7, "lines": [8]},
        ],
        "summary_lines": [],
        "employments": [],
        "roles": [
            _role(
                title="Store Manager",
                employer="Fabrikam Retail",
                dates="2019 - 2021",
                header_lines=[2],
                # The sentence taken for a sub-heading, as a reading may.
                subheading_lines=[3, 4],
                bullet_lines=[5, 6],
            )
        ],
        "skills": [],
        "entries": [
            {"kind": "education", "lines": [8], "dates": "2015", "school": school, "degree": degree}
        ],
        "skipped": [],
    }


def _read_schooled(school: str, degree: str) -> ImportResult:
    reader = FakeReader(_schooled(school, degree))
    return import_resume(SCHOOLED.encode(), "pat.txt", today=TODAY, reader=reader)


def test_the_school_and_degree_are_as_claude_names_them() -> None:
    result = _read_schooled("Lakeshore College", "Bachelor of Science : Business Administration")
    [school] = [c for c in result.cards if c.kind == "education"]
    assert school.content.facts["institution"] == "Lakeshore College"
    assert school.content.facts["degree"] == "Bachelor of Science : Business Administration"


def test_a_school_the_line_doesnt_name_is_not_taken() -> None:
    result = _read_schooled("Harvard University", "")
    [school] = [c for c in result.cards if c.kind == "education"]
    assert school.content.facts.get("institution") != "Harvard University"
    assert school.content.facts["degree"] == "Bachelor of Science : Business Administration"


def test_a_sentence_taken_for_a_sub_heading_is_an_accomplishment() -> None:
    result = _read_schooled("Lakeshore College", "")
    done = {
        c.content.framing.headline: c.content.facts.get("workstream")
        for c in result.cards
        if c.kind == "accomplishment"
    }
    assert done == {
        "Grew sales 12% in two years by reworking the floor plan.": None,
        "Led a team of 40.": "Leadership",
        "Opened the store on weekends.": "Leadership",
    }
