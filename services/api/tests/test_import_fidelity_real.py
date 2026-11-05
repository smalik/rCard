"""Scoring real resumes: labels with gaps, stand-in employers, near words, and labels
made from a resume builder's web page. Everyone here is made up."""

import csv
import hashlib
import os
from pathlib import Path

from plytos_api.cards.model import Framing, MainContent
from plytos_api.imports.fidelity.archive import career_from_html, convert, date, items
from plytos_api.imports.fidelity.real import load_labels, read_label
from plytos_api.imports.fidelity.score import norm, report, score
from plytos_api.imports.fidelity.truth import (
    PRESENT,
    Career,
    Employment,
    Group,
    Position,
)
from plytos_api.imports.model import Contact, DocumentFacts, ImportResult, ProposedCard

# -- a reading built by hand ----------------------------------------------------------


class Cards:
    def __init__(self) -> None:
        self.cards: list[ProposedCard] = []

    def add(
        self,
        kind: str,
        headline: str,
        facts: dict[str, object] | None = None,
        parent: ProposedCard | None = None,
    ) -> ProposedCard:
        card = ProposedCard.model_validate(
            {
                "ref": f"card-{len(self.cards) + 1}",
                "kind": kind,
                "content": MainContent(
                    facts=facts or {},  # type: ignore[arg-type]
                    framing=Framing(headline=headline),
                ),
                "parent_ref": parent.ref if parent else None,
            }
        )
        self.cards.append(card)
        return card

    def result(self) -> ImportResult:
        return ImportResult(
            facts=DocumentFacts(format="pdf", filename="resume.pdf"),
            contact=Contact(),
            sections=[],
            roles=[],
            cards=self.cards,
            findings=[],
            blocks=[],
        )


def job(title: str, start: str, end: str, *bullets: str) -> Employment:
    return Employment(
        employer="Company Name",
        positions=[Position(title=title, start=start, end=end, groups=[Group(items=[*bullets])])],
    )


TWO_STAND_INS = Career(
    key="stand-ins",
    anonymous_employers=True,
    employments=[
        job("Store Manager", "2019-03", PRESENT, "Grew sales 12% in two years."),
        job("Assistant Manager", "2016-01", "2019-02", "Trained nine new cashiers."),
    ],
)


def two_stand_ins(*, merged: bool = False) -> Cards:
    """A reading of TWO_STAND_INS: each job its own employment, or (as a reader may
    well do with two employers of the same name) both under one."""
    r = Cards()
    first = r.add("employment", "Company Name", {"employer": "Company Name"})
    store = r.add(
        "position",
        "Store Manager",
        {"title": "Store Manager", "start": "2019-03", "end": "present"},
        first,
    )
    r.add("accomplishment", "Grew sales 12% in two years.", None, store)
    second = first if merged else r.add("employment", "Company Name", {"employer": "Company Name"})
    assistant = r.add(
        "position",
        "Assistant Manager",
        {"title": "Assistant Manager", "start": "2016-01", "end": "2019-02"},
        second,
    )
    r.add("accomplishment", "Trained nine new cashiers.", None, assistant)
    return r


def test_stand_in_employers_are_scored_by_title_alone() -> None:
    for merged in (False, True):
        s = score(TWO_STAND_INS, None, two_stand_ins(merged=merged).result())
        assert s.employers.of == 0
        assert (s.extra, s.misattributed, s.employers_split) == (0, 0, 0)
        assert s.items.right == s.items.of == 2
        assert s.positions.right == 2


def test_an_accomplishment_under_the_other_stand_in_job_is_misattributed() -> None:
    r = two_stand_ins()
    trained = next(c for c in r.cards if c.content.framing.headline.startswith("Trained"))
    trained.parent_ref = "card-2"
    s = score(TWO_STAND_INS, None, r.result())
    assert s.misattributed == 1


def test_jobs_with_one_name_are_told_apart_by_their_dates() -> None:
    career = Career(
        key="twice",
        employments=[
            Employment(
                employer="Fabrikam",
                positions=[Position(title="Lead", start="2020-01", end=PRESENT)],
            ),
            Employment(
                employer="Fabrikam",
                positions=[Position(title="Analyst", start="2014-01", end="2016-01")],
            ),
        ],
    )
    r = Cards()
    # Read in the opposite order: only the dates say which is which.
    old = r.add("employment", "Fabrikam", {"employer": "Fabrikam", "start": "2014-01"})
    old.content.facts["end"] = "2016-01"
    r.add("position", "Analyst", {"title": "Analyst", "start": "2014-01", "end": "2016-01"}, old)
    new = r.add("employment", "Fabrikam", {"employer": "Fabrikam", "start": "2020-01"})
    new.content.facts["end"] = "present"
    r.add("position", "Lead", {"title": "Lead", "start": "2020-01", "end": "present"}, new)
    s = score(career, None, r.result())
    assert s.employers.right == 2
    assert s.positions.right == 2
    assert s.dates.right == s.dates.of == 8


