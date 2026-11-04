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

    @property
    def dev_shortcuts(self) -> bool:
        return self.env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
