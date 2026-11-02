"""Application settings (pydantic-settings). Every value can be set through the environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DataMode = Literal["real", "demo"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage. SQLite for local dev/tests; Postgres (+pgvector) in docker-compose.
    database_url: str = "sqlite:///./var/fx.db"
    auto_create_schema: bool = True  # create tables on startup (handy for SQLite; prod uses alembic)

    # Data mode served by this instance. Demo rows are never mixed into real queries.
    data_mode: DataMode = "real"
    seed_demo: bool = Field(default=False, validation_alias=AliasChoices("FX_SEED_DEMO", "SEED_DEMO"))

    # HTTP
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_key: str | None = None  # when set, protects /mcp and write endpoints (X-API-Key / Bearer)
    app_version: str = "0.1.0"

    # Event stream
    event_retention: int = 20000  # max events kept (oldest pruned first)
    event_retention_s: int = 86400  # events older than this are pruned
    stream_max_duration_s: float = 55.0  # bounded SSE connection; clients resume by cursor
    stream_heartbeat_s: float = 15.0
    stream_poll_s: float = 1.0
    stream_batch: int = 500

    # Collector
    poll_interval_s: int = 300
    worker_tick_s: int = 30  # worker wakes this often; sources are polled only when due
    backoff_max_s: int = 3600
    evidence_dir: str = "./var/evidence"
    history_default_grid_s: int = 300
    watch_min_interval_s: int = 60
    watch_max_interval_s: int = 900

    # Notifications (secrets only via environment)
    telegram_bot_token: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    alert_http_timeout_s: float = 10.0
    quotes_lookback_s: int = 7 * 86400  # how far back "latest per context" looks

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