def test_words_misread_from_a_scan_still_count_but_are_noted() -> None:
    r = two_stand_ins()
    grew = next(c for c in r.cards if c.content.framing.headline.startswith("Grew"))
    grew.content.framing.headline = "Grew saies 12% in two vears."
    s = score(TWO_STAND_INS, None, r.result())
    assert s.items.right == 2
    assert s.garbled == 1
    assert s.kinds == {"accomplishment misread": 1}


def test_what_a_label_leaves_out_is_not_invented() -> None:
    career = TWO_STAND_INS.model_copy(
        update={"unscored_kinds": ["skill"], "unscored": ["Fluent in Spanish and French"]}
    )
    r = two_stand_ins()
    r.add("skill", "Languages", {"category": "Languages", "skills": ["Spanish"]})
    r.add("activity", "Fluent in Spanish and French")
    r.add("accomplishment", "Something nobody wrote.")
    s = score(career, None, r.result())
    assert s.extra == 1
    assert s.kinds == {"accomplishment invented": 1}


def test_what_a_label_doesnt_say_isnt_scored() -> None:
    career = Career(
        key="sparse",
        employments=[
            Employment(employer="Tailspin", positions=[Position(title="Driver", start="2018")])
        ],
    )
    r = Cards()
    tailspin = r.add("employment", "Tailspin", {"employer": "Tailspin", "start": "2018-06"})
    r.add("position", "Driver", {"title": "Driver", "start": "2018-06"}, tailspin)
    s = score(career, None, r.result())
    # Only the start was written, as a year: the year is all that's asked for.
    assert s.dates.right == s.dates.of == 2
    assert s.contact.of == 0
    assert s.others.of == 0
    assert s.fidelity == 1.0


def test_a_private_report_holds_no_words() -> None:
    r = two_stand_ins()
    r.cards = [c for c in r.cards if not c.content.framing.headline.startswith("Grew")]
    s = score(TWO_STAND_INS, None, r.result(), kind="pdf", name="RETAIL")
    text = report([s], private=True)
    assert "Grew" not in text
    assert "Store Manager" not in text
    assert "accomplishment lost" in text
    assert "RETAIL" in text


# -- a resume builder's web page --------------------------------------------------------

