import threading
from uuid import UUID

import psycopg
import pytest

from plytos_api.cards.model import Framing, VariantContent
from plytos_api.cards.repository import (
    Author,
    CardNotFoundError,
    CardRepository,
    StaleHeadError,
    UnsupportedClaimsError,
    VariantExistsError,
)
from plytos_api.db import Database
from plytos_api.keys import Vault

from .conftest import DbUrls, RepoFor, main_content

ME = Author("person")


def variant(headline: str) -> VariantContent:
    return VariantContent(framing=Framing(headline=headline))


def test_new_card_starts_its_main_line_at_v1(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        assert card.main.head.number == 1
        assert card.main.head.parent_id is None
        assert card.main.content == main_content()
        assert repo.verify(card.id) == []


def test_each_save_appends_the_next_numbered_version(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        v2 = repo.save_main_version(card.id, card.main.head.id, main_content(team_size="7"), ME)
        v3 = repo.save_main_version(card.id, v2.version.id, main_content(team_size="8"), ME)
        history = repo.history(card.id, None)
        assert [v.number for v in history] == [1, 2, 3]
        assert history[2].parent_id == v2.version.id
        assert v3.version.chain_hash != v2.version.chain_hash
        assert repo.verify(card.id) == []
        assert repo.card_detail(card.id).main.content == main_content(team_size="8")


def test_saving_from_an_old_version_is_refused(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        v2 = repo.save_main_version(card.id, card.main.head.id, main_content(team_size="7"), ME)
        with pytest.raises(StaleHeadError) as stale:
            repo.save_main_version(card.id, card.main.head.id, main_content(team_size="9"), ME)
        assert stale.value.current_head_id == v2.version.id


def test_concurrent_saves_from_the_same_version_let_only_one_win(
    make_user, db: Database, vault: Vault, repo_for: RepoFor
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
    base = card.main.head.id

    first_saved = threading.Event()
    release_first = threading.Event()
    errors: list[BaseException] = []

    def first() -> None:
        with db.as_user(user) as conn:
            repo = CardRepository(conn, user, vault.cipher_for(conn, user))
            repo.save_main_version(card.id, base, main_content(team_size="7"), ME)
            first_saved.set()
            release_first.wait(5)

    def second() -> None:
        first_saved.wait(5)
        try:
            with db.as_user(user) as conn:
                repo = CardRepository(conn, user, vault.cipher_for(conn, user))
                repo.save_main_version(card.id, base, main_content(team_size="9"), ME)
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()
    first_saved.wait(5)
    # The second save is now blocked behind the first, uncommitted one.
    threading.Timer(0.3, release_first.set).start()
    t1.join(10)
    t2.join(10)

    assert len(errors) == 1 and isinstance(errors[0], StaleHeadError)
    with repo_for(user) as repo:
        assert [v.number for v in repo.history(card.id, None)] == [1, 2]
        assert repo.card_detail(card.id).main.content == main_content(team_size="7")


def test_variant_rewords_and_records_the_main_version_it_is_based_on(
    make_user, repo_for: RepoFor
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        finance = repo.create_target("industry", "Finance", None)
        jpm = repo.create_target("company", "JP Morgan", finance.id)
        detail = repo.create_variant(
            card.id, jpm.id, variant("Shortened the financial close from 10 to 4 days"), ME
        )
        (line,) = detail.variants
        assert line.target_id == jpm.id
        assert line.head.number == 1
        assert line.head.based_on_main_version_id == card.main.head.id
        assert line.based_on_main_number == 1
        assert line.state == "current"
        assert [t.name for t in repo.list_targets()] == ["Finance", "JP Morgan"]
        assert repo.verify(card.id) == []


def test_variant_cannot_add_a_number(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        pharma = repo.create_target("industry", "Pharma", None)
        with pytest.raises(UnsupportedClaimsError) as err:
            repo.create_variant(card.id, pharma.id, variant("Cut close time 60%"), ME)
        assert '"60%"' in err.value.problems[0]


def test_one_variant_per_target(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        pharma = repo.create_target("industry", "Pharma", None)
        repo.create_variant(card.id, pharma.id, variant("Faster close"), ME)
        with pytest.raises(VariantExistsError):
            repo.create_variant(card.id, pharma.id, variant("Quicker close"), ME)


def test_correcting_a_fact_marks_variants_behind_until_refreshed(
    make_user, repo_for: RepoFor
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        pharma = repo.create_target("industry", "Pharma", None)
        detail = repo.create_variant(card.id, pharma.id, variant("Close down to 4 days"), ME)
        variant_head = detail.variants[0].head.id

        corrected = main_content(
            headline="Cut month-end close from 10 days to 5", close_days_after="5"
        )
        saved = repo.save_main_version(card.id, card.main.head.id, corrected, ME)
        assert saved.variants_marked_behind == [detail.variants[0].id]
        assert repo.card_detail(card.id).variants[0].state == "behind"

        # The old wording now cites a number main no longer has.
        with pytest.raises(UnsupportedClaimsError):
            repo.save_variant_version(
                card.id, pharma.id, variant_head, variant("Close down to 4 days"), ME
            )
        refreshed = repo.save_variant_version(
            card.id, pharma.id, variant_head, variant("Close down to 5 days"), ME
        )
        line = repo.card_detail(card.id).variants[0]
        assert line.state == "current"
        assert line.head.id == refreshed.version.id
        assert line.head.number == 2
        assert line.based_on_main_number == 2


def test_rewording_main_leaves_variants_current(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        pharma = repo.create_target("industry", "Pharma", None)
        repo.create_variant(card.id, pharma.id, variant("Close down to 4 days"), ME)
        saved = repo.save_main_version(
            card.id, card.main.head.id, main_content(headline="Monthly close in 4 days"), ME
        )
        assert saved.variants_marked_behind == []
        assert repo.card_detail(card.id).variants[0].state == "current"


def test_list_cards_summarizes_heads(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        repo.save_main_version(card.id, card.main.head.id, main_content(team_size="7"), ME)
        (summary,) = repo.list_cards()
        assert summary.id == card.id
        assert summary.main_version == 2
        assert summary.headline == "Cut month-end close from 10 days to 4"


def test_content_and_target_names_are_encrypted_at_rest(
    make_user, repo_for: RepoFor, test_db: DbUrls
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        repo.create_target("company", "JP Morgan", None)
    with psycopg.connect(test_db.owner_url) as owner:
        (ciphertext,) = owner.execute(
            "select content_ciphertext from plytos.card_version where card_id = %s", (card.id,)
        ).fetchone()
        (name,) = owner.execute(
            "select name_ciphertext from plytos.target where owner_id = %s", (user,)
        ).fetchone()
    assert b"Acme" not in bytes(ciphertext) and b"month-end" not in bytes(ciphertext)
    assert b"Morgan" not in bytes(name)


def test_unknown_card_is_not_found(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo, pytest.raises(CardNotFoundError):
        repo.card_detail(UUID(int=1))
