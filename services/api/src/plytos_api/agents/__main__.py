"""Runs the background workers until stopped: `python -m plytos_api.agents`.

One thread works through agent runs, another reads uploaded resumes, so a
long reading never holds up the conversation.
"""

import logging
import signal
import threading

from plytos_api.agents.crew import crew
from plytos_api.agents.runtime import BackgroundWorker, Worker
from plytos_api.config import get_settings
from plytos_api.db import Database
from plytos_api.imports.ai import reader_for
from plytos_api.imports.worker import ImportWorker
from plytos_api.keys import Vault, kek_from_setting

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    db = Database(settings.database_url)
    db.open()
    vault = Vault(kek_from_setting(settings.kek, allow_local=settings.dev_shortcuts))
    reader = reader_for(
        settings.ai_provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )
    workers = [
        BackgroundWorker(Worker(db, vault, crew(settings)), name="agents"),
        BackgroundWorker(ImportWorker(db, vault, reader), every_seconds=1.0, name="imports"),
    ]
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    for worker in workers:
        worker.start()
    log.info("Workers started")
    try:
        stop.wait()
    finally:
        for worker in workers:
            worker.stop()
        db.close()


if __name__ == "__main__":
    main()