# The shape of the pages: sections by field code; a job's fields by code in their ids.
PAGE = """
<div class="fontsize fontface" id="document">
 <div class="section firstsection" id="SECTION_NAME101">
  <div class="paragraph PARAGRAPH_NAME firstparagraph" id="PARAGRAPH_1_2_3">
   <div class="name"><span class="field" id="11FNAM1"></span>
    <span class="field" id="11LNAM1">STORE MANAGER</span></div>
  </div>
 </div>
 <div class="section" id="SECTION_SUMM102">
  <div class="heading"><div class="sectiontitle" id="SECTNAME_SUMM102">Summary</div></div>
  <div class="paragraph firstparagraph" id="PARAGRAPH_4_5_6">
   <div class="field singlecolumn" id="12FRFM1"><p>Retail manager who opens stores
     on time. Known for calm holiday seasons.</p></div>
  </div>
 </div>
 <div class="section" id="SECTION_HILT103">
  <div class="heading"><div class="sectiontitle" id="SECTNAME_HILT103">Skill Highlights</div></div>
  <div class="paragraph firstparagraph" id="PARAGRAPH_7_8_9">
   <table class="twocol"><tbody><tr>
    <td class="field twocol_1" id="13SKC1">
     <ul><li>Scheduling</li><li>Inventory control</li></ul></td>
    <td class="field twocol_2" id="13SKC2"><ul><li>Visual merchandising</li></ul></td>
   </tr></tbody></table>
  </div>
 </div>
 <div class="section" id="SECTION_ACCM104">
  <div class="heading"><div class="sectiontitle" id="SECTNAME_ACCM104">Accomplishments</div></div>
  <div class="paragraph firstparagraph" id="PARAGRAPH_10_11_12">
   <div class="field singlecolumn" id="14FRFM1"><p>Awards</p>
    <ul><li>Store of the Year for the northeast region.</li></ul></div>
  </div>
 </div>
 <div class="section" id="SECTION_EXPR105">
  <div class="heading"><div class="sectiontitle" id="SECTNAME_EXPR105">Experience</div></div>
  <div class="paragraph firstparagraph" id="PARAGRAPH_13_14_15">
   <div class="singlecolumn">
    <span class="paddedline"><span class="jobtitle" id="15JTIT1">Store Manager</span><br>
     <span><span class="jobdates" id="15JSTD1" format="%B %Y">March 2019</span>
     <span>to</span> <span class="jobdates" id="15EDDT1" format="%B %Y">Current</span></span></span>
    <span class="paddedline"><span class="companyname" id="15COMP1">Company Name</span>
     <span>-</span> <span class="joblocation jobcity" id="15JCIT1">City</span><span>,</span>
     <span class="joblocation jobstate" id="15JSTA1">State</span></span>
    <span class="paddedline"><span class="jobline" id="15JDES1">
     <p>Run a store of 40 people.</p>
     <ul><li>Grew sales 12% in two years.</li>
      <li>Cut shrink from 2.1%
       to 1.3%.</li></ul></span></span>
   </div>
  </div>
  <div class="paragraph" id="PARAGRAPH_16_17_18">
   <div class="singlecolumn">
    <span class="paddedline txtCenter">
     <span class="companyname" id="16COMP1">Company Name</span></span>
    <span class="paddedline"><span class="jobtitle" id="16JTIT1">Assistant Manager</span>
     <span class="datesWrapper"><span class="jobdates" id="16JSTD1" format="%m/%Y">01/2016</span>
     <span>to</span><span class="jobdates" id="16EDDT1" format="%m/%Y">02/2019</span></span></span>
    <span class="paddedline"><span class="jobline" id="16JDES1">Trained nine new cashiers.<br>
     &bull; Opened the store on weekends.</span></span>
   </div>
  </div>
 </div>
 <div class="section" id="SECTION_EDUC106">
  <div class="heading"><div class="sectiontitle" id="SECTNAME_EDUC106">Education</div></div>
  <div class="paragraph firstparagraph" id="PARAGRAPH_19_20_21">
   <div class="singlecolumn">
    <span class="paddedline"><span class="degree" id="17DGRE1">Bachelor of Science</span>
     <span>:</span> <span class="programline" id="17STUY1">Business Administration</span>
     <span>,</span> <span class="jobdates" id="17GRYR1">May 2015</span></span>
    <span class="paddedline"><span class="companyname companyname_educ" id="17SCHO1">Lakeshore
     College</span></span>
    <span class="paddedline"><span class="field" id="17FRFM1"><p>Dean's list.</p></span></span>
   </div>
  </div>
 </div>
</div>
"""


def test_a_web_page_becomes_a_label() -> None:
    career, left_out = career_from_html(PAGE, key="k", source="/x/RETAIL/1.pdf")
    assert career.anonymous_employers
    assert (
        career.summary == "Retail manager who opens stores on time. Known for calm holiday seasons."
    )
    store, assistant = (e.positions[0] for e in career.employments)
    assert (store.title, store.start, store.end) == ("Store Manager", "2019-03", PRESENT)
    assert store.items == [
        "Run a store of 40 people.",
        "Grew sales 12% in two years.",
        "Cut shrink from 2.1% to 1.3%.",
    ]
    assert (assistant.title, assistant.start, assistant.end) == (
        "Assistant Manager",
        "2016-01",
        "2019-02",
    )
    assert assistant.items == ["Trained nine new cashiers.", "Opened the store on weekends."]
    assert career.employments[0].location == "City, State"
    [school] = career.education
    assert (school.school, school.degree, school.field, school.year) == (
        "Lakeshore College",
        "Bachelor of Science",
        "Business Administration",
        "2015",
    )
    assert [h.text for h in career.highlights] == ["Store of the Year for the northeast region."]
    # Skills, the label over the accomplishments, the name line and the coursework
    # aren't scored, so a reader's cards for them aren't held against it.
    assert {"Scheduling", "Visual merchandising", "Awards", "STORE MANAGER", "Dean's list."} <= set(
        career.unscored
    )
    assert "skill" in career.unscored_kinds
    assert "Skill Highlights" not in career.unscored
    assert sorted(left_out) == ["section HILT", "section NAME"]


def test_dates_as_the_builder_writes_them() -> None:
    assert date("01/2016") == "2016-01"
    assert date("1 2016") == "2016-01"
    assert date("September 2012") == "2012-09"
    assert date("Sep 2012") == "2012-09"
    assert date("Sep2012") == "2012-09"
    assert date("2012") == "2012"
    assert date("Current") == PRESENT
    assert date("") is None


