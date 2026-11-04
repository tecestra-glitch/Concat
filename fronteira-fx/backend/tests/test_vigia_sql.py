"""Paridade entre deploy/supabase/vigia.sql e o backend (sem banco: lê o texto do arquivo).

O comportamento do SQL é testado de verdade contra um Postgres com pg_net (ver docs/deploy.md); aqui ficam as
garantias que dá para checar sem rede: user-agent igual ao do backend, um alvo por adaptador (menos westernunion),
nenhum segredo no arquivo e o agendamento comentado.
"""

import re
from pathlib import Path

from fronteira_fx.adapters import registry
from fronteira_fx.adapters._http import USER_AGENT

VIGIA = Path(__file__).resolve().parents[2] / "deploy" / "supabase" / "vigia.sql"
FINGERPRINT_CHECK = Path(__file__).resolve().parents[2] / "deploy" / "supabase" / "tests" / "fingerprint_check.sql"
NO_BROWSER_NEEDED = {"westernunion"}  # precisa de navegador: fica fora do vigia


def _sql() -> str:
    return VIGIA.read_text(encoding="utf-8")


def _seeded_ids(sql: str) -> set[str]:
    section = sql.split("-- 6. Alvos (seed)", 1)[1].split("on conflict (source_id) do update", 1)[0]
    return set(re.findall(r"^\s+\('([a-z0-9_]+)', '", section, flags=re.MULTILINE))


def test_user_agent_matches_the_backend():
    assert f"v_ua constant text := '{USER_AGENT}';" in _sql()


def test_one_target_per_registry_adapter_except_browser_ones():
    expected = set(registry.ADAPTERS) - NO_BROWSER_NEEDED
    assert _seeded_ids(_sql()) == expected


def test_no_secret_in_the_file():
    sql = _sql()
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    # fora dos comentários, o Bearer só existe como concatenação com a variável lida do Vault
    assert "Bearer" in code
    assert code.count("Bearer") == code.count("'Bearer ' || v_secret")
    assert "fx_cron_secret" in sql  # o nome do segredo, não o valor
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", sql)  # forma de JWT
    assert not re.search(r"(?i)(password|senha)\s*[:=]\s*'[^']+'", sql)


def test_cron_schedule_is_commented_out():
    active = [line for line in _sql().splitlines() if "cron.schedule(" in line and not line.lstrip().startswith("--")]
    assert active == []


def test_fingerprint_test_file_exists():
    assert FINGERPRINT_CHECK.is_file()
