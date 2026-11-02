"""Shared FastAPI dependencies."""

from __future__ import annotations

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..config import DataMode, Settings
from ..services.collector import Collector

LIKE_ESCAPE = "\\"


def like_literal(value: str) -> str:
    """Make `value` a literal LIKE fragment: `%`, `_` and the escape char itself lose their meaning."""
    escaped = value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    return escaped.replace("%", f"{LIKE_ESCAPE}%").replace("_", f"{LIKE_ESCAPE}_")


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_db(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbDep = Annotated[Session, Depends(get_db)]


def get_data_mode(settings: SettingsDep) -> str:
    return settings.data_mode


DataModeDep = Annotated[str, Depends(get_data_mode)]


def require_instance_mode(
    settings: SettingsDep,
    data_mode: Annotated[
        DataMode | None,
        Query(
            description=(
                "Modo que o cliente espera. Cada instância serve um único data_mode: se este valor diferir "
                "do modo da instância, a resposta é 409 e nada é lido nem gravado. Ausente = modo da instância."
            ),
        ),
    ] = None,
) -> None:
    """SEC-01: modes never mix. Mounted on every /v1 router except `/v1/health` (how a client learns the mode)."""
    if data_mode is not None and data_mode != settings.data_mode:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"esta instância serve data_mode={settings.data_mode}; o pedido declarou data_mode={data_mode}. "
                "Os modos nunca se misturam: aponte para uma instância nesse modo ou mude a preferência."
            ),
        )


def get_collector(request: Request) -> Collector:
    return request.app.state.collector


CollectorDep = Annotated[Collector, Depends(get_collector)]


def _same_secret(given: str, expected: str) -> bool:
    """Constant-time comparison (SEC-08): the response time never tells how much of the key matched."""
    return hmac.compare_digest(given.encode(), expected.encode())


def api_key_matches(settings: Settings, x_api_key: str | None, authorization: str | None) -> bool:
    if not settings.api_key:
        return True
    if x_api_key is not None and _same_secret(x_api_key, settings.api_key):
        return True
    if authorization and authorization.lower().startswith("bearer "):
        return _same_secret(authorization[7:].strip(), settings.api_key)
    return False


def require_api_key(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Enforced only when API_KEY is configured (write endpoints and /mcp)."""
    if not api_key_matches(settings, x_api_key, authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida ou ausente")


ApiKey = Depends(require_api_key)
