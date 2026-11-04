"""`uv run fx-discover <url> [--seconds 20] [--out arquivo.json] [--scaffold <source_id>]`

Development tool only (not part of the API or the collector). One headless visit, no login, no stored cookies.
Exit codes: 0 ok, 1 capture/replay failure, 2 invalid input or unsafe URL, 3 visited the same host under 60 s ago.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from .probe import MIN_INTERVAL_S, ThrottleError, run_discovery, to_json_text
from .scaffold import ScaffoldError, scaffold
from .urlguard import UnsafeUrl, check_public_url

BACKEND = Path(__file__).resolve().parents[3]
STATE_FILE = BACKEND / ".local" / "fx-discover" / "visits.json"  # .local/ is gitignored
ADAPTERS_DIR = BACKEND / "src" / "fronteira_fx" / "adapters"
FIXTURES_DIR = BACKEND / "tests" / "adapters" / "fixtures"
TESTS_DIR = BACKEND / "tests" / "adapters"


def _summary(report: dict[str, Any]) -> str:
    lines = [
        f"fx-discover · {report['url']} · {report['seconds']:g} s · requisições vistas: {report['requests_seen']}",
        f"título: {report['title'] or '-'}",
    ]
    cands = report["candidates"]
    if not cands:
        lines.append("nenhum candidato.")
    else:
        lines.append("")
        lines.append(f"{'#':>2} {'score':>5} {'método':<6} {'tipo':<9} {'status':>6} {'sem nav.':<9} url")
        for c in cands:
            replay = c.get("replay") or {}
            sem_nav = "-" if not replay else ("sim" if replay.get("works_without_browser") else "não")
            lines.append(
                f"{c['rank']:>2} {c['score']:>5} {c['method']:<6} {(c['content_type'] or '-')[:9]:<9} "
                f"{str(c['status'] or '-'):>6} {sem_nav:<9} {c['url'][:120]}"
            )
            if c["rank"] == 1 and c["reasons"]:
                lines.append(f"   motivos: {'; '.join(c['reasons'])}")
            if c["rank"] == 1 and c["omitted_headers"]:
                lines.append(f"   cabeçalhos omitidos (precisam do navegador): {', '.join(c['omitted_headers'])}")
    lines.extend(f"nota: {n}" for n in report["notes"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fx-discover",
        description="Descobre endpoints internos de um site (uma visita headless, sem login) e ranqueia os candidatos.",
    )
    parser.add_argument("url", help="página pública http(s) do site")
    parser.add_argument("--seconds", type=float, default=20.0, help="tempo de observação após carregar (5 a 120)")
    parser.add_argument("--out", type=Path, help="grava o relatório JSON neste arquivo")
    parser.add_argument("--scaffold", metavar="SOURCE_ID", help="gera adaptador, fixture e teste (candidato 1)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        check_public_url(args.url)
    except UnsafeUrl as exc:
        print(f"URL recusada: {exc}", file=sys.stderr)
        return 2

    try:
        report = asyncio.run(run_discovery(args.url, seconds=args.seconds, state_file=STATE_FILE))
    except ThrottleError as exc:
        print(f"Sondagem mínima de {MIN_INTERVAL_S:.0f} s por fonte: {exc}", file=sys.stderr)
        return 3
    except UnsafeUrl as exc:
        print(f"URL recusada: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"falha na captura: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(to_json_text(report), encoding="utf-8")
        print(f"relatório gravado em {args.out}")

    if args.scaffold:
        from ..adapters.registry import ADAPTERS

        if not report["candidates_internal"]:
            print("sem candidato para gerar adaptador", file=sys.stderr)
            return 1
        try:
            paths = scaffold(
                args.scaffold,
                report["candidates_internal"][0],
                adapters_dir=ADAPTERS_DIR,
                fixtures_dir=FIXTURES_DIR,
                tests_dir=TESTS_DIR,
                existing_ids=set(ADAPTERS),
            )
        except ScaffoldError as exc:
            print(f"scaffold recusado: {exc}", file=sys.stderr)
            return 2
        print("\nGerado (não registrado no registry; revise e complete os TODO):")
        for p in (paths.adapter, paths.fixture, paths.test):
            print(f"  {p}")
        print("Depois de mapear o parse: adicione o módulo a adapters/registry.py e rode os testes.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
