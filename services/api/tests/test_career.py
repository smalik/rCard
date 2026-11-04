"""The career tree: employments hold positions, positions hold accomplishments.

Every person in these tests is made up."""

from uuid import UUID

import psycopg
import pytest
from psycopg import errors

from plytos_api.cards.model import Framing, MainContent
from plytos_api.cards.repository import Author, ParentError
from plytos_api.imports.career import group_employments
from plytos_api.imports.dates import find_range
from plytos_api.imports.model import Role

from .conftest import DbUrls, RepoFor

ME = Author("person")


def content(headline: str, parent: UUID | None = None, **facts: str) -> MainContent:
    return MainContent(parent=parent, facts=dict(facts), framing=Framing(headline=headline))


def test_a_career_nests_employment_position_accomplishment(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        job = repo.create_card(
            "employment", content("Northwind Logistics", start="2014-03", end="present"), ME
        )
        director = repo.create_card(
            "position", content("Director", job.id, title="Director", start="2021-01"), ME
        )
        win = repo.create_card(
            "accomplishment", content("Cut late shipments by 22%", director.id), ME
        )
        assert (job.parent_id, director.parent_id, win.parent_id) == (None, job.id, director.id)
        assert repo.card_detail(win.id).main.content == content(
            "Cut late shipments by 22%", director.id
        )
        listed = {c.id: c.parent_id for c in repo.list_cards()}
        assert listed[win.id] == director.id
        assert repo.verify(win.id) == []


def test_a_win_across_promotions_sits_on_the_employment(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        job = repo.create_card("employment", content("Northwind Logistics"), ME)
        win = repo.create_card("accomplishment", content("Cut freight cost 30%", job.id), ME)
        assert win.parent_id == job.id


@pytest.mark.parametrize(
    ("kind", "parent_kind"),
    [
        ("accomplishment", "skill"),
        ("position", "position"),
        ("employment", "employment"),
        ("position", "accomplishment"),
        ("role", "employment"),
    ],
)
def test_a_card_only_sits_under_a_kind_that_can_hold_it(
    make_user, repo_for: RepoFor, kind: str, parent_kind: str
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        parent = repo.create_card(parent_kind, content("Parent"), ME)  # type: ignore[arg-type]
        with pytest.raises(ParentError, match="can't sit under"):
            repo.create_card(kind, content("Child", parent.id), ME)  # type: ignore[arg-type]


def test_the_database_refuses_a_bad_placement_on_its_own(
    make_user, repo_for: RepoFor, test_db: DbUrls
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        skill = repo.create_card("skill", content("Forecasting"), ME)
    with psycopg.connect(test_db.owner_url) as owner, pytest.raises(errors.CheckViolation):
        owner.execute(
            "insert into plytos.card (owner_id, kind, parent_id) values (%s, 'accomplishment', %s)",
            (user, skill.id),
        )


def test_nobody_can_put_a_card_under_someone_elses(
    make_user, repo_for: RepoFor, test_db: DbUrls
) -> None:
    alice, bob = make_user(), make_user()
    with repo_for(alice) as repo:
        job = repo.create_card("employment", content("Contoso"), ME)
    with repo_for(bob) as repo, pytest.raises(ParentError, match="doesn't exist"):
        repo.create_card("position", content("Analyst", job.id), ME)
    # Even past the app's checks, the parent must belong to the same person.
    with psycopg.connect(test_db.owner_url) as owner, pytest.raises(errors.ForeignKeyViolation):
        owner.execute(
            "insert into plytos.card (owner_id, kind, parent_id) values (%s, 'position', %s)",
            (bob, job.id),
        )


def test_moving_a_card_is_a_new_version(make_user, repo_for: RepoFor) -> None:
    user = make_user()
    with repo_for(user) as repo:
        job = repo.create_card("employment", content("Northwind Logistics"), ME)
        manager = repo.create_card("position", content("Senior Manager", job.id), ME)
        director = repo.create_card("position", content("Director", job.id), ME)
        win = repo.create_card("accomplishment", content("Rolled out 6 sites", director.id), ME)
        saved = repo.save_main_version(
            win.id, win.main.head.id, content("Rolled out 6 sites", manager.id), ME
        )
        assert saved.version.number == 2
        assert repo.card_detail(win.id).parent_id == manager.id
        # The first version still says where it used to sit.
        [v1, _] = repo.history(win.id, None)
        assert repo._main_content(v1).parent == director.id
        with pytest.raises(ParentError):
            repo.save_main_version(
                win.id, saved.version.id, content("Rolled out 6 sites", win.id), ME
            )


def test_the_app_role_can_only_change_where_a_card_sits(make_user, test_db: DbUrls) -> None:
    with psycopg.connect(test_db.app_url) as app, pytest.raises(errors.InsufficientPrivilege):
        app.execute("update plytos.card set kind = 'employment'")


# -- grouping a resume's roles into employments ------------------------------


def role(ref: str, org: str | None, title: str | None, dates: str | None, **kw: object) -> Role:
    return Role.model_validate(
        {
            "ref": ref,
            "organization": org,
            "title": title,
            "dates": find_range(dates) if dates else None,
            **kw,
        }
    )


def test_titles_under_one_employer_line_share_its_tenure() -> None:
    roles = [
        role("role-1", "Northwind Logistics", "Director", "Jan 2021 - Present", employer_block=3),
        role("role-2", "Northwind Logistics", "Manager", "Jun 2017 - Dec 2020", employer_block=3),
    ]
    [job] = group_employments(roles, {3: "Northwind Logistics, Chicago IL  Mar 2014 - Present"})
    assert job.role_refs == ["role-1", "role-2"]
    assert job.tenure_written
    assert job.dates is not None and job.dates.raw == "Mar 2014 - Present"
    assert [r.employment_ref for r in roles] == [job.ref, job.ref]


def test_back_to_back_titles_at_one_employer_are_one_employment() -> None:
    roles = [
        role("role-1", "Litware Inc.", "Lead Engineer", "Apr 2019 - Present"),
        role("role-2", "Litware", "Engineer", "Jan 2016 - Mar 2019"),
    ]
    [job] = group_employments(roles, {})
    assert job.organization == "Litware Inc."
    # No line on the resume states the whole stretch, so it's worked out.
    assert not job.tenure_written
    assert job.dates is not None and job.dates.raw == "Jan 2016 – Present"


def test_leaving_and_coming_back_is_two_employments() -> None:
    roles = [
        role("role-1", "Contoso", "Director", "Mar 2020 - Present"),
        role("role-2", "Contoso", "Analyst", "Jan 2014 - Jun 2017"),
    ]
    first, second = group_employments(roles, {})
    assert (first.role_refs, second.role_refs) == (["role-1"], ["role-2"])


def test_an_employer_in_between_splits_the_stints() -> None:
    roles = [
        role("role-1", "Contoso", "Director", "2021 - Present"),
        role("role-2", "Fabrikam", "Manager", "2019 - 2021"),
        role("role-3", "Contoso", "Analyst", "2016 - 2019"),
    ]
    assert len(group_employments(roles, {})) == 3


def test_client_work_joins_the_agency_employment() -> None:
    roles = [
        role("role-1", "Brightline Partners", "Consultant", "Jun 2010 - Feb 2014"),
        role("role-2", "Brightline Partners", None, None, client="Fabrikam", parent_ref="role-1"),
        role("role-3", "Brightline Partners", None, None, client="Tailspin", parent_ref="role-1"),
    ]
    [job] = group_employments(roles, {})
    assert job.role_refs == ["role-1", "role-2", "role-3"]
