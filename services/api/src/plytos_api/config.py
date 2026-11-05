"""Runtime settings, read from PLYTOS_* environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLYTOS_")

    # "prod" is the default so a missing setting never turns on dev shortcuts.
    env: Literal["dev", "test", "prod"] = "prod"
    database_url: str = "postgresql://localhost:5432/plytos"
    # Key-encryption key that wraps each person's data key.
    #   local:<base64 of 32 bytes>   dev and test only
    #   gcp-kms:projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>
    kek: str = ""
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR
    # Comma-separated login roles to grant plytos_app after migrating
    # (Cloud SQL IAM users for the API service account).
    app_login_roles: str = ""
    # Reading resumes with Claude (imports/ai.py). "off" uses the rule-based parser only.
    #   anthropic  the Claude API; the key comes from ANTHROPIC_API_KEY
    #   vertex     Claude on Google Cloud Vertex AI, with the service's own identity
    ai_provider: Literal["off", "anthropic", "vertex"] = "off"
    ai_model: str = "claude-haiku-5-5"
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    ai_vertex_project: str = ""
    ai_vertex_region: str = "global"
    # Agents (agents/). Inline runs a worker on a thread inside the API, for
    # development; production runs `python -m plytos_api.agents` as its own service.
    agents_inline: bool = False
    # Reads uploaded resumes on a thread inside the API, so an upload is read
    # wherever the API runs. Turn it off once a separate worker reads them.
    imports_inline: bool = True
    # How long the Stitcher waits after a note, so a burst of notes is read together.
    stitch_delay_seconds: int = 30
    # How long the Summarizer waits after accomplishments change, so a burst of
    # edits to one job is summed up once.
    summary_delay_seconds: int = 20

    @property
    def dev_shortcuts(self) -> bool:
        return self.env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