def test_a_paragraph_is_read_a_sentence_at_a_time() -> None:
    import lxml.html

    element = lxml.html.fragment_fromstring(
        "<div><p>Led the team. Cut costs 5%.</p><p>- Hired four people</p></div>"
    )
    assert items(element) == ["Led the team.", "Cut costs 5%.", "Hired four people"]


def test_a_folder_of_pages_becomes_private_labels(tmp_path: Path) -> None:
    pdfs = tmp_path / "data"
    (pdfs / "RETAIL").mkdir(parents=True)
    pdf = pdfs / "RETAIL" / "1001.pdf"
    pdf.write_bytes(b"%PDF-1.4 a made-up file")
    sheet = tmp_path / "Resume.csv"
    with sheet.open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(["ID", "Resume_str", "Resume_html", "Category"])
        out.writerow(["1001", "", PAGE, "RETAIL"])
        out.writerow(["1002", "", PAGE, "RETAIL"])  # no PDF
        out.writerow(["1003", "", "<div>nothing marked up</div>", "RETAIL"])
    (pdfs / "RETAIL" / "1003.pdf").write_bytes(b"%PDF-1.4 another")
    labels = tmp_path / "labels"
    counts = convert(sheet, pdfs, labels)
    assert counts["labelled"] == 1
    assert counts["skipped: no PDF"] == 1
    assert counts["skipped: no jobs marked up"] == 1
    assert counts["accomplishments"] == 5
    key = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    written = labels / f"{key}.json"
    assert os.stat(written).st_mode & 0o777 == 0o600
    [career], bad = load_labels(labels)
    assert bad == 0
    assert career.source == str(pdf)


def test_a_label_for_another_file_is_not_scored_against_it(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 changed since it was labelled")
    career = TWO_STAND_INS.model_copy(update={"source": str(pdf), "key": "0" * 16})
    s = read_label(career)
    assert s is not None
    assert s.failed == "LabelIsForAnotherFile"


def test_a_stand_in_employer_in_a_hand_label_is_treated_as_unknown() -> None:
    career = TWO_STAND_INS.model_copy(update={"anonymous_employers": False})
    s = score(career, None, two_stand_ins(merged=True).result())
    assert s.employers.of == 0
    assert (s.misattributed, s.extra) == (0, 0)


def test_text_copied_out_wrongly_still_compares() -> None:
    assert norm("Sales &amp; marketing") == norm("Sales & marketing")
    assert norm("Didnâ€™t miss a deadline") == norm("Didn’t miss a deadline")
    assert norm("Led teamsÂ of 12") == norm("Led teams of 12")


def test_a_job_with_no_title_is_paired_with_one_read_without_a_title() -> None:
    career = Career(
        key="untitled",
        employments=[
            Employment(
                employer="Fabrikam",
                positions=[Position(title="", groups=[Group(items=["Kept the books."])])],
            )
        ],
    )
    r = Cards()
    fabrikam = r.add("employment", "Fabrikam", {"employer": "Fabrikam"})
    untitled = r.add("position", "Title not found", {}, fabrikam)
    r.add("accomplishment", "Kept the books.", None, untitled)
    s = score(career, None, r.result())
    assert s.positions.right == s.positions.of == 1
    assert s.items.right == 1
    assert s.extra == 0


def test_the_same_words_under_two_jobs_are_each_found_under_their_own() -> None:
    career = Career(
        key="twins",
        anonymous_employers=True,
        employments=[
            job("Store Manager", "2019-03", PRESENT, "Ran the weekly stock count."),
            job("Assistant Manager", "2016-01", "2019-02", "Ran the weekly stock count."),
        ],
    )
    r = two_stand_ins()
    for card in r.cards:
        if card.kind == "accomplishment":
            card.content.framing.headline = "Ran the weekly stock count."
    s = score(career, None, r.result())
    assert (s.items.right, s.misattributed) == (2, 0)


def test_a_generic_sub_heading_is_no_workstream() -> None:
    career = TWO_STAND_INS.model_copy(deep=True)
    career.employments[0].positions[0].groups[0].label = "Key Achievements:"
    r = two_stand_ins()
    grew = next(c for c in r.cards if c.content.framing.headline.startswith("Grew"))
    grew.content.facts["workstream"] = "Responsibilities"
    s = score(career, None, r.result())
    assert s.groups.of == 0
    assert s.kinds == {}
