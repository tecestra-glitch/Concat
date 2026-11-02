"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import Settings
from ..services.collector import Collector


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


def get_collector(request: Request) -> Collector:
    return request.app.state.collector


CollectorDep = Annotated[Collector, Depends(get_collector)]


def api_key_matches(settings: Settings, x_api_key: str | None, authorization: str | None) -> bool:
    if not settings.api_key:
        return True
    if x_api_key == settings.api_key:
        return True
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() == settings.api_key
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
