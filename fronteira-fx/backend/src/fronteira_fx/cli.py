"""Operational commands: `python -m fronteira_fx.cli seed-knowledge [--database-url URL] [--dir PATH]`.

The same seeding runs at API startup (`SEED_KNOWLEDGE=true`, the default); the command exists for images or
deployments that start the API with `SEED_KNOWLEDGE=false` and seed from a one-off job instead."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Settings
from .db import create_schema, make_engine, make_session_factory, session_scope
from .services.rag import default_knowledge_dir, seed_knowledge


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fronteira_fx.cli", description="Comandos operacionais do Fronteira FX.")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-knowledge", help="semeia backend/knowledge/*.md no corpus do RAG (idempotente)")
    seed.add_argument("--database-url", help="sobrescreve DATABASE_URL")
    seed.add_argument("--dir", help="diretório com os arquivos .md (padrão: KNOWLEDGE_DIR ou backend/knowledge)")
    return parser


def _seed_knowledge(args: argparse.Namespace) -> int:
    overrides = {"database_url": args.database_url} if args.database_url else {}
    settings = Settings(**overrides)
    directory = args.dir or settings.knowledge_dir or default_knowledge_dir()
    engine = make_engine(settings.database_url)
    try:
        if settings.auto_create_schema:
            create_schema(engine)
        with session_scope(make_session_factory(engine)) as session:
            stats = seed_knowledge(session, directory, data_mode=settings.data_mode)
    finally:
        engine.dispose()
    print(
        f"Base de conhecimento ({settings.data_mode}) em {directory}: "
        f"{stats['added']} adicionado(s), {stats['updated']} atualizado(s), {stats['unchanged']} sem mudança, "
        f"{stats['skipped']} ignorado(s)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "seed-knowledge":
        return _seed_knowledge(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
