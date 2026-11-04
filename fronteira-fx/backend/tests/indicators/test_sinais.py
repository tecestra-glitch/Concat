"""Sinais: lookahead, repintura, só velas fechadas, validação de velas e busca de padrões proibidos."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fronteira_fx.indicators import sinais
from fronteira_fx.market.vol import Candle

FIXTURE = Path(__file__).parent / "fixtures" / "serie_sintetica_talib.json"
SRC_INDICATORS = Path(__file__).resolve().parents[2] / "src" / "fronteira_fx" / "indicators"
BASE = datetime(2026, 11, 1, tzinfo=UTC)


def D(x: float | str) -> Decimal:
    return Decimal(str(x))


def _candles() -> list[Candle]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["candles"]
    out: list[Candle] = []
    for i, r in enumerate(rows):
        ot = BASE + timedelta(minutes=5 * i)
        out.append(
            Candle(
                open_time=ot,
                close_time=ot + timedelta(minutes=5),
                open=D(r["o"]),
                high=D(r["h"]),
                low=D(r["l"]),
                close=D(r["c"]),
            )
        )
    return out


@pytest.fixture(scope="module")
def candles() -> list[Candle]:
    return _candles()


def test_lookahead_cortar_ultima_vela_nao_muda_sinais_anteriores(candles: list[Candle]) -> None:
    completo = sinais.calcula_sinais(candles)
    for k in range(40, len(candles)):
        parcial = sinais.calcula_sinais(candles[:k])
        assert parcial[k - 2] == completo[k - 2], f"corte em {k} mudou o sinal da vela {k - 2}"
        assert parcial == completo[:k], f"corte em {k} mudou sinais anteriores"


def test_sinais_existem_depois_do_aquecimento(candles: list[Candle]) -> None:
    s = sinais.calcula_sinais(candles)
    assert all(x is None for x in s[:52])  # Senkou B completa só no índice 51
    assert any(x is not None and x.macd_cruzamento != 0 for x in s)


def test_repintura_gravado_em_tempo_real_nao_muda(candles: list[Candle]) -> None:
    agora = candles[-1].close_time
    gravados = sinais.grava_em_tempo_real(candles, agora)
    assert gravados, "deveria haver sinais gravados"
    assert sinais.verifica_repintura(gravados, candles) == []


def test_repintura_detecta_mudanca_quando_dado_passado_muda(candles: list[Candle]) -> None:
    gravados = sinais.grava_em_tempo_real(candles, candles[-1].close_time)
    alterado = list(candles)
    c = alterado[60]
    novo_close = c.close * Decimal("1.05")
    alterado[60] = Candle(
        open_time=c.open_time,
        close_time=c.close_time,
        open=c.open,
        high=max(c.high, novo_close),
        low=c.low,
        close=novo_close,
    )
    divs = sinais.verifica_repintura(gravados, alterado)
    assert divs, "alterar vela passada deveria aparecer como repintura"
    assert all(d.indice >= 60 for d in divs)


def test_vela_aberta_nao_entra_no_sinal(candles: list[Candle]) -> None:
    fechadas = candles[:80]
    aberta = Candle(
        open_time=candles[80].open_time,
        close_time=candles[80].close_time,
        open=candles[80].open,
        high=candles[80].high,
        low=candles[80].low,
        close=candles[80].close,
    )
    agora = candles[79].close_time + timedelta(seconds=30)  # vela 80 ainda não fechou
    filtradas = sinais.apenas_fechadas([*fechadas, aberta], agora)
    assert len(filtradas) == 80
    assert sinais.grava_em_tempo_real([*fechadas, aberta], agora) == sinais.grava_em_tempo_real(fechadas, agora)


def test_valida_velas_rejeita_inconsistencias(candles: list[Candle]) -> None:
    c = candles[5]
    ruim = Candle(
        open_time=c.open_time, close_time=c.close_time, open=c.open, high=c.low, low=c.high, close=c.close
    )
    with pytest.raises(sinais.VelaInvalidaError):
        sinais.valida_velas([*candles[:5], ruim])
    with pytest.raises(sinais.VelaInvalidaError):
        sinais.valida_velas([candles[1], candles[0]])


def test_sem_shift_negativo_nem_iloc_ultimo_no_codigo_de_indicadores() -> None:
    padroes = [r"shift\(\s*-", r"\.iloc\[\s*-", r"\[\s*-1\s*\]"]
    achados: list[str] = []
    for arq in SRC_INDICATORS.glob("*.py"):
        for num, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), start=1):
            for p in padroes:
                if re.search(p, linha):
                    achados.append(f"{arq.name}:{num}: {linha.strip()}")
    assert achados == []
