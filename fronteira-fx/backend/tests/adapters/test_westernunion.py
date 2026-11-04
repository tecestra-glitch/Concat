from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from fronteira_fx.adapters import westernunion as wu
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

FIXTURE = "westernunion_5000_brl_pyg.json"
URL = wu.START_URL


def test_fixture_is_marked_historical() -> None:
    data = json.loads(load(FIXTURE))
    assert data["historical"] is True and "historical" in data["note"].lower()


def test_parse_two_receive_methods(captured_at: datetime) -> None:
    res = wu.adapter.parse(load(FIXTURE), captured_at=captured_at, url=URL)
    # historical data is never served as current
    assert res.status == AdapterStatus.STALE and "historical" in (res.message or "")
    assert len(res.quotes) == 2
    bank = next(q for q in res.quotes if q.context and q.context["receive"] == "bank_account")
    cash = next(q for q in res.quotes if q.context and q.context["receive"] == "cash_pickup")

    # effective rate = receive / amount
    assert bank.amount_base == Decimal("5000") and bank.base == "BRL" and bank.quote == "PYG"
    assert bank.buy == Decimal("1080.3742")  # 5,401,871 / 5,000
    assert bank.sell is None and "PYG por 1 BRL" in bank.unit_note
    assert cash.buy == Decimal("1065.6418")  # 5,328,209 / 5,000
    assert bank.buy != cash.buy

    # the two receive methods are different quotes with different, complete contexts
    assert bank.context != cash.context
    assert bank.context["delivery"] == "0–4 dias úteis" and cash.context["delivery"] == "minutos"
    for q in (bank, cash):
        assert q.context is not None
        assert q.context["origin"] == "BR" and q.context["destination"] == "PY"
        assert q.context["send_currency"] == "BRL" and q.context["receive_currency"] == "PYG"
        assert q.context["amount_brl"] == "5000" and q.context["payment"] == "pix"
        assert q.context["bank"] is None and q.context["channel"] == "web"
        assert q.context["promo"] == "100% desconto na tarifa"
        assert q.fees and q.fees[0].amount == Decimal("0") and q.fees[0].currency == "BRL"
        assert q.kind == "indicative" and q.channel == "digital" and q.city is None
    assert bank.modality == "transfer" and cash.modality == "cash"
    assert res.evidence is not None and res.evidence.kind == "json" and "bank_account" in res.evidence.excerpt


