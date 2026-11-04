"""The import worker: reading kept uploads in the background.

Readers here are fakes, so nothing calls a model. The queue is shared by every
person in the test database, so each test drains it first with a worker that
reads by the rules, then checks only its own person's imports.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from uuid import UUID

import pytest

from plytos_api.agents.store import AgentStore
from plytos_api.db import Database
from plytos_api.imports.ai import AiResume
from plytos_api.imports.extract import ExtractedDocument
from plytos_api.imports.store import ImportNotFoundError, ImportStatus, ImportStore
from plytos_api.imports.worker import COULD_NOT_READ, ImportWorker
from plytos_api.keys import Vault

from .resume_samples import promotions_text

Stores = Callable[[UUID], AbstractContextManager[tuple[ImportStore, AgentStore]]]


@pytest.fixture
def stores(db: Database, vault: Vault) -> Stores:
    @contextmanager
    def _stores(user_id: UUID) -> Iterator[tuple[ImportStore, AgentStore]]:
        with db.as_user(user_id) as conn:
            cipher = vault.cipher_for(conn, user_id)
            yield ImportStore(conn, user_id, cipher), AgentStore(conn, user_id, cipher)

    return _stores


@pytest.fixture
def drained(db: Database, vault: Vault) -> None:
    """Reads whatever other tests left in the queue."""
    ImportWorker(db, vault, None, retry_base_seconds=0).run_until_idle()


def keep(stores: Stores, user: UUID, *, shared: bool = True) -> UUID:
    with stores(user) as (imports, agents):
        kept = imports.keep(promotions_text().encode(), "Avery Quinn.txt", "text")
        if shared:
            agents.share_resume(kept.id)
    return kept.id


def status(stores: Stores, user: UUID, import_id: UUID) -> ImportStatus:
    with stores(user) as (imports, _):
        return imports.status(import_id)


def answers(stores: Stores, user: UUID) -> list[str]:
    with stores(user) as (_, agents):
        return [m.text for m in agents.conversation() if m.author == "plytos"]


class Broken:
    name = "broken"

    def __init__(self) -> None:
        self.tries = 0

    def read(self, doc: ExtractedDocument) -> AiResume | None:
        self.tries += 1
        raise RuntimeError("the model is away")


def test_a_reading_that_keeps_breaking_is_tried_three_times_then_given_up(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)
    reader = Broken()

    ImportWorker(db, vault, reader, retry_base_seconds=0).run_until_idle()

    assert reader.tries == 3
    now = status(stores, user, import_id)
    assert (now.state, now.stage, now.error_code) == ("failed", None, "error_runtime_error")
    assert answers(stores, user) == [COULD_NOT_READ]


def test_a_reading_tried_again_after_it_failed_gets_its_own_answer(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)
    ImportWorker(db, vault, Broken(), retry_base_seconds=0).run_until_idle()
    assert answers(stores, user) == [COULD_NOT_READ]

    with stores(user) as (imports, _):
        assert imports.read_again(import_id).state == "reading"
    ImportWorker(db, vault, None).run_until_idle()
    ImportWorker(db, vault, None).run_until_idle()

    assert status(stores, user, import_id).state == "read"
    failed, read = answers(stores, user)
    assert failed == COULD_NOT_READ
    assert read.startswith("I read it: ")


def test_a_reading_that_breaks_waits_before_it_is_tried_again(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)
    reader = Broken()

    ImportWorker(db, vault, reader, retry_base_seconds=600).run_until_idle()

    # Tried once; the next try is ten minutes off, and nothing is said yet.
    assert reader.tries == 1
    now = status(stores, user, import_id)
    assert (now.state, now.error_code) == ("reading", "error_runtime_error")
    assert answers(stores, user) == []
    with db.as_user(user) as conn:
        row = conn.execute(
            "select attempts, run_after > now() + interval '9 minutes', locked_until"
            " from plytos.resume_import where id = %s",
            (import_id,),
        ).fetchone()
    assert row == (1, True, None)


def test_the_stage_shows_while_the_reading_runs(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)
    seen: list[ImportStatus] = []

    class Watching:
        name = "watching"

        def read(self, doc: ExtractedDocument) -> AiResume | None:
            # Another connection, as the person waiting would use, sees the stage.
            seen.append(status(stores, user, import_id))
            return None  # the rules read it instead

    ImportWorker(db, vault, Watching()).run_until_idle()

    assert [(s.state, s.stage) for s in seen] == [("reading", "structure")]
    done = status(stores, user, import_id)
    assert (done.state, done.stage, done.error_code) == ("read", None, None)
    [answer] = answers(stores, user)
    assert answer.startswith("I read it: ")


def test_a_reading_whose_worker_stopped_on_its_last_try_is_given_up(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)
    with db.as_user(user) as conn:
        # As if a worker claimed it a third time and stopped without a word.
        conn.execute(
            "update plytos.resume_import set attempts = 3,"
            " locked_until = now() - interval '1 minute' where id = %s",
            (import_id,),
        )

    ImportWorker(db, vault, Broken()).run_until_idle()

    now = status(stores, user, import_id)
    assert (now.state, now.error_code) == ("failed", "gave_up")
    assert answers(stores, user) == [COULD_NOT_READ]


def test_a_reading_still_leased_is_left_to_its_worker(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)
    with db.as_user(user) as conn:
        conn.execute(
            "update plytos.resume_import set attempts = 1,"
            " locked_until = now() + interval '5 minutes' where id = %s",
            (import_id,),
        )
    reader = Broken()

    ImportWorker(db, vault, reader).run_until_idle()

    assert reader.tries == 0
    assert status(stores, user, import_id).state == "reading"


def test_an_upload_deleted_while_it_is_read_is_left_alone(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user)

    class Deleting:
        name = "deleting"

        def read(self, doc: ExtractedDocument) -> AiResume | None:
            with stores(user) as (imports, _):
                imports.delete(import_id)
            return None

    ImportWorker(db, vault, Deleting()).run_until_idle()

    with stores(user) as (imports, _), pytest.raises(ImportNotFoundError):
        imports.status(import_id)
    assert answers(stores, user) == []


def test_an_upload_not_shared_in_the_conversation_gets_no_answer_there(
    db: Database, vault: Vault, make_user: Callable[[], UUID], stores: Stores, drained: None
) -> None:
    user = make_user()
    import_id = keep(stores, user, shared=False)

    ImportWorker(db, vault, Broken(), retry_base_seconds=0).run_until_idle()

    assert status(stores, user, import_id).state == "failed"
    assert answers(stores, user) == []


def take_over(db: Database, user: UUID, import_id: UUID) -> None:
    """As if this worker's lease ran out and another worker claimed the reading."""
    with db.as_user(user) as conn:
        conn.execute(
            "update plytos.resume_import set attempts = attempts + 1,"
            " locked_until = now() + interval '5 minutes' where id = %s",
            (import_id,),
        )


