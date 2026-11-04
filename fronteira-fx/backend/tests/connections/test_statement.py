"""Importação de extrato: CSV com mapeamento, OFX, valores em Decimal, limites e deduplicação."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fronteira_fx.connections.statement import (
    MAX_STATEMENT_ROWS,
    CsvMapping,
    StatementError,
    fingerprint,
    parse_amount,
    parse_csv,
    parse_ofx,
)

MAP = CsvMapping(date="Data", description="Descrição", amount="Valor", currency="Moeda", date_format="%d/%m/%Y")


def test_csv_valid_with_pt_br_amounts_and_currency_column():
    content = (
        "Data;Descrição;Valor;Moeda\n"
        "03/11/2026;PIX recebido;1.234,56;BRL\n"
        "04/11/2026;Compra loja;-50,00;brl\n"
    )
    rows = parse_csv(content, CsvMapping(**{**MAP.__dict__, "delimiter": ";"}))
    assert [r.occurred_on for r in rows] == [date(2026, 11, 3), date(2026, 11, 4)]
    assert rows[0].amount == Decimal("1234.56")
    assert rows[1].amount == Decimal("-50.00")
    assert rows[1].currency == "BRL"
    assert all(isinstance(r.amount, Decimal) for r in rows)


def test_csv_default_currency_when_no_currency_column():
    content = "Data,Descrição,Valor\n2026-11-03,Transferência,\"1,000.10\"\n"
    mapping = CsvMapping(date="Data", description="Descrição", amount="Valor")
    rows = parse_csv(content, mapping, default_currency="USD")
    assert rows[0].amount == Decimal("1000.10") and rows[0].currency == "USD"


def test_csv_without_currency_source_refused():
    with pytest.raises(StatementError, match="moeda"):
        parse_csv("Data,Descrição,Valor\n2026-11-03,x,1\n", CsvMapping(date="Data", description="Descrição", amount="Valor"))


def test_csv_missing_mapped_column_refused():
    with pytest.raises(StatementError, match="colunas ausentes"):
        parse_csv("Data,Descrição\n03/11/2026,x\n", MAP)


def test_csv_one_bad_row_refuses_whole_file_with_line_numbers():
    content = (
        "Data,Descrição,Valor,Moeda\n"
        "03/11/2026,ok,10,BRL\n"
        "31/02/2026,data ruim,10,BRL\n"
        "04/11/2026,valor ruim,abc,BRL\n"
        "05/11/2026,moeda ruim,10,EUR\n"
        "06/11/2026,,10,BRL\n"
    )
    with pytest.raises(StatementError) as info:
        parse_csv(content, MAP)
    errors = info.value.errors
    assert any(e.startswith("linha 3: data") for e in errors)
    assert any(e.startswith("linha 4: valor") for e in errors)
    assert any(e.startswith("linha 5: moeda") for e in errors)
    assert any(e.startswith("linha 6: descrição vazia") for e in errors)


def test_csv_extra_columns_refused():
    with pytest.raises(StatementError, match="mais colunas"):
        parse_csv("Data,Descrição,Valor,Moeda\n03/11/2026,x,1,BRL,EXTRA\n", MAP)


def test_csv_row_limit():
    header = "Data,Descrição,Valor,Moeda\n"
    body = "".join("03/11/2026,x,1,BRL\n" for _ in range(MAX_STATEMENT_ROWS + 1))
    with pytest.raises(StatementError, match="mais de"):
        parse_csv(header + body, MAP)


def test_csv_description_truncated_not_refused():
    content = "Data,Descrição,Valor,Moeda\n03/11/2026," + "x" * 300 + ",1,BRL\n"
    rows = parse_csv(content, MAP)
    assert len(rows[0].description) == 200


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("-12,5", "-12.5"),
        ("(12,50)", "-12.50"),
        ("1.234.567", "1234567"),
        ("+3", "3"),
    ],
)
def test_parse_amount_formats(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "abc", "1e9", "NaN", "Infinity", "1,2,3.4,5", "9" * 14])
def test_parse_amount_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


OFX = """OFXHEADER:100
<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<CURDEF>USD
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20261103120000[-3:PYT]
<TRNAMT>250.00
<FITID>2026110301
<NAME>Transf recebida
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20261104
<TRNAMT>-19.90
<FITID>2026110402
<MEMO>Assinatura
</STMTTRN>
</BANKTRANLIST>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""


def test_ofx_valid_reads_currency_and_transactions():
    rows = parse_ofx(OFX)
    assert [r.occurred_on for r in rows] == [date(2026, 11, 3), date(2026, 11, 4)]
    assert rows[0].amount == Decimal("250.00") and rows[0].currency == "USD"
    assert rows[1].amount == Decimal("-19.90") and rows[1].description == "Assinatura"
    assert rows[0].fitid == "2026110301"


def test_ofx_missing_header_refused():
    with pytest.raises(StatementError, match="não é OFX"):
        parse_ofx("<STMTTRN><DTPOSTED>20261103<TRNAMT>1</STMTTRN>")


def test_ofx_missing_currency_refused():
    with pytest.raises(StatementError, match="moeda"):
        parse_ofx("<OFX><STMTTRN><DTPOSTED>20261103<TRNAMT>1<NAME>x</STMTTRN></OFX>")


def test_ofx_invalid_date_and_amount_refused_with_positions():
    bad = (
        "<OFX><CURDEF>BRL<STMTTRN><DTPOSTED>2026XX03<TRNAMT>1<NAME>a</STMTTRN>"
        "<STMTTRN><DTPOSTED>20261103<NAME>b</STMTTRN>"
        "<STMTTRN><DTPOSTED>20261103<TRNAMT>zz<NAME>c</STMTTRN></OFX>"
    )
    with pytest.raises(StatementError) as info:
        parse_ofx(bad)
    assert info.value.errors == [
        "transação 1: DTPOSTED inválido",
        "transação 2: TRNAMT ausente",
        "transação 3: valor inválido",
    ]


def test_ofx_does_not_resolve_entities_or_execute_anything():
    content = "<OFX><CURDEF>BRL<STMTTRN><DTPOSTED>20261103<TRNAMT>1<NAME>&xxe;<!ENTITY a 'b'></STMTTRN></OFX>"
    rows = parse_ofx(content)
    assert rows[0].description == "&xxe;"


def test_fingerprint_stable_and_connection_scoped():
    tx = parse_ofx(OFX)[0]
    assert fingerprint("c1", tx, 0) == fingerprint("c1", tx, 0)
    assert fingerprint("c1", tx, 0) != fingerprint("c2", tx, 0)
    assert len(fingerprint("c1", tx, 0)) == 64