def test_single_live_scenario_is_ok() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    sc = json.loads(load(FIXTURE))["scenarios"][0]
    sc["captured_at"] = now.isoformat()
    res = wu.adapter.parse(json.dumps(sc), captured_at=now, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert res.quotes[0].buy == Decimal("1080.3742") and res.quotes[0].declared_updated_at == now


def test_screenshot_evidence_kind() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    sc = json.loads(load(FIXTURE))["scenarios"][1]
    sc["captured_at"] = now.isoformat()
    res = wu.adapter.parse(json.dumps(sc), captured_at=now, url=URL, screenshot_path="/tmp/x.png",
                           screenshot_bytes=b"png")
    assert res.evidence is not None and res.evidence.kind == "screenshot" and res.evidence.raw_path == "/tmp/x.png"


def test_bad_payloads(captured_at: datetime) -> None:
    assert wu.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert wu.adapter.parse("{}", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    html = wu.adapter.parse("<html>spa</html>", captured_at=captured_at, url=URL)
    assert html.status == AdapterStatus.DEGRADED and html.quotes == []
    missing = json.dumps({"scenarios": [{"amount_brl": "5000", "receive": "bank_account", "payment": "pix"}]})
    res = wu.adapter.parse(missing, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []  # no receive value -> no invented rate
    zero = json.dumps({"amount_brl": "5000", "receive_amount_pyg": "0", "receive": "bank_account", "payment": "pix"})
    assert wu.adapter.parse(zero, captured_at=captured_at, url=URL).status == AdapterStatus.ERROR


def test_unknown_method_is_degraded() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    sc = json.loads(load(FIXTURE))["scenarios"][0]
    sc["captured_at"] = now.isoformat()
    sc["receive"] = "pigeon"
    res = wu.adapter.parse(json.dumps(sc), captured_at=now, url=URL)
    assert res.status == AdapterStatus.DEGRADED and "pigeon" in (res.message or "")


@pytest.mark.asyncio
async def test_fetch_without_playwright_is_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001, ANN202
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    res = await wu.adapter.fetch(amount_brl="5000", payment="pix", receive="bank_account")
    assert res.status == AdapterStatus.DEGRADED and "playwright" in (res.message or "").lower()


@pytest.mark.asyncio
async def test_fetch_rejects_bad_params() -> None:
    assert (await wu.adapter.fetch(amount_brl="abc")).status == AdapterStatus.ERROR
    assert (await wu.adapter.fetch(receive="pigeon")).status == AdapterStatus.ERROR  # type: ignore[arg-type]


def test_evidence_dir_follows_evidence_dir_then_the_legacy_alias(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Q-08/LOW-14: EVIDENCE_DIR (B9, the canonical name) wins; FX_EVIDENCE_DIR is only the legacy alias."""
    monkeypatch.setenv("FX_EVIDENCE_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "canonical"))
    assert wu.evidence_dir() == tmp_path / "canonical"
    monkeypatch.delenv("EVIDENCE_DIR")
    assert wu.evidence_dir() == tmp_path / "legacy"


def test_evidence_dir_is_gitignored(monkeypatch: pytest.MonkeyPatch) -> None:
    # backend/.gitignore ignores the whole var/ tree, so screenshots never reach Git. (A nested var/.gitignore is
    # itself untracked and only exists where the adapter has already run, so it cannot be what this test relies on.)
    backend_root = Path(__file__).resolve().parents[2]
    rules = [line.strip() for line in (backend_root / ".gitignore").read_text().splitlines()]
    assert any(rule.strip("/") == "var" for rule in rules), rules
    monkeypatch.delenv("FX_EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("EVIDENCE_DIR", raising=False)
    assert wu.evidence_dir() == backend_root / "var" / "evidence"


# visible page text captured live on 2026-11-02 after choosing Conta Bancaria + PIX for 5000 BRL
LIVE_BODY = (
    "Valor a enviar\nBRL\nValor a receber\nPYG\nUSD\nEnviar até 25,000.00 BRL\n\n1.00 BRL = 1,080.3741 Paraguay Guarani "
    "(PYG) 2\n\nComo o seu destinatário quer receber o dinheiro?\nReceber em dinheiro\nem uma loja\nConta Bancaria10\n"
    "Como você gostaria de pagar?\nPIX ou transferência bancária4\n0-4 Dias úteis1, 8, 12\nTarifa2 0.00\xa0 BRL\n\n"
    "Tenho um código promocional\nContinuar\nRESUMO\nTAXA DE CÂMBIO2\n1.00 BRL = 1,080.3741 PYG\nValor da transferência\n"
    "5,000.00 BRL\n100% de desconto 45.00 BRL\nTaxa de transferência2\n+ 0.00 BRL\nTotal da transferência\n5,000.00 BRL\n"
    "Total  O destinatário recebe\n5,401,871.00PYG\nTempo de atendimento:1, 8, 12\n0-4 Dias úteis\n0 to 4 Dia"
)


def test_extract_summary_from_live_text() -> None:
    summary = wu.extract_summary(LIVE_BODY)
    assert summary["fee_brl"] == "0.00"
    assert summary["fee_before_discount_brl"] == "45.00"
    assert summary["exchange_rate"] == "1,080.3741"
    assert summary["delivery"] == "0-4 Dias úteis"
    assert summary["promo"] == "100% de desconto 45.00 BRL"
    assert summary["summary_text"].startswith("RESUMO")
    assert wu.extract_summary("nothing here")["fee_brl"] is None


# ---- forma de recebimento suspensa pela WU (04/11/2026: "Conta Bancaria" desativada para PYG no Paraguai)
_AVISO = "Para enviar dinheiro para uma conta bancária, tente alterar a moeda de receção."


def test_choose_receive_ativa_segue_a_pedida() -> None:
    assert wu.choose_receive("bank_account", {"bank_account": None, "cash_pickup": None}) == ("bank_account", None)


def test_choose_receive_conta_suspensa_troca_por_retirada_e_explica() -> None:
    chosen, note = wu.choose_receive("bank_account", {"bank_account": _AVISO, "cash_pickup": None})
    assert chosen == "cash_pickup"
    assert note is not None and "bank_account suspenso pela WU" in note and "coletado cash_pickup" in note
    assert _AVISO in note


def test_choose_receive_sem_alternativa_ativa_nao_coleta() -> None:
    chosen, note = wu.choose_receive("bank_account", {"bank_account": _AVISO, "cash_pickup": "também fora"})
    assert chosen is None and note is not None and "suspenso" in note
    chosen, note = wu.choose_receive("cash_pickup", {"bank_account": None, "cash_pickup": "fora do ar"})
    assert chosen is None  # retirada não tem alternativa: nunca troca por conta sem pedir


def test_choose_receive_tile_ausente_mantem_o_caminho_antigo() -> None:
    # layout mudou e o tile não apareceu: segue a pedida (o clique ainda tenta pelo texto) e falha com a mensagem antiga
    assert wu.choose_receive("bank_account", {}) == ("bank_account", None)
    assert wu.choose_receive("bank_account", {"cash_pickup": None}) == ("bank_account", None)


def test_cotacao_de_retirada_tem_contexto_e_modalidade_proprios() -> None:
    doc = {"scenarios": [{"amount_brl": "5000", "receive_amount_pyg": "5461841", "receive": "cash_pickup",
                          "payment": "pix", "captured_at": "2026-11-04T18:19:00Z"}]}
    r = wu.adapter.parse(json.dumps(doc), captured_at=datetime(2026, 11, 4, 18, 19, tzinfo=UTC), url="https://x")
    assert len(r.quotes) == 1
    q = r.quotes[0]
    assert q.modality == "cash" and q.context["receive"] == "cash_pickup"
    assert q.buy == Decimal("1092.3682")


# Texto da página com retirada em loja + Pix, transcrito do print de 04/11/2026 18:22 UTC (notas de rodapé "2,5").
CASH_BODY = (
    "Como o seu destinatário quer receber o dinheiro?\nReceber em dinheiro\nem uma loja6\nConta Bancaria\n"
    "Como você gostaria de pagar?\nPagamento em dinheiro em umaloja habilitada\nEm minutos1\nTarifa2,5 75.00 BRL\n"
    "PIX ou transferência bancária4\nEm minutos1, 13\nTarifa2,5 0.00 BRL\nTenho um código promocional\nContinuar\n"
    "RESUMO\nTAXA DE CÂMBIO2\n1.00 BRL = 1,092.3681 PYG\nValor da transferência\n5,000.00 BRL\n100% de desconto\n"
    "55.00 BRL\nTaxa de transferência2,5\n+ 0.00 BRL\nTotal da transferência\n5,000.00 BRL\n"
    "Total O destinatário recebe\n5,461,841.00 PYG\nTempo de atendimento:1, 13\nEm minutos"
)


def test_extract_summary_retirada_le_a_tarifa_do_resumo_com_notas_2_5() -> None:
    summary = wu.extract_summary(CASH_BODY)
    assert summary["fee_brl"] == "0.00"  # a do Pix escolhido (resumo), nunca os R$ 75 do pagamento em dinheiro
    assert summary["fee_before_discount_brl"] == "55.00"
    assert summary["exchange_rate"] == "1,092.3681"
    assert summary["delivery"].lower() == "em minutos"


def test_extract_summary_sem_resumo_usa_a_primeira_tarifa_e_nunca_confunde_nota_com_valor() -> None:
    assert wu.extract_summary("Tarifa2,5 75.00 BRL")["fee_brl"] == "75.00"
    assert wu.extract_summary("Tarifa 2,500.00 BRL")["fee_brl"] == "2500.00"
    # nota colada no valor, sem espaço: valor desconhecido em vez de um número errado
    assert wu.extract_summary("Tarifa2,500.00 BRL")["fee_brl"] is None
