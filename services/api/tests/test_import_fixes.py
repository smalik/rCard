"""The person's corrections while checking an import (imports/store.py): a card's
words or dates fixed before it's approved, kept across visits, taken back with an
undo, and counted by kind as numbers only."""

from datetime import date
from typing import Any

import pytest

from plytos_api.cards.model import MainContent
from plytos_api.cards.repository import Author, CardRepository
from plytos_api.imports.extract import extract
from plytos_api.imports.model import ImportResult, ProposedCard
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportConflictError, ImportNotFoundError, ImportStore
from tests.resume_samples import clean_pdf, messy_docx, title_first_text, two_column_pdf

TODAY = date(2026, 11, 5)
ME = Author("person")


def _result() -> ImportResult:
    return import_resume(title_first_text().encode(), "robin.txt", today=TODAY)


def _line(result: ImportResult, words: str) -> ProposedCard:
    return next(c for c in result.cards if words in c.content.framing.headline)


def _reworded(card: ProposedCard, headline: str) -> MainContent:
    return card.content.model_copy(
        update={"framing": card.content.framing.model_copy(update={"headline": headline})}
    )


def test_a_fix_is_kept_and_saved_in_the_persons_words(make_user, db: Any, vault: Any) -> None:
    result = _result()
    line = _line(result, "Cut load time")
    user = make_user()
    with db.as_user(user) as conn:
        cipher = vault.cipher_for(conn, user)
        store = ImportStore(conn, user, cipher)
        cards = CardRepository(conn, user, cipher)
        import_id = store.create(title_first_text().encode(), "robin.txt", result).id
        progress = store.fix(import_id, line.ref, _reworded(line, "Cut nightly load time by 40%."))
        assert progress.corrections == {"wording": 1}
        # It's still there on the next visit, and approving saves it as fixed.
        assert (
            store.get(import_id).progress.fixes[line.ref].framing.headline.startswith("Cut nightly")
        )
        for ref in _above(result, line):
            store.approve(import_id, ref, None, cards, ME)
        detail, _ = store.approve(import_id, line.ref, None, cards, ME)
        assert detail.main.content.framing.headline == "Cut nightly load time by 40%."


def _above(result: ImportResult, card: ProposedCard) -> list[str]:
    """The refs a card sits under, the top first."""
    refs: list[str] = []
    ref = card.parent_ref
    while ref is not None:
        refs.insert(0, ref)
        ref = next(c for c in result.cards if c.ref == ref).parent_ref
    return refs


def test_a_fix_can_be_taken_back(make_user, db: Any, vault: Any) -> None:
    result = _result()
    line = _line(result, "Cut load time")
    user = make_user()
    with db.as_user(user) as conn:
        store = ImportStore(conn, user, vault.cipher_for(conn, user))
        import_id = store.create(title_first_text().encode(), "robin.txt", result).id
        store.fix(import_id, line.ref, _reworded(line, "Cut load time by half."))
        progress = store.fix(import_id, line.ref, None)
        assert progress.fixes == {}
        # A fix that changes nothing isn't a correction.
        progress = store.fix(import_id, line.ref, line.content)
        assert progress.fixes == {} and progress.corrections == {"wording": 1}


def test_dates_and_moves_are_counted_by_kind(make_user, db: Any, vault: Any) -> None:
    result = _result()
    titles = [c for c in result.cards if c.kind == "position"]
    first, second = titles[0], titles[1]
    line = _line(result, "Cut load time")
    user = make_user()
    with db.as_user(user) as conn:
        store = ImportStore(conn, user, vault.cipher_for(conn, user))
        import_id = store.create(title_first_text().encode(), "robin.txt", result).id
        facts = {**first.content.facts, "start": "2005-07"}
        store.fix(import_id, first.ref, first.content.model_copy(update={"facts": facts}))
        other = second.ref if line.parent_ref == first.ref else first.ref
        progress = store.place(import_id, line.ref, other)
        assert progress.corrections == {"dates": 1, "moved": 1}
        # Only counts leave the person's words out of it.
        assert all(isinstance(n, int) for n in progress.corrections.values())


def test_an_approved_card_or_someone_elses_import_cant_be_fixed(
    make_user, db: Any, vault: Any
) -> None:
    result = _result()
    employer = next(c for c in result.cards if c.kind == "employment")
    me, someone = make_user(), make_user()
    with db.as_user(me) as conn:
        cipher = vault.cipher_for(conn, me)
        store = ImportStore(conn, me, cipher)
        import_id = store.create(title_first_text().encode(), "robin.txt", result).id
        store.approve(import_id, employer.ref, None, CardRepository(conn, me, cipher), ME)
        with pytest.raises(ImportConflictError, match="already approved"):
            store.fix(import_id, employer.ref, _reworded(employer, "Contoso"))
    with db.as_user(someone) as conn:
        theirs = ImportStore(conn, someone, vault.cipher_for(conn, someone))
        with pytest.raises(ImportNotFoundError):
            theirs.fix(import_id, employer.ref, None)


# -- where each line sits on its page ------------------------------------------


def test_every_pdf_line_knows_where_it_sits_on_its_page() -> None:
    for data in (clean_pdf(), two_column_pdf()):
        doc = extract(data, "made-up.pdf")
        assert doc.facts.page_sizes and all(w > 0 and h > 0 for w, h in doc.facts.page_sizes)
        tops: dict[int, list[float]] = {}
        for block in doc.blocks:
            assert block.box is not None, block.text
            left, top, right, bottom = block.box
            assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1
            tops.setdefault(block.page or 0, []).append(top)
        assert all(len(set(on_page)) > 1 for on_page in tops.values())


def test_a_line_that_wraps_is_one_box_around_both_rows() -> None:
    doc = extract(clean_pdf(), "made-up.pdf")
    heights = [b.box[3] - b.box[1] for b in doc.blocks if b.box is not None]
    single = min(heights)
    wrapped = [b for b in doc.blocks if b.box is not None and b.box[3] - b.box[1] > single * 1.6]
    assert wrapped, "the sample has a bullet that wraps onto a second row"


def test_word_files_have_no_page_places() -> None:
    doc = extract(messy_docx(), "made-up.docx")
    assert doc.facts.page_sizes == []
    assert all(b.box is None for b in doc.blocks)


def test_listing_files_reads_each_readings_outline_not_the_reading(
    make_user, db: Any, vault: Any
) -> None:
    result = _result()
    user = make_user()
    with db.as_user(user) as conn:
        store = ImportStore(conn, user, vault.cipher_for(conn, user))
        import_id = store.create(title_first_text().encode(), "robin.txt", result).id
        [listed] = store.summaries()
        assert listed.cards == len(result.cards)
        assert listed.to_settle == len(store.get(import_id).to_settle)

        # An import read before outlines were kept gets its outline the first
        # time it's listed, and says the same.
        conn.execute("update plytos.resume_import set outline_ciphertext = null")
        assert store.summaries() == [listed]
        kept = conn.execute("select outline_ciphertext is not null from plytos.resume_import")
        assert kept.fetchone() == (True,)
        assert store.summaries() == [listed]
