"""Runs the agent worker until stopped: `python -m plytos_api.agents`."""

import logging
import signal
import threading

from plytos_api.agents.crew import crew
from plytos_api.agents.runtime import Worker
from plytos_api.config import get_settings
from plytos_api.db import Database
from plytos_api.keys import Vault, kek_from_setting

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    db = Database(settings.database_url)
    db.open()
    vault = Vault(kek_from_setting(settings.kek, allow_local=settings.dev_shortcuts))
    worker = Worker(db, vault, crew(settings))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log.info("Agent worker started")
    try:
        while not stop.is_set():
            try:
                if worker.run_once() == 0:
                    stop.wait(2.0)
            except Exception as exc:
                log.warning("Agent worker round failed: %s", type(exc).__name__)
                stop.wait(5.0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
