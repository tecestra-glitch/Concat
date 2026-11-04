"""Application settings (pydantic-settings). Every value can be set through the environment."""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("fronteira_fx.config")

DataMode = Literal["real", "simulation", "demo"]
PLACEHOLDER_PREFIX = "TROQUE_"  # `.env.example` placeholders (SEC-05)
SIMULATION_MODE: DataMode = "simulation"  # every persisted simulation row is tagged with this mode (D3)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage. SQLite for local dev/tests; Postgres (+pgvector) in docker-compose.
    database_url: str = "sqlite:///./var/fx.db"
    auto_create_schema: bool = True  # create tables on startup (handy for SQLite; prod uses alembic)

    # Data mode served by this instance. Demo rows are never mixed into real queries.
    data_mode: DataMode = "real"
    seed_demo: bool = Field(default=False, validation_alias=AliasChoices("FX_SEED_DEMO", "SEED_DEMO"))

    # Serverless (Vercel function fed by an external cron, see docs/deploy.md). Off = long-running process.
    serverless: bool = Field(default=False, validation_alias=AliasChoices("FX_SERVERLESS", "SERVERLESS"))
    # With an API key set, every /v1 read also needs the key (health and the cron route excepted): accounts, memory,
    # journal and alerts are personal. The frontend proxy injects the key only when the site itself is protected.
    private_reads: bool = Field(default=False, validation_alias=AliasChoices("FX_PRIVATE_READS", "PRIVATE_READS"))

    # HTTP
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_key: str | None = None  # when set, protects /mcp and write endpoints (X-API-Key / Bearer)
    cron_secret: str | None = None  # Bearer of POST /v1/internal/collect; unset = that route answers 404
    app_version: str = "0.1.0"

    # Event stream
    event_retention: int = 20000  # max events kept (oldest pruned first)
    event_retention_s: int = 86400  # events older than this are pruned
    stream_max_duration_s: float = 55.0  # bounded SSE connection; clients resume by cursor
    stream_retry_ms: int = 1000  # `retry:` sent on connect; serverless sets 30000 (reconnect every ~30 s)
    stream_heartbeat_s: float = 15.0
    stream_poll_s: float = 1.0
    stream_batch: int = 500

    # Collector
    poll_interval_s: int = 300
    worker_tick_s: int = 30  # worker wakes this often; sources are polled only when due
    backoff_max_s: int = 3600
    # Raw payloads captured by the collector. `FX_EVIDENCE_DIR` is a deprecated alias (warns at startup).
    evidence_dir: str = Field(
        default="./var/evidence", validation_alias=AliasChoices("EVIDENCE_DIR", "FX_EVIDENCE_DIR")
    )
    history_default_grid_s: int = 300
    watch_min_interval_s: int = 60
    watch_max_interval_s: int = 900
    collect_budget_s: float = 45  # one round started by POST /v1/internal/collect stops starting sources after this

    # Notifications (secrets only via environment)
    telegram_bot_token: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    alert_http_timeout_s: float = 10.0
    # Stream público da Binance (klines fechadas e bookTicker) no worker. Desligado por padrão: só liga com
    # FX_BINANCE_WS=1. Só leitura; HTTP 451 desliga a fonte (não há contorno). Ver market/binance_ws.py.
    binance_ws: bool = Field(default=False, validation_alias=AliasChoices("FX_BINANCE_WS"))
    binance_ws_url: str = Field(
        default="wss://data-stream.binance.vision/stream", validation_alias=AliasChoices("FX_BINANCE_WS_URL")
    )
    binance_ws_symbols: str = Field(
        default="BTCUSDT,ETHUSDT,USDTBRL", validation_alias=AliasChoices("FX_BINANCE_WS_SYMBOLS")
    )
    binance_ws_interval: str = "5m"
    binance_ws_rotate_s: int = 23 * 3600  # a Binance encerra a conexão em 24 h; renova antes (sem perder velas)
    binance_ws_overlap_s: float = 10.0  # tempo em que as duas conexões escutam ao mesmo tempo na renovação
    binance_ws_flush_s: float = 5.0  # gravação em lote no banco
    binance_ws_ping_s: float = 20.0  # ping do cliente; o pong de pings do servidor é automático
    quotes_lookback_s: int = 7 * 86400  # how far back "latest per context" looks
    # idade máxima da cotação mais velha de um plano antes de ele expirar (sem execução iniciada)
    plan_quote_max_age_s: int = 900

    # Mini navegador (fronteira-fx/browser, função Vercel): runs the browser-only adapters without a local Chromium
    # when both values are set. Secret only via environment; the URL must be https (http only for localhost).
    browser_url: str | None = Field(default=None, validation_alias=AliasChoices("FX_BROWSER_URL"))
    browser_secret: str | None = Field(default=None, validation_alias=AliasChoices("FX_BROWSER_SECRET"))
    remote_browser_min_interval_s: int = 7200  # Western Union at most every 2 h (Vercel free-plan CPU budget)

    # Conexões de contas (módulo connections). FX_CONNECTIONS_KEY é a chave mestra do cofre (AES-256-GCM, 32 bytes em
    # base64); sem ela o cofre fica desligado e as rotas que tocam em chaves respondem 503. Nunca vai para o frontend.
    connections_key: str | None = Field(default=None, validation_alias=AliasChoices("FX_CONNECTIONS_KEY"))
    # Open Finance por consentimento: desligado por padrão. Exige um agregador autorizado (ex.: pluggy) e as credenciais
    # dele; sem provedor a rota de consentimento responde "não configurado".
    openfinance_provider: str | None = Field(default=None, validation_alias=AliasChoices("FX_OPENFINANCE_PROVIDER"))
    openfinance_client_id: str | None = Field(default=None, validation_alias=AliasChoices("FX_OPENFINANCE_CLIENT_ID"))
    openfinance_client_secret: str | None = Field(
        default=None, validation_alias=AliasChoices("FX_OPENFINANCE_CLIENT_SECRET")
    )

    # Referências de câmbio (módulo market, U03). Tudo é REFERÊNCIA, nunca executável. Open Exchange Rates só entra
    # com OXR_APP_ID (chave só por variável de ambiente); sem ela a fonte fica desligada e nenhuma chamada é feita.
    oxr_app_id: str | None = Field(default=None, validation_alias=AliasChoices("OXR_APP_ID"))
    # teto mensal de chamadas à OXR (UTC). O plano gratuito permite 1.000; nunca passa de 1.000 (ver reference.py).
    oxr_monthly_cap: int = Field(default=1000, ge=0, validation_alias=AliasChoices("OXR_MONTHLY_CAP"))
    # desvio absoluto (%) entre duas fontes de referência para o mesmo instrumento que dispara alerta (acima dele)
    fx_reference_deviation_alert_pct: Decimal = Field(
        default=Decimal("1.0"), gt=0, validation_alias=AliasChoices("FX_REFERENCE_DEVIATION_ALERT_PCT")
    )
    # Macro (módulo market). Só variáveis de ambiente, tipo SecretStr (não aparece em repr). Sem FRED_API_KEY a
    # fonte FRED fica desligada. BRAPI_TOKEN só serve a testes e validação manual da B3 (nunca ao agendador).
    fred_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("FRED_API_KEY"))
    brapi_token: SecretStr | None = Field(default=None, validation_alias=AliasChoices("BRAPI_TOKEN"))

    # Knowledge base (RAG). `backend/knowledge/*.md` is seeded at startup, idempotently (hash per file);
    # `KNOWLEDGE_DIR` points elsewhere (e.g. inside a container image).
    # One-off alternative: `python -m fronteira_fx.cli seed-knowledge`.
    seed_knowledge: bool = True
    knowledge_dir: str | None = None

    @model_validator(mode="after")
    def _refuse_placeholder_secrets(self) -> Self:
        """SEC-05: the `TROQUE_ESTA_*` placeholders of `.env.example` are public; never run with them."""
        if self.api_key and self.api_key.strip().upper().startswith(PLACEHOLDER_PREFIX):
            raise ValueError("API_KEY ainda é o placeholder do .env.example; gere uma com `openssl rand -hex 32`")
        if self.cron_secret and self.cron_secret.strip().upper().startswith(PLACEHOLDER_PREFIX):
            raise ValueError("CRON_SECRET ainda é o placeholder do .env.example; gere com `openssl rand -hex 32`")
        if PLACEHOLDER_PREFIX in self.database_url.upper():
            raise ValueError(
                "POSTGRES_PASSWORD (DATABASE_URL) ainda é o placeholder do .env.example; "
                "gere com `openssl rand -hex 32`"
            )
        if self.connections_key and self.connections_key.strip().upper().startswith(PLACEHOLDER_PREFIX):
            raise ValueError(
                "FX_CONNECTIONS_KEY ainda é o placeholder do .env.example; gere com `openssl rand -base64 32`"
            )
        if self.oxr_app_id and self.oxr_app_id.strip().upper().startswith(PLACEHOLDER_PREFIX):
            raise ValueError("OXR_APP_ID ainda é o placeholder do .env.example; use a chave da sua conta OXR")
        if self.browser_secret and self.browser_secret.strip().upper().startswith(PLACEHOLDER_PREFIX):
            raise ValueError("FX_BROWSER_SECRET ainda é o placeholder do .env.example; gere com `openssl rand -hex 32`")
        return self

    @model_validator(mode="after")
    def _check_browser_remote(self) -> Self:
        """Empty values count as unset; the mini navegador URL must not expose the Bearer secret in clear text."""
        self.browser_secret = (self.browser_secret or "").strip() or None
        url = (self.browser_url or "").strip().rstrip("/")
        self.browser_url = url or None
        if url:
            parts = urlsplit(url)
            local = parts.hostname in ("localhost", "127.0.0.1", "::1")
            if parts.scheme != "https" and not (parts.scheme == "http" and local):
                raise ValueError("FX_BROWSER_URL precisa ser https:// (http só é aceito para localhost)")
        return self

    @model_validator(mode="after")
    def _normalise_reference_settings(self) -> Self:
        """Chave vazia conta como desligada; o teto mensal da OXR nunca passa de 1.000 (limite do plano gratuito)."""
        self.oxr_app_id = (self.oxr_app_id or "").strip() or None
        self.oxr_monthly_cap = min(self.oxr_monthly_cap, 1000)
        return self

    @model_validator(mode="after")
    def _normalise_connection_settings(self) -> Self:
        """Empty values count as unset (a blank line in `.env` must not enable anything)."""
        self.connections_key = (self.connections_key or "").strip() or None
        self.openfinance_provider = (self.openfinance_provider or "").strip().lower() or None
        self.openfinance_client_id = (self.openfinance_client_id or "").strip() or None
        self.openfinance_client_secret = (self.openfinance_client_secret or "").strip() or None
        return self

    @property
    def remote_browser_enabled(self) -> bool:
        return bool(self.browser_url and self.browser_secret)

    @model_validator(mode="after")
    def _warn_deprecated_env_names(self) -> Self:
        if "FX_EVIDENCE_DIR" in os.environ:
            log.warning("FX_EVIDENCE_DIR está obsoleto; use EVIDENCE_DIR (diretório em uso: %s)", self.evidence_dir)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cron_secret_enabled(self) -> bool:
        """An empty CRON_SECRET counts as unset: the internal collect route then answers 404."""
        return bool(self.cron_secret and self.cron_secret.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
