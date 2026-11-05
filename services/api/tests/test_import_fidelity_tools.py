"""The bench's tools for real resumes: Claude's answers kept to score again for free
(fidelity/tape.py), a resume's shape without its words (fidelity/shape.py), and misses
that say what went wrong. Everyone here is made up."""

import os
import stat
from pathlib import Path

import httpx2

from plytos_api.imports.ai import AiProofread, ClaudeReader
from plytos_api.imports.fidelity.layouts import PDF
from plytos_api.imports.fidelity.real import file_id
from plytos_api.imports.fidelity.run import TODAY
from plytos_api.imports.fidelity.score import score
from plytos_api.imports.fidelity.shape import show, skeleton
from plytos_api.imports.fidelity.tape import TapedReader
from plytos_api.imports.fidelity.truth import MORGAN, Career, School
from plytos_api.imports.pipeline import import_resume
from tests.test_import_fidelity_real import Cards, job
from tests.test_import_usage import _client, _reply


def test_a_question_asked_before_is_answered_from_the_tape(tmp_path: Path) -> None:
    asked: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request.url.path)
        return httpx2.Response(200, json=_reply('{"typos": []}', {"input_tokens": 10}))

    tape = tmp_path / "tape"
    reader = TapedReader(ClaudeReader(_client(handler), "claude-haiku-5-5", "medium"), tape)
    first = reader.metered()
    assert first.ask("Proofread.", "Lines", AiProofread, step="proofread") is not None
    again = reader.metered()
    assert again.ask("Proofread.", "Lines", AiProofread, step="proofread") is not None
    # Asked once, and the second answer cost nothing.
    assert len(asked) == 1 and len(first.calls) == 1 and again.calls == []
    # A changed question is asked anew.
    again.ask("Proofread.", "Other lines", AiProofread, step="proofread")
    assert len(asked) == 2
    [kept, *_] = tape.iterdir()
    assert stat.S_IMODE(os.stat(kept).st_mode) == 0o600


def test_a_shape_holds_no_words(tmp_path: Path) -> None:
    assert skeleton("Grew sales 12% at Fabrikam (2019).") == "W w 9% w W (9)."
    assert skeleton("May 2019 to Present") == "May 9 w Present"
    web_print = next(lay for lay in PDF if lay.name == "pdf-web-print")
    data = web_print.render(MORGAN)
    source = tmp_path / "resume.pdf"
    source.write_bytes(data)
    career = MORGAN.model_copy(update={"key": file_id(data), "source": str(source)})
    reading = import_resume(data, "resume.pdf", today=TODAY, reader=None)
    shown = show(career, reading).lower()
    words = {
        w.strip(".,;:()").lower()
        for e in MORGAN.employments
        for p in e.positions
        for g in p.groups
        for item in g.items
        for w in item.split()
    } | {MORGAN.name.lower(), *(e.employer.lower() for e in MORGAN.employments)}
    # The tool's own words ("under", "employer") aren't the resume's.
    own = {"under", "employer", "facts", "reading", "lines", "label", "item"}
    leaked = {w for w in words - own if len(w) > 3 and w in shown.split()}
    assert not leaked
    assert "reading (100%)" in shown


def test_an_education_miss_says_what_was_misread() -> None:
    career = Career(
        key="school",
        employments=[job("Store Manager", "2019-03", "2021-01", "Grew sales 12%.")],
        education=[
            School(
                school="Lakeshore College",
                degree="Bachelor of Science",
                field="Business Administration",
                year="2015",
            )
        ],
    )
    r = Cards()
    work = r.add("employment", "Fabrikam", {"employer": "Company Name"})
    title = r.add("position", "Store Manager", {"title": "Store Manager", "start": "2019-03"}, work)
    r.add("accomplishment", "Grew sales 12%.", None, title)
    r.add(
        "education",
        "Bachelor of Science : Business Administration, Lakeshore College Chicago",
        {
            "degree": "Bachelor of Science : Business Administration",
            "institution": "Lakeshore College Chicago",
            "date": "2016",
        },
    )
    kinds = score(career, None, r.result()).kinds
    assert kinds.get("education school misread") == 1
    assert kinds.get("education year misread") == 1
    assert "education degree misread" not in kinds


def test_an_accomplishment_under_a_title_not_in_the_resume_says_so() -> None:
    store, assistant = (
        job("Store Manager", "2019-03", "2021-01", "Grew sales 12% in a year."),
        job("Assistant Manager", "2016-01", "2019-02", "Trained nine new cashiers."),
    )
    career = Career(
        key="titles",
        employments=[store.model_copy(update={"positions": store.positions + assistant.positions})],
    )
    r = Cards()
    work = r.add("employment", "Company Name", {"employer": "Company Name"})
    r.add("position", "Store Manager", {"title": "Store Manager", "start": "2019-03"}, work)
    # A title that is no title of the resume's, holding the job's bullets.
    wrong = r.add("position", "Night Cashier", {"title": "Night Cashier"}, work)
    card = r.add("accomplishment", "Grew sales 12% in a year.", None, wrong)
    scored = score(career, None, r.result())
    assert scored.kinds.get("accomplishment under a title the resume doesn't have") == 1
    assert "accomplishment under a title the resume doesn't have" in scored.marks[card.ref]
