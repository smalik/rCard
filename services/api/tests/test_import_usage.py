"""What Claude calls cost (imports/usage.py) and the bench runner over folders of
resumes (imports/bench.py), without calling Claude. The resumes are made up
(tests/resume_samples.py)."""

import json
from pathlib import Path
from typing import Any

import anthropic
import httpx2

from plytos_api.imports.ai import AiProofread, ClaudeReader
from plytos_api.imports.bench import find_resumes, measured_ids, pick, run
from plytos_api.imports.extract import extract
from plytos_api.imports.model import ExtractedDocument
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.usage import AiCall, AiUsage, cost
from tests.resume_samples import clean_pdf, pictured_pdf, promotions_text, two_column_pdf


def _call(**fields: Any) -> AiCall:
    base: dict[str, Any] = {"step": "structure", "model": "claude-haiku-5-5", "effort": "medium"}
    return AiCall(**{"ok": True, **base, **fields})


def test_cost_is_list_price_per_million_tokens() -> None:
    assert cost(_call(input_tokens=10_000, output_tokens=2_000)) == 0.002
    # Past 100K tokens of prompt, the whole request is at the long rates.
    assert cost(_call(input_tokens=150_000, output_tokens=1_000)) == 0.0775
    assert cost(_call(cache_read_tokens=10_000)) == 0.0001
    assert cost(_call(cache_write_tokens=10_000)) == 0.00125
    assert cost(_call(model="some-other-model", input_tokens=10)) is None


def test_usage_totals_count_cached_input_too() -> None:
    usage = AiUsage(
        calls=[
            _call(input_tokens=100, cache_read_tokens=50, output_tokens=10, cost_usd=0.5),
            _call(step="facts", output_tokens=5, cost_usd=0.25),
        ]
    )
    assert usage.input_tokens == 150 and usage.output_tokens == 15
    assert usage.cost_usd == 0.75
    # A call lost to an error is estimated at the dearest call of its step.
    usage.calls.append(_call(ok=False, cost_usd=None))
    assert usage.cost_usd == 0.75 and usage.unpriced == 1
    assert usage.estimated_cost_usd == 1.25


def _client(handler: Any) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="test",
        base_url="https://api.test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def _reply(text: str, usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage,
    }


def test_each_call_is_recorded_with_its_step_tokens_and_cost() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        usage = {
            "input_tokens": 12_000,
            "output_tokens": 3_000,
            "cache_read_input_tokens": 0,
            "output_tokens_details": {"thinking_tokens": 1_000},
        }
        return httpx2.Response(200, json=_reply('{"typos": []}', usage))

    shared = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium")
    reader = shared.metered()
    doc = extract(promotions_text().encode(), "avery.txt")
    assert reader.proofread(doc) is not None
    [call] = reader.calls
    assert (call.step, call.effort, call.ok) == ("proofread", "low", True)
    assert (call.input_tokens, call.output_tokens, call.thinking_tokens) == (12_000, 3_000, 1_000)
    assert call.cost_usd == 0.0027
    # The shared reader keeps no calls; each import counts its own.
    assert shared.calls == []


def test_a_failed_call_is_recorded_as_failed() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"type": "error", "error": {"type": "api_error"}})

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium").metered()
    assert reader.read(extract(promotions_text().encode(), "avery.txt")) is None
    [call] = reader.calls
    assert not call.ok and call.error == "InternalServerError" and call.cost_usd == 0.0


class MeteredFake:
    """Charges a fixed amount for reading the structure, then leaves it to the rules."""

    name = "fake-model"

    def __init__(self, charge: float = 0.004) -> None:
        self.charge = charge
        self.calls: list[AiCall] = []

    def metered(self) -> "MeteredFake":
        return MeteredFake(self.charge)

    def read(self, doc: ExtractedDocument) -> None:
        self.calls.append(
            _call(input_tokens=4_000, output_tokens=1_500, seconds=0.5, cost_usd=self.charge)
        )


def test_an_import_keeps_what_its_calls_cost() -> None:
    result = import_resume(promotions_text().encode(), "avery.txt", reader=MeteredFake())
    assert result.usage is not None
    assert [c.step for c in result.usage.calls] == ["structure"]
    assert result.usage.cost_usd == 0.004
    assert import_resume(promotions_text().encode(), "avery.txt").usage is None


def _folders(tmp_path: Path) -> Path:
    root = tmp_path / "resumes"
    (root / "ACCOUNTANT").mkdir(parents=True)
    (root / "DESIGNER").mkdir()
    (root / "ACCOUNTANT" / "1.pdf").write_bytes(clean_pdf())
    (root / "DESIGNER" / "2.pdf").write_bytes(two_column_pdf())
    (root / "DESIGNER" / "notes.txt").write_text("not a resume")
    (root / "3.pdf").write_bytes(pictured_pdf())
    return root


def test_resumes_are_found_by_category_and_sampled_across_them(tmp_path: Path) -> None:
    root = _folders(tmp_path)
    found = find_resumes([root])
    assert sorted((p.name, c) for p, c in found) == [
        ("1.pdf", "ACCOUNTANT"),
        ("2.pdf", "DESIGNER"),
        ("3.pdf", "resumes"),
    ]
    assert sorted(c for _, c in pick(found, 3, seed=1)) == ["ACCOUNTANT", "DESIGNER", "resumes"]
    assert pick(found, 2, seed=1) == pick(found, 2, seed=1)


