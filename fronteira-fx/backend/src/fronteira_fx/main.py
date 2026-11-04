"""FastAPI application factory. `fronteira_fx.main:app` is the ASGI entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import v1_router
from .api.deps import api_key_matches
from .config import Settings, get_settings
from .db import create_schema, make_engine, make_session_factory, session_scope
from .market.demo import seed_market_demo
from .mcp import mount_mcp
from .services.collector import Collector
from .services.demo import ensure_demo_seeded
from .services.rag import default_knowledge_dir, seed_knowledge

log = logging.getLogger("fronteira_fx")

DESCRIPTION = (
    "Terminal pessoal de câmbio BRL/USD/PYG (Ciudad del Este, Asunción, Pedro Juan Caballero; "
    "Western Union, ueno, Nomad, Revolut, casas de câmbio). Valores monetários trafegam como strings decimais."
)


PUBLIC_V1_PATHS = frozenset({"/v1/health"})


def create_app(settings: Settings | None = None, *, mount_mcp_server: bool = True) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url, serverless=settings.serverless)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_schema:
            create_schema(engine)
        seeded = ensure_demo_seeded(session_factory, settings)
        if seeded:
            log.info("demo data seeded: %s", seeded)
        market_rows = seed_market_demo(session_factory, settings)
        if market_rows:
            log.info("market demo seeded: %d rows", market_rows)
        if settings.seed_knowledge:
            knowledge_dir = settings.knowledge_dir or default_knowledge_dir()
            with session_scope(session_factory) as session:
                stats = seed_knowledge(session, knowledge_dir, data_mode=settings.data_mode)
            log.info("knowledge base (%s) from %s: %s", settings.data_mode, knowledge_dir, stats)
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
    app.state.exchange_transport = None  # httpx transport para as corretoras; só os testes injetam um mock

    @app.exception_handler(RequestValidationError)
    async def _validation_errors(request: Request, exc: RequestValidationError):
        # Um 422 do FastAPI devolve `input`, que em /v1/connections é a chave da corretora: ele some daqui.
        if request.url.path.startswith("/v1/connections"):
            errors = [
                {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
                for e in exc.errors()
            ]
            return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": errors})
        return await request_validation_exception_handler(request, exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.middleware("http")
    async def private_reads_guard(request: Request, call_next):
        path = request.url.path
        if (
            settings.private_reads
            and settings.api_key
            and request.method != "OPTIONS"
            and path.startswith("/v1/")
            and path not in PUBLIC_V1_PATHS
            and not path.startswith("/v1/internal/")  # own Bearer (CRON_SECRET)
            and not api_key_matches(settings, request.headers.get("x-api-key"), request.headers.get("authorization"))
        ):
            return JSONResponse({"detail": "API key inválida ou ausente"}, status_code=status.HTTP_401_UNAUTHORIZED)
        return await call_next(request)

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
