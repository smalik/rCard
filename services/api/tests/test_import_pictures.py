"""Reading the words in a resume's pictures (imports/pictures.py and the picture parts of
extract.py and ai.py), without calling Claude. The resumes are made up
(tests/resume_samples.py), and a fake reader stands in for Claude."""

import io
import json
from datetime import date
from typing import Any

import anthropic
import httpx2
import pytest
from docx import Document
from docx.shared import Pt
from PIL import Image

from plytos_api.imports.ai import AiPictures, AiResume, ClaudeReader
from plytos_api.imports.extract import _prepared, extract
from plytos_api.imports.model import ExtractedDocument, PictureImage
from plytos_api.imports.pictures import add_picture_lines, page_picture
from plytos_api.imports.pipeline import import_resume
from tests.resume_samples import _png, consultant_docx, pictured_pdf, scanned_pdf

TODAY = date(2026, 11, 4)
SCREENSHOT = "Cut forecast error 18% for the planning team."


class FakeReader:
    """Reads pictures as told, and leaves the structure to the rules."""

    name = "fake-model"

    def __init__(self, pictures: list[dict[str, Any]] | None) -> None:
        self.pictures = pictures
        self.asked: list[list[PictureImage]] = []

    def read_pictures(self, images: list[PictureImage]) -> AiPictures | None:
        self.asked.append(images)
        if self.pictures is None:
            return None
        return AiPictures.model_validate({"pictures": self.pictures})

    def read(self, doc: ExtractedDocument) -> AiResume | None:
        return None


def _line(text: str, *, bullet: bool = False, bold: bool = False) -> dict[str, Any]:
    return {"text": text, "bullet": bullet, "bold": bold}


def _text(*lines: dict[str, Any], picture: int = 1) -> dict[str, Any]:
    return {"picture": picture, "kind": "text", "lines": list(lines)}


def test_a_word_screenshot_is_kept_to_read_after_the_line_above_it() -> None:
    doc = extract(consultant_docx(), "riley.docx")
    assert len(doc.images) == 1
    image = doc.images[0]
    assert doc.blocks[image.after_block or 0].text == "Built a demand forecast used by 40 planners."
    assert image.picture is not None and doc.facts.pictures[image.picture].width_in == 6.5
    assert image.media_type == "image/png" and image.data.startswith(b"\x89PNG")
    # The pixels never leave with the document.
    assert "images" not in doc.model_dump()


def test_icons_are_too_small_to_read() -> None:
    word = Document()
    word.add_paragraph("Avery Chen")
    word.add_picture(io.BytesIO(_png(12, 12)), width=Pt(12), height=Pt(12))
    out = io.BytesIO()
    word.save(out)
    doc = extract(out.getvalue(), "avery.docx")
    assert len(doc.facts.pictures) == 1 and doc.images == []


def test_a_scanned_pdf_page_is_kept_whole() -> None:
    doc = extract(scanned_pdf(), "scan.pdf")
    assert doc.blocks == [] and not doc.facts.has_text_layer
    assert doc.facts.scanned_pages == [1]
    assert len(doc.images) == 1
    assert doc.images[0].picture is None and doc.images[0].page == 1
    assert doc.images[0].after_block is None


def test_a_pdf_picture_is_kept_but_a_panel_behind_text_is_not() -> None:
    doc = extract(pictured_pdf(), "casey.pdf")
    texts = [b.text for b in doc.blocks]
    assert texts[:2] == ["Casey Morgan", "casey.morgan@example.com"]
    # The shaded panel has text over it, so it's a background, not a picture of words.
    assert len(doc.facts.pictures) == 1 and len(doc.images) == 1
    assert doc.images[0].after_block == 1 and doc.images[0].page == 1
    assert doc.facts.pictures[0].width_in > 4


def test_pictures_that_cant_be_read_are_skipped() -> None:
    assert _prepared(b"not a picture") is None
    clear = Image.new("RGBA", (30, 10), (0, 0, 0, 0))
    out = io.BytesIO()
    clear.save(out, "PNG")
    prepared = _prepared(out.getvalue())
    assert prepared is not None and prepared[0] == "image/png"
    assert Image.open(io.BytesIO(prepared[1])).mode == "RGB"


def test_words_in_a_screenshot_become_lines_after_the_line_above_it() -> None:
    reader = FakeReader([_text(_line("• " + SCREENSHOT))])
    result = import_resume(consultant_docx(), "riley.docx", today=TODAY, reader=reader)
    assert len(reader.asked) == 1

    texts = [b.text for b in result.blocks]
    at = texts.index(SCREENSHOT)
    assert texts[at - 1] == "Built a demand forecast used by 40 planners."
    read = result.blocks[at]
    assert read.where == "image" and read.is_bullet and read.bullet_char == "•"
    assert [b.index for b in result.blocks] == list(range(len(result.blocks)))

    card = next(c for c in result.cards if at in c.source_blocks)
    assert card.kind == "accomplishment"
    # Read from a picture, it's checked against the page once, not asked about here.
    assert card.needs_check == []

    big = next(f for f in result.findings if f.rule == "ats.large_image")
    assert "holds 1 line of text. Plytos read them" in big.detail
    assert big.locations[0].block == at - 1
    assert result.facts.pictures[0].lines_read == 1
    assert result.lines is not None and at not in result.lines.guessed


