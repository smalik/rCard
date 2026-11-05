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
from plytos_api.imports.fidelity.truth import MORGAN, Career, School, SkillGroup
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


def test_a_line_heading_a_run_of_bullets_is_a_workstream_in_the_label() -> None:
    import lxml.html

    from plytos_api.imports.fidelity.archive import groups

    description = lxml.html.fromstring(
        "<div><p>Ran a store of 40 people.</p><p>Key Projects</p>"
        "<ul><li>Opened two stores.</li><li>Moved the stockroom.</li></ul>"
        "<p>Team: Finance</p><ul><li>Closed the books in 3 days.</li></ul>"
        "<p>Short line</p><p>Followed by prose, not bullets.</p></div>"
    )
    assert [(g.label, g.items) for g in groups(description)] == [
        (None, ["Ran a store of 40 people."]),
        ("Key Projects", ["Opened two stores.", "Moved the stockroom."]),
        (
            "Team: Finance",
            ["Closed the books in 3 days.", "Short line", "Followed by prose, not bullets."],
        ),
    ]


def test_skills_count_wherever_the_reading_grouped_them() -> None:
    career = Career(
        key="skills",
        employments=[job("Store Manager", "2019-03", "2021-01", "Grew sales 12%.")],
        skills=[
            SkillGroup(category="Languages", items=["Python", "SQL"]),
            SkillGroup(category="Tools", items=["Git", "Excel"]),
        ],
    )
    r = Cards()
    work = r.add("employment", "Fabrikam", {"employer": "Company Name"})
    title = r.add("position", "Store Manager", {"title": "Store Manager", "start": "2019-03"}, work)
    r.add("accomplishment", "Grew sales 12%.", None, title)
    r.add("skill", "Skills", {"category": "Skills", "skills": ["Python", "SQL", "Git"]})
    scored = score(career, None, r.result())
    assert scored.kinds.get("skills grouped differently") == 1
    # Excel isn't anywhere: that group is misread, the other is right.
    assert scored.kinds.get("skills misread") == 1
    assert scored.others.right == 1 and scored.others.of == 2


def test_a_city_and_state_count_for_a_whole_address() -> None:
    career = Career(
        key="where",
        location="12 Oak Way, Boston, MA 02118",
        employments=[job("Store Manager", "2019-03", "2021-01", "Grew sales 12%.")],
    )
    r = Cards()
    work = r.add("employment", "Fabrikam", {"employer": "Company Name"})
    title = r.add("position", "Store Manager", {"title": "Store Manager", "start": "2019-03"}, work)
    r.add("accomplishment", "Grew sales 12%.", None, title)
    result = r.result()
    result.contact.location = "Boston, MA 02118"
    assert "contact location lost" not in score(career, None, result).kinds
    result.contact.location = "Springfield, IL"
    assert "contact location lost" in score(career, None, result).kinds


def test_the_city_and_state_are_kept_from_an_address_line() -> None:
    from plytos_api.imports.model import Block
    from plytos_api.imports.segment import parse_contact

    def where(text: str) -> str | None:
        return parse_contact([Block(index=0, text=text)]).location

    assert where("123 Main St, Springfield, IL 62701") == "Springfield, IL 62701"
    assert where("123 Main St Springfield IL 62701") == "Springfield IL 62701"
    assert where("Springfield , IL") == "Springfield, IL"
    assert where("12 Oak Way Apt 4 Boston MA 02118") == "Boston MA 02118"


def test_a_label_can_be_read_written_out_as_a_word_file() -> None:
    from plytos_api.imports.fidelity.layouts import WORD
    from plytos_api.imports.fidelity.real import read_label

    # No file of its own: the layout writes the label out.
    career = MORGAN.model_copy(update={"key": "0" * 16, "source": "/nowhere/resume.pdf"})
    scored = read_label(career, layout=WORD[0])
    assert scored is not None and scored.failed is None
    assert scored.layout == WORD[0].name and scored.kind == "docx"
    assert scored.fidelity == 1.0