def test_the_bench_stops_at_the_budget_across_runs(tmp_path: Path) -> None:
    root = _folders(tmp_path)
    out = tmp_path / "bench"
    items = pick(find_resumes([root]), 3, seed=1)

    records = run(items, MeteredFake(0.004), out, budget=0.01, run_id="first")
    assert len(records) == 2
    ledger = json.loads((out / "spend.json").read_text())
    assert ledger["spent_usd"] == 0.008 and ledger["resumes"] == 2
    assert len(measured_ids(out)) == 2
    assert len((out / "index.jsonl").read_text().splitlines()) == 2
    readings = sorted((out / "readings" / "first").glob("*.json"))
    assert [p.stem for p in readings] == sorted(measured_ids(out))
    assert (readings[0].stat().st_mode & 0o777) == 0o600
    assert (out.stat().st_mode & 0o777) == 0o700

    summary = (out / "summary-first.md").read_text()
    assert "Stopped at the budget." in summary
    assert "| $1 | 250 | 250 |" in summary
    # Numbers only: nothing from the resumes themselves.
    assert "Avery" not in summary and "Casey" not in summary

    # The next run picks up the total and has no room for another resume.
    assert run(items[2:], MeteredFake(0.004), out, budget=0.01, run_id="second") == []


def test_an_answer_that_breaks_the_schema_is_asked_for_once_more(caplog: Any) -> None:
    answers = iter(['{"typos": "not a list"}', '{"typos": []}'])

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, json=_reply(next(answers), {"input_tokens": 10, "output_tokens": 5})
        )

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium").metered()
    found = reader.proofread(extract(promotions_text().encode(), "avery.txt"))
    assert found is not None and found.typos == []
    first, second = reader.calls
    # The unusable answer was billed, and is counted with its tokens.
    assert (first.ok, first.error, first.output_tokens) == (False, "ValidationError", 5)
    assert first.cost_usd is not None and first.cost_usd > 0
    assert second.ok and second.cost_usd is not None
    # The log says where the answer broke, never what it said.
    assert "typos: list_type" in caplog.text and "not a list" not in caplog.text


def test_a_run_can_be_read_again_and_compared(tmp_path: Path) -> None:
    from plytos_api.imports.bench import compare, rerun_items

    root = _folders(tmp_path)
    out = tmp_path / "bench"
    items = pick(find_resumes([root]), 3, seed=1)
    run(items, MeteredFake(0.001), out, budget=1.0, run_id="base")
    again = rerun_items(out, "base")
    assert [p for p, _ in again] == [p for p, _ in items]
    records = run(again, MeteredFake(0.002), out, budget=1.0, run_id="low", label="structure=low")
    assert {r["label"] for r in records} == {"structure=low"}
    assert "Variant: structure=low" in (out / "summary-low.md").read_text()

    report = compare(out, "base", "low")
    assert "3 resumes read in both." in report
    # The same rules read the same files the same way.
    assert "Employers (mean overlap): 100.0%" in report
    assert "Accomplishments under the same job: 100.0%" in report
    assert "| Mean cost (USD) | 0.0010 | 0.0020 |" in report
    assert "| Mean cost without proofreading | 0.0010 | 0.0020 |" in report
    assert "| Mean cost of facts | 0.0000 | 0.0000 |" in report
    assert "## Facts on the same accomplishments" in report
    assert "Avery" not in report and "Casey" not in report


def test_a_step_can_run_at_another_effort() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content)["output_config"]["effort"])
        return httpx2.Response(200, json=_reply('{"typos": []}', {"input_tokens": 10}))

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium")
    reader.step_efforts = {"proofread": "high"}
    metered = reader.metered()
    metered.proofread(extract(promotions_text().encode(), "avery.txt"))
    assert seen == ["high"]
    assert metered.calls[0].effort == "high"


def test_an_answer_cut_off_for_length_is_asked_again_at_low_effort() -> None:
    sent: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content)["output_config"]["effort"])
        reply = _reply('{"typos": [' if len(sent) == 1 else '{"typos": []}', {"output_tokens": 9})
        if len(sent) == 1:
            reply["stop_reason"] = "max_tokens"
        return httpx2.Response(200, json=reply)

    reader = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium").metered()
    found = reader.ask("Proofread.", "Lines", AiProofread, step="proofread", effort="medium")
    assert found is not None
    assert sent == ["medium", "low"]
    first, second = reader.calls
    assert (first.ok, first.error, first.stop_reason) == (False, "max_tokens", "max_tokens")
    assert first.cost_usd is not None and second.ok


class FailingFake(MeteredFake):
    """Charges for a reading, then fails, as a crash partway through an import would."""

    def metered(self) -> "FailingFake":
        return FailingFake(self.charge)

    def read(self, doc: ExtractedDocument) -> None:
        super().read(doc)
        raise RuntimeError("something about the resume")


def test_a_failed_import_still_counts_what_it_spent(tmp_path: Path) -> None:
    root = _folders(tmp_path)
    out = tmp_path / "bench"
    items = pick(find_resumes([root]), 1, seed=1)
    [record] = run(items, FailingFake(0.003), out, budget=1.0, run_id="crash")
    assert record["error"] == "RuntimeError"
    assert record["cost_usd"] == 0.003
    assert record["where"].startswith("test_import_usage.py:")
    # Where it failed, never what the error said.
    assert "resume" not in json.dumps(record["where"])
    assert json.loads((out / "spend.json").read_text())["spent_usd"] == 0.003