def test_a_logo_or_photo_adds_no_lines() -> None:
    before = import_resume(consultant_docx(), "riley.docx", today=TODAY)
    reader = FakeReader([{"picture": 1, "kind": "photo", "lines": [_line("Riley")]}])
    after = import_resume(consultant_docx(), "riley.docx", today=TODAY, reader=reader)
    assert [b.text for b in after.blocks] == [b.text for b in before.blocks]
    big = next(f for f in after.findings if f.rule == "ats.large_image")
    assert "If it shows text" in big.detail


def test_when_pictures_cant_be_read_the_import_goes_on() -> None:
    before = import_resume(consultant_docx(), "riley.docx", today=TODAY)
    after = import_resume(consultant_docx(), "riley.docx", today=TODAY, reader=FakeReader(None))
    assert [b.text for b in after.blocks] == [b.text for b in before.blocks]


def test_a_scanned_resume_is_read_from_its_picture() -> None:
    reader = FakeReader(
        [
            _text(
                _line("Casey Morgan", bold=True),
                _line("casey.morgan@example.com"),
                _line("EXPERIENCE", bold=True),
                _line("Operations Lead, Tailspin Toys  2019 - 2024", bold=True),
                _line("Ran a warehouse team of 12 people.", bullet=True),
                _line("Cut shipping errors by 40% in a year.", bullet=True),
            )
        ]
    )
    result = import_resume(scanned_pdf(), "scan.pdf", today=TODAY, reader=reader)
    assert all(b.where == "image" and b.page == 1 for b in result.blocks)
    assert result.contact.name == "Casey Morgan"
    no_text = next(f for f in result.findings if f.rule == "ats.no_text")
    assert "Plytos read the words from the picture" in no_text.detail
    results = [c for c in result.cards if c.kind == "accomplishment"]
    assert {c.content.framing.headline for c in results} >= {
        "Cut shipping errors by 40% in a year."
    }
    # The page is checked as a whole beside its cards, not a question on every card.
    asked = [q for c in result.cards for q in c.needs_check]
    assert not any("picture" in q for q in asked)


def test_a_page_is_drawn_to_check_its_cards_against() -> None:
    picture = page_picture(scanned_pdf(), 1)
    assert picture is not None
    with Image.open(io.BytesIO(picture)) as page:
        assert page.format == "JPEG" and page.width == 1000
    assert page_picture(scanned_pdf(), 2) is None
    assert page_picture(b"not a pdf", 1) is None


def test_a_scan_with_no_reader_still_says_it_has_no_text() -> None:
    result = import_resume(scanned_pdf(), "scan.pdf", today=TODAY)
    assert result.blocks == [] and result.cards == []
    no_text = next(f for f in result.findings if f.rule == "ats.no_text")
    assert "Plytos read" not in no_text.detail


def test_lines_from_a_picture_before_any_text_come_first() -> None:
    doc = extract(scanned_pdf(), "scan.pdf")
    found = AiPictures.model_validate(
        {"pictures": [_text(_line("Casey Morgan")), _text(_line("ignored"), picture=9)]}
    )
    read = add_picture_lines(doc, found)
    assert [b.text for b in read.blocks] == ["Casey Morgan"]
    assert read.images == [] and read.facts.word_count == 2


def _client(handler: Any) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="test",
        base_url="https://api.test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def test_claude_reads_pictures_at_low_effort_with_each_one_labelled() -> None:
    sent: list[dict[str, Any]] = []
    answer = {"pictures": [_text(_line(SCREENSHOT, bullet=True))]}

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

    doc = extract(consultant_docx(), "riley.docx")
    found = ClaudeReader(_client(handler), "claude-haiku-5-5", "medium").read_pictures(doc.images)
    assert found is not None and found.pictures[0].lines[0].text == SCREENSHOT
    body = sent[0]
    assert body["output_config"]["effort"] == "low"
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Picture 1: an image placed in the resume."}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["media_type"] == "image/png"


def test_a_scan_whose_pictures_hold_no_words_is_unreadable() -> None:
    from plytos_api.imports.extract import UnsupportedFileError

    class Blind:
        name = "blind"

        def read(self, doc: Any) -> None:
            return None

        def read_pictures(self, images: Any) -> AiPictures:
            return AiPictures.model_validate({"pictures": []})

    with pytest.raises(UnsupportedFileError):
        import_resume(scanned_pdf(), "scan.pdf", today=TODAY, reader=Blind())  # type: ignore[arg-type]


def test_pages_drawn_from_many_threads_at_once_all_come_back() -> None:
    # PDFium can't draw from two threads at once; requests come in on many.
    from concurrent.futures import ThreadPoolExecutor

    data = scanned_pdf()
    with ThreadPoolExecutor(max_workers=6) as pool:
        drawn = list(pool.map(lambda _: page_picture(data, 1), range(18)))
    assert all(d is not None and d.startswith(b"\xff\xd8") for d in drawn)
