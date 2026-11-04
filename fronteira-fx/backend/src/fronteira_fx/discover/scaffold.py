"""Turns the best discovery candidate into an adapter skeleton, a sanitised fixture and an offline parse test.

Nothing is registered: `adapters/registry.py` stays untouched, a human reviews the files first. The generated
parse test fails on purpose until the TODO mapping is written. Files that already exist are never overwritten.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .redact import scrub_raw

SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9]{1,30}$")


class ScaffoldError(ValueError):
    pass


@dataclass(slots=True)
class ScaffoldPaths:
    adapter: Path
    fixture: Path
    test: Path


def _class_name(source_id: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[_-]", source_id)) + "Adapter"


def _json_keys(body: bytes) -> list[str]:
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return []
    keys: list[str] = []
    if isinstance(data, dict):
        keys = list(data.keys())
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        keys = [f"[].{k}" for k in data[0].keys()]
    return keys[:40]


def _adapter_source(source_id: str, cand: dict[str, Any], *, is_json: bool, keys: list[str]) -> str:
    cls = _class_name(source_id)
    host = urlsplit(cand["url"]).hostname or ""
    home = f"{urlsplit(cand['url']).scheme}://{host}/"
    method = "official_api" if is_json else "html"
    integration = "endpoint_interno" if is_json else "html"
    reasons = "; ".join(cand.get("reasons") or []) or "sem motivos"
    key_hint = ", ".join(keys) if keys else "(HTML: estrutura a mapear)"
    accept_name = "ACCEPT_JSON" if is_json else "ACCEPT_HTML"
    headers_hint = ", ".join(cand.get("required_headers", {})) or "nenhum"
    replay_note = "sem navegador: " + (
        "funcionou no replay" if (cand.get("replay") or {}).get("works_without_browser") else "NÃO confirmado"
    )
    return f'''"""{host} — ESQUELETO gerado por fx-discover em {datetime.now(tz=UTC):%Y-%m-%d}. NÃO REGISTRADO.

Candidato: {cand["method"]} {cand["url"]}
Pontuação: {cand["score"]} ({reasons}); {replay_note}.
Revise, complete os TODO e só então registre em adapters/registry.py. Termos de uso do site antes de tudo.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ._common import error_result, finalize, payload_kind
from ._http import {accept_name}, build_evidence, default_headers, http_get, utcnow
from .base import AdapterInfo, AdapterResult, QuoteDraft

URL = {cand["url"]!r}  # TODO: <redigido> vem de variável de ambiente, nunca do código
HOME_URL = {home!r}
RULE = {f"{source_id} {'json' if is_json else 'html'} v0 (esqueleto)"!r}  # TODO: versão após revisão


class {cls}:
    info = AdapterInfo(
        id={source_id!r},
        name={source_id.title()!r},  # TODO: nome comercial da casa
        kind="exchange_house",  # TODO: confirmar tipo
        method={method!r},
        integration={integration!r},
        url=HOME_URL,
        capabilities=[],  # TODO: só o que foi comprovado no parse
        limitations=["endpoint descoberto por fx-discover; pode mudar sem aviso"],  # TODO: limitações reais
        cities=[],  # TODO: cidades cobertas (CDE/ASU/PJC)
        currencies=["USD", "BRL", "PYG"],  # TODO: confirmar moedas
        poll_interval_s=300,
        allowed_domains=[{host!r}],
    )
    stale_after = timedelta(hours=36)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        # TODO: cabeçalhos necessários (ver relatório): {headers_hint}
        out = await http_get(URL, headers=default_headers({accept_name}, {{"Referer": HOME_URL}}))
        if not out.ok:
            return out.failure(self.info.id)
        return self.parse(out.text, captured_at=captured_at, url=out.url)

    def parse(self, raw: str | bytes, *, captured_at: Any, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        if payload_kind(raw) == "empty":
            return error_result("empty payload")
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        quotes: list[QuoteDraft] = []
        # TODO: mapear o payload para QuoteDraft. Chaves observadas (nível 1): {key_hint}
        # Exemplo: QuoteDraft(source_id=self.info.id, base="USD", quote="PYG", buy=..., sell=...,
        #   unit_note="PYG por 1 USD", modality="cash", kind="indicative", channel="physical")
        evidence = build_evidence(
            source_id=self.info.id, kind={"json" if is_json else "html"!r}, url=url, captured_at=captured_at,
            raw=text, rules=[RULE],
        )
        return finalize(
            quotes=quotes, evidence=evidence, issues=[], captured_at=captured_at, stale_after=self.stale_after,
            empty_message="TODO: parse ainda não mapeado",
        )


adapter = {cls}()
'''


def _test_source(source_id: str, *, fixture_name: str, url: str) -> str:
    cls = _class_name(source_id)
    return f'''"""Teste offline do parse de {source_id}. Falha de propósito até o mapeamento (TODO) ser escrito.

Fixture: {fixture_name} (sanitizada pelo fx-discover; revise antes de commitar).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fronteira_fx.adapters.{source_id} import adapter

FIXTURE = Path(__file__).parent / "fixtures" / {fixture_name!r}
URL = {url!r}


def test_parse_fixture_maps_quotes() -> None:
    result = adapter.parse(FIXTURE.read_bytes(), captured_at=datetime(2026, 11, 4, tzinfo=UTC), url=URL)
    # TODO: completar o mapeamento em {cls}.parse; até lá este teste falha de propósito.
    assert result.quotes, f"mapeamento pendente: {{result.message}}"
    assert all(q.source_id == {source_id!r} for q in result.quotes)
'''


def scaffold(
    source_id: str,
    cand: dict[str, Any],
    *,
    adapters_dir: Path,
    fixtures_dir: Path,
    tests_dir: Path,
    existing_ids: set[str],
) -> ScaffoldPaths:
    if not SOURCE_ID_RE.match(source_id):
        raise ScaffoldError("source_id deve ter só minúsculas e dígitos, começar por letra (2 a 31 caracteres)")
    if source_id in existing_ids:
        raise ScaffoldError(f"já existe um adaptador {source_id!r}; escolha outro id")
    body: bytes = cand["_body"]
    is_json = bool(cand.get("content_type") and "json" in cand["content_type"])
    fixture_name = f"{source_id}.{'json' if is_json else 'html'}"
    paths = ScaffoldPaths(
        adapter=adapters_dir / f"{source_id}.py",
        fixture=fixtures_dir / fixture_name,
        test=tests_dir / f"test_{source_id}.py",
    )
    for target in (paths.adapter, paths.fixture, paths.test):
        if target.exists():
            raise ScaffoldError(f"{target} já existe; não sobrescrevo")

    text = body.decode("utf-8", errors="replace")
    if is_json:
        try:
            clean = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except ValueError:
            clean = scrub_raw(text)
        clean = scrub_raw(clean)
    else:
        clean = scrub_raw(text)
    keys = _json_keys(body) if is_json else []

    adapters_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    paths.fixture.write_text(clean + "\n", encoding="utf-8")
    paths.adapter.write_text(_adapter_source(source_id, cand, is_json=is_json, keys=keys), encoding="utf-8")
    paths.test.write_text(_test_source(source_id, fixture_name=fixture_name, url=cand["url"]), encoding="utf-8")
    return paths
