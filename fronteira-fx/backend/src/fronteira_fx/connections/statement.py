"""Importação de extrato: CSV com mapeamento de colunas e OFX. Só leitura de texto: nada do arquivo é executado,
nenhuma entidade XML é resolvida, e todo dinheiro sai como Decimal. Erro de qualquer linha recusa o arquivo inteiro.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_STATEMENT_CHARS = 512 * 1024
MAX_STATEMENT_ROWS = 5000
MAX_DESCRIPTION = 200
MAX_ABS_AMOUNT = Decimal(10) ** 12
SUPPORTED_CURRENCIES = frozenset({"BRL", "USD", "PYG"})
ALLOWED_DATE_FORMATS = frozenset({"%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"})
_AMOUNT_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_TRN_OPEN_RE = re.compile(r"<STMTTRN>", re.IGNORECASE)
_TRN_TAG_RE = re.compile(r"<STMTTRN>|</STMTTRN>", re.IGNORECASE)


class StatementError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


@dataclass(frozen=True)
class Transaction:
    occurred_on: date
    description: str
    amount: Decimal
    currency: str
    fitid: str | None = None


@dataclass(frozen=True)
class CsvMapping:
    date: str
    description: str
    amount: str
    currency: str | None = None
    date_format: str = "%Y-%m-%d"
    delimiter: str = ","


def parse_amount(raw: str) -> Decimal:
    """Aceita 1234.56, 1.234,56, 1,234.56, -12,5, (12,50) e 12.5. Sempre Decimal finito e dentro do limite."""
    s = raw.strip().replace(" ", "").replace(" ", "")
    if not s:
        raise ValueError("valor vazio")
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    last_comma, last_dot = s.rfind(","), s.rfind(".")
    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot:  # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:  # 1,234.56
            s = s.replace(",", "")
    elif last_comma != -1:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif s.count(".") > 1:  # 1.234.567
        s = s.replace(".", "")
    if not _AMOUNT_RE.match(s):
        raise ValueError("valor inválido")
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError("valor inválido") from None
    if not value.is_finite() or abs(value) >= MAX_ABS_AMOUNT:
        raise ValueError("valor fora do limite")
    return -value if negative else value


def _currency(raw: str | None, default: str | None) -> str:
    code = (raw or default or "").strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ValueError(f"moeda não suportada: {code or '(vazia)'}")
    return code


def _check_size(content: str) -> None:
    if len(content) > MAX_STATEMENT_CHARS:
        raise StatementError([f"arquivo acima de {MAX_STATEMENT_CHARS} caracteres"])


def parse_csv(content: str, mapping: CsvMapping, default_currency: str | None = None) -> list[Transaction]:
    _check_size(content)
    if mapping.date_format not in ALLOWED_DATE_FORMATS:
        raise StatementError(["date_format não permitido"])
    if mapping.delimiter not in (",", ";", "\t"):
        raise StatementError(["delimitador não permitido"])
    reader = csv.DictReader(io.StringIO(content), delimiter=mapping.delimiter, restkey="_extra")
    fields = reader.fieldnames or []
    needed = [mapping.date, mapping.description, mapping.amount] + ([mapping.currency] if mapping.currency else [])
    missing = [c for c in needed if c not in fields]
    if missing:
        raise StatementError([f"colunas ausentes no CSV: {', '.join(missing)}"])
    if not mapping.currency and not default_currency:
        raise StatementError(["informe a coluna de moeda ou default_currency"])

    rows: list[Transaction] = []
    errors: list[str] = []
    for n, row in enumerate(reader, start=2):  # linha 1 é o cabeçalho
        if len(rows) + len(errors) >= MAX_STATEMENT_ROWS:
            raise StatementError([f"mais de {MAX_STATEMENT_ROWS} linhas"])
        if row.get("_extra"):
            errors.append(f"linha {n}: mais colunas que o cabeçalho")
            continue
        try:
            occurred = datetime.strptime((row[mapping.date] or "").strip(), mapping.date_format).date()
        except ValueError:
            errors.append(f"linha {n}: data inválida")
            continue
        description = (row[mapping.description] or "").strip()
        if not description:
            errors.append(f"linha {n}: descrição vazia")
            continue
        try:
            amount = parse_amount(row[mapping.amount] or "")
        except ValueError as exc:
            errors.append(f"linha {n}: {exc}")
            continue
        try:
            currency = _currency(row[mapping.currency] if mapping.currency else None, default_currency)
        except ValueError as exc:
            errors.append(f"linha {n}: {exc}")
            continue
        rows.append(Transaction(occurred, description[:MAX_DESCRIPTION], amount, currency))
    if errors:
        raise StatementError(errors)
    return rows


def _tag(block: str, name: str) -> str | None:
    match = re.search(rf"<{name}>([^<\r\n]*)", block, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _trn_blocks(content: str) -> list[str]:
    """Blocos <STMTTRN>…</STMTTRN> numa única passada linear. Abertura sem fechamento é ignorada (não há busca
    repetida até o fim do texto, então um arquivo com muitas aberturas não custa tempo quadrático)."""
    blocks: list[str] = []
    start: int | None = None
    for match in _TRN_TAG_RE.finditer(content):
        is_close = match.group(0)[1] == "/"
        if start is None:
            if not is_close:
                start = match.end()
        elif is_close:
            blocks.append(content[start : match.start()])
            start = None
    return blocks


def parse_ofx(content: str, default_currency: str | None = None) -> list[Transaction]:
    """OFX 1.x (SGML) e 2.x (XML) por texto: pega o CURDEF e cada bloco STMTTRN. Não resolve entidades nem URLs."""
    _check_size(content)
    if "<OFX>" not in content.upper():
        raise StatementError(["arquivo não é OFX (falta <OFX>)"])
    openings = len(_TRN_OPEN_RE.findall(content))
    if openings > MAX_STATEMENT_ROWS:
        raise StatementError([f"mais de {MAX_STATEMENT_ROWS} transações"])
    currency_tag = _tag(content, "CURDEF")
    try:
        currency = _currency(currency_tag, default_currency)
    except ValueError as exc:
        raise StatementError([str(exc)]) from None

    rows: list[Transaction] = []
    errors: list[str] = []
    for n, block in enumerate(_trn_blocks(content), start=1):
        if n > MAX_STATEMENT_ROWS:
            raise StatementError([f"mais de {MAX_STATEMENT_ROWS} transações"])
        posted = _tag(block, "DTPOSTED") or ""
        try:
            occurred = datetime.strptime(posted[:8], "%Y%m%d").date()
        except ValueError:
            errors.append(f"transação {n}: DTPOSTED inválido")
            continue
        raw_amount = _tag(block, "TRNAMT")
        if raw_amount is None:
            errors.append(f"transação {n}: TRNAMT ausente")
            continue
        try:
            amount = parse_amount(raw_amount)
        except ValueError as exc:
            errors.append(f"transação {n}: {exc}")
            continue
        fitid = _tag(block, "FITID") or None
        description = (_tag(block, "NAME") or _tag(block, "MEMO") or fitid or "").strip()
        if not description:
            errors.append(f"transação {n}: descrição ausente")
            continue
        rows.append(Transaction(occurred, description[:MAX_DESCRIPTION], amount, currency, fitid))
    if errors:
        raise StatementError(errors)
    return rows


def fingerprint(connection_id: str, tx: Transaction, occurrence: int) -> str:
    """Identidade estável de um lançamento: FITID quando existe; senão data+valor+moeda+descrição e a ordem entre
    lançamentos idênticos do mesmo arquivo. Reimportar o mesmo extrato não duplica nada."""
    if tx.fitid:
        base = f"fitid|{tx.fitid}"
    else:
        base = f"{tx.occurred_on.isoformat()}|{tx.amount}|{tx.currency}|{tx.description}"
    digest = hashlib.sha256(f"{connection_id}|{base}|{occurrence}".encode()).hexdigest()
    return digest