def test_a_label_without_a_place_dates_or_title_is_written_without_them() -> None:
    from plytos_api.imports.extract import extract
    from plytos_api.imports.fidelity.layouts import WORD
    from plytos_api.imports.fidelity.truth import Employment, Group, Position

    career = Career(
        key="bare",
        name="Pat Lee",
        employments=[
            Employment(
                employer="Company Name",
                positions=[
                    Position(
                        title="Cashier",
                        start="2016-03",
                        end="2019-05",
                        groups=[Group(items=["Processed returns", "Trained four new cashiers"])],
                    )
                ],
            ),
            Employment(
                employer="Fabrikam Retail",
                positions=[Position(title="", groups=[Group(items=["Opened the store"])])],
            ),
        ],
    )
    for layout in WORD:
        text = "\n".join(b.text for b in extract(layout.render(career), "resume.docx").blocks)
        assert "None" not in text, layout.name
        assert " – \n" not in text and not text.rstrip().endswith("–"), layout.name
    paragraphs = next(lay for lay in WORD if lay.name == "word-paragraphs")
    text = "\n".join(b.text for b in extract(paragraphs.render(career), "resume.docx").blocks)
    assert "Processed returns. Trained four new cashiers." in text


def test_a_shape_can_show_a_label_written_out_as_a_word_file() -> None:
    from plytos_api.imports.fidelity.layouts import WORD

    classic = next(lay for lay in WORD if lay.name == "word-classic")
    reading = import_resume(classic.render(MORGAN), "resume.docx", today=TODAY, reader=None)
    shown = show(MORGAN, reading, classic)
    assert shown.startswith(f"== {MORGAN.key} (word-classic)")
    assert "Reading (100%)" in shown
    assert MORGAN.employments[0].employer.lower() not in shown.lower()


def test_a_title_with_how_the_job_was_held_after_it_is_the_same_title() -> None:
    from plytos_api.imports.fidelity.score import same_title

    assert same_title("Data Analyst", "Data Analyst (Contract)")
    assert same_title("Data Analyst (Contract)", "Data Analyst (Contract)")
    assert same_title("", "")
    assert not same_title("Data Analyst", "Data Analyst (Northwind)")
    career = Career(
        key="contract",
        employments=[job("Data Analyst (Contract)", "2019-03", "2021-01", "Built sales reports.")],
    )
    r = Cards()
    work = r.add("employment", "Company Name", {"employer": "Company Name"})
    title = r.add(
        "position",
        "Data Analyst",
        {"title": "Data Analyst", "employment_type": "contract", "start": "2019-03"},
        work,
    )
    r.add("accomplishment", "Built sales reports.", None, title)
    scored = score(career, None, r.result())
    assert scored.misattributed == 0 and "title lost" not in scored.kinds


def test_a_tight_budget_waits_for_room_instead_of_skipping(tmp_path: Path) -> None:
    import json
    import time
    from concurrent.futures import ThreadPoolExecutor

    from plytos_api.imports.bench import Ledger

    path = tmp_path / "spend.json"
    path.write_text(json.dumps({"spent_usd": 0.0, "most_per_resume_usd": 0.04}))
    ledger = Ledger(path, budget=0.10)  # room for two at a time
    read: list[int] = []

    def one(n: int) -> None:
        if not ledger.may_start():
            return
        time.sleep(0.02)
        ledger.add(0.01)
        read.append(n)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, range(6)))
    assert sorted(read) == list(range(6))
    # With nothing running and no room, it says no at once.
    path.write_text(json.dumps({"spent_usd": 0.09, "most_per_resume_usd": 0.04}))
    assert not Ledger(path, budget=0.10).may_start()


def test_a_phone_written_another_countrys_way_is_found_on_a_contact_line() -> None:
    from plytos_api.imports.model import Block
    from plytos_api.imports.segment import parse_contact

    def phones(text: str) -> list[str]:
        return parse_contact([Block(index=0, text=text)]).phones

    assert phones("Phone: (555) 555 55 55") == ["(555) 555 55 55"]
    assert phones("Mobile: +919845012345 • Pune") == ["+919845012345"]
    assert phones("+44 20 7946 0958") == ["+44 20 7946 0958"]
    assert phones("Call 312-555-0142 or 312-555-0143") == ["312-555-0142", "312-555-0143"]
    # Years, ZIP codes and street numbers aren't phones.
    for text in ["2015 2016 2017", "Springfield, IL 62704-1234", "Jan 2019 - Present"]:
        assert phones(text) == [], text
