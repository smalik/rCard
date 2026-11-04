from plytos_api.cards.model import Framing, MainContent, VariantContent
from plytos_api.cards.rules import facts_changed, number_tokens, unsupported_claims

from .conftest import main_content


def variant(headline: str, body: str = "", shown: list[str] | None = None) -> VariantContent:
    return VariantContent(framing=Framing(headline=headline, body=body, shown_facts=shown))


def test_number_tokens_normalize_money_percent_and_separators() -> None:
    assert number_tokens("Grew revenue $1,200,000 (18 %) in 2023") == {"1200000", "18%", "2023"}
    assert number_tokens("$1.2M pipeline, 3k users") == {"1.2m", "3k"}


def test_variant_may_reword_using_numbers_from_main() -> None:
    main = main_content()
    v = variant("Shortened the financial close from 10 to 4 days", "Led a team of 6.")
    assert unsupported_claims(v, main) == []


def test_variant_may_not_introduce_a_number() -> None:
    main = main_content()
    problems = unsupported_claims(variant("Cut close time 60%"), main)
    assert len(problems) == 1
    assert '"60%"' in problems[0]


def test_variant_may_not_show_a_fact_main_lacks() -> None:
    main = main_content()
    problems = unsupported_claims(variant("Closed faster", shown=["employer", "budget"]), main)
    assert problems == ['shows a fact "budget" that the main card does not have']


def test_facts_changed_ignores_framing_only_edits() -> None:
    before = main_content()
    reworded = main_content(headline="Brought the monthly close down to 4 days")
    corrected = main_content(close_days_after="5")
    assert not facts_changed(before, reworded)
    assert facts_changed(before, corrected)
    assert facts_changed(None, before)


def test_list_fact_values_count_as_support() -> None:
    main = MainContent.model_validate(
        {"facts": {"skills": ["SQL", "Python 3"]}, "framing": {"headline": "Data work"}}
    )
    assert unsupported_claims(variant("Python 3 automation"), main) == []