def lease(db: Database, user: UUID, import_id: UUID) -> tuple[int, bool, str | None]:
    with db.as_user(user) as conn:
        row = conn.execute(
            "select attempts, locked_until > now() + interval '4 minutes', error_code"
            " from plytos.resume_import where id = %s",
            (import_id,),
        ).fetchone()
    assert row is not None
    return row[0], row[1], row[2]


@pytest.mark.parametrize("ends", ["read", "broken"])
def test_a_worker_that_ran_past_its_lease_leaves_the_reading_to_the_one_that_took_over(
    db: Database,
    vault: Vault,
    make_user: Callable[[], UUID],
    stores: Stores,
    drained: None,
    ends: str,
) -> None:
    user = make_user()
    import_id = keep(stores, user)

    class Overtaken:
        name = "overtaken"

        def read(self, doc: ExtractedDocument) -> AiResume | None:
            take_over(db, user, import_id)
            if ends == "broken":
                raise RuntimeError("the model is away")
            return None

    ImportWorker(db, vault, Overtaken(), retry_base_seconds=0).run_once()

    # Neither its result nor its failure lands; the new claim's lease stands.
    assert status(stores, user, import_id).state == "reading"
    assert lease(db, user, import_id) == (2, True, None)
    assert answers(stores, user) == []


def test_each_stage_renews_the_lease_of_its_own_attempt_only(
    db: Database, make_user: Callable[[], UUID], stores: Stores
) -> None:
    user = make_user()
    import_id = keep(stores, user, shared=False)
    with db.as_user(user) as conn:
        conn.execute(
            "update plytos.resume_import set attempts = 1,"
            " locked_until = now() + interval '1 second' where id = %s",
            (import_id,),
        )
    with stores(user) as (imports, _):
        assert not imports.at_stage(import_id, 2, "structure", 300)
    assert lease(db, user, import_id)[1] is False
    with stores(user) as (imports, _):
        assert imports.at_stage(import_id, 1, "structure", 300)
    assert lease(db, user, import_id)[1] is True
    assert status(stores, user, import_id).stage == "structure"
    # Leave nothing in the queue for other tests.
    with stores(user) as (imports, _):
        imports.delete(import_id)
