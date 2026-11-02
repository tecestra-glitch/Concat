"""FastAPI application factory. `fronteira_fx.main:app` is the ASGI entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import v1_router
from .api.deps import api_key_matches
from .config import Settings, get_settings
from .db import create_schema, make_engine, make_session_factory
from .mcp import mount_mcp
from .services.collector import Collector
from .services.demo import ensure_demo_seeded

log = logging.getLogger("fronteira_fx")

DESCRIPTION = (
    "Terminal pessoal de câmbio BRL/USD/PYG (Ciudad del Este, Asunción, Pedro Juan Caballero; "
    "Western Union, ueno, Nomad, Revolut, casas de câmbio). Valores monetários trafegam como strings decimais."
)


def create_app(settings: Settings | None = None, *, mount_mcp_server: bool = True) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_schema:
            create_schema(engine)
        seeded = ensure_demo_seeded(session_factory, settings)
        if seeded:
            log.info("demo data seeded: %s", seeded)
        yield
        engine.dispose()

    app = FastAPI(
        title="Fronteira FX API",
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.collector = Collector(session_factory, settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.middleware("http")
    async def mcp_api_key_guard(request: Request, call_next):
        if settings.api_key and request.url.path.startswith("/mcp"):
            if not api_key_matches(settings, request.headers.get("x-api-key"), request.headers.get("authorization")):
                return JSONResponse({"detail": "API key inválida ou ausente"}, status_code=status.HTTP_401_UNAUTHORIZED)
        return await call_next(request)

    app.include_router(v1_router)
    if mount_mcp_server:
        app.state.mcp = mount_mcp(app)
    return app


app = create_app()
