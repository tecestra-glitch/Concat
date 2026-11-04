"""/v1/connections: contas conectadas sem senha de banco. Todas as rotas exigem a API_KEY; sem API_KEY configurada
elas respondem 503, porque o cofre guarda chave de corretora. Respostas nunca trazem segredo."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select

from ..config import Settings
from ..connections.exchanges import ExchangeCheckError, KeyCheck, validate_readonly_key
from ..connections.openfinance import OpenFinanceNotConfigured, OpenFinanceNotIntegrated, require_openfinance
from ..connections.schemas import (
    BalanceOut,
    ConnectionCreate,
    ConnectionOut,
    KeyCheckOut,
    KeyValidationIn,
    OpenFinanceConsentIn,
    StatementImportIn,
    StatementImportOut,
)
from ..connections.service import (
    balances_snapshot,
    check_linked_account,
    get_connection_or_404,
    import_transactions,
    to_out,
)
from ..connections.statement import CsvMapping, StatementError, parse_csv, parse_ofx
from ..connections.vault import (
    Credentials,
    VaultError,
    VaultUnavailable,
    key_hint,
    load_master_key,
    open_credentials,
    seal_credentials,
)
from ..models import Connection, new_id, utcnow
from .deps import DataModeDep, DbDep, SettingsDep, api_key_matches

log = logging.getLogger("fronteira_fx.connections")


def require_connections_access(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="conexões de conta exigem API_KEY configurada: o cofre guarda chave de corretora",
        )
    if not api_key_matches(settings, x_api_key, authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida ou ausente")


router = APIRouter(prefix="/connections", tags=["connections"], dependencies=[Depends(require_connections_access)])


def _vault_key(settings: Settings) -> bytes:
    try:
        return load_master_key(settings.connections_key)
    except VaultUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None


def _exchange_transport(request: Request):  # testes injetam um httpx.MockTransport aqui
    return getattr(request.app.state, "exchange_transport", None)


def _check_key(request: Request, institution: str, creds: Credentials) -> KeyCheck:
    try:
        return validate_readonly_key(
            institution, creds.api_key, creds.api_secret, transport=_exchange_transport(request)
        )
    except ExchangeCheckError as exc:
        return KeyCheck(ok=False, institution=institution.lower(), reasons=[str(exc)])


def _key_check_out(check: KeyCheck) -> KeyCheckOut:
    return KeyCheckOut(
        ok=check.ok,
        institution=check.institution,
        flags=check.flags,
        reasons=check.reasons,
        balances=[BalanceOut(asset=b.asset, free=b.free, locked=b.locked) for b in check.balances],
    )


@router.get("", operation_id="list_connections")
def list_connections(db: DbDep, data_mode: DataModeDep) -> list[ConnectionOut]:
    rows = db.scalars(select(Connection).where(Connection.data_mode == data_mode).order_by(Connection.created_at)).all()
    return [to_out(r) for r in rows]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="create_connection",
)
def create_connection(
    body: ConnectionCreate, request: Request, settings: SettingsDep, db: DbDep, data_mode: DataModeDep
) -> ConnectionOut:
    check_linked_account(db, body.account_id, data_mode)
    if body.kind == "consent":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="conexão por consentimento usa POST /v1/connections/openfinance/consent",
        )
    if body.kind != "readonly_key" and (body.api_key is not None or body.api_secret is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="chave só é aceita em readonly_key"
        )

    now = utcnow()
    row = Connection(
        id=new_id(),
        institution=body.institution.strip().lower(),
        label=body.label.strip(),
        kind=body.kind,
        status="active",
        account_id=body.account_id,
        data_mode=data_mode,
        created_at=now,
        updated_at=now,
    )
    if body.kind == "readonly_key":
        if body.api_key is None or body.api_secret is None:
            raise HTTPException(status_code=422, detail="readonly_key exige api_key e api_secret")
        key = _vault_key(settings)
        creds = Credentials(body.api_key.get_secret_value().strip(), body.api_secret.get_secret_value().strip())
        check = _check_key(request, row.institution, creds)
        if not check.ok:
            raise HTTPException(status_code=422, detail="chave recusada: " + "; ".join(check.reasons)[:900])
        row.key_hint = key_hint(creds.api_key)
        row.ciphertext = seal_credentials(key, row.id, row.institution, creds)
        row.balances = balances_snapshot(check)
        row.last_synced_at = now
    db.add(row)
    db.flush()
    log.info("conexão criada: id=%s kind=%s institution=%s", row.id, row.kind, row.institution)
    return to_out(row)


@router.post("/validate-key", operation_id="validate_connection_key")
def validate_connection_key(body: KeyValidationIn, request: Request, settings: SettingsDep) -> KeyCheckOut:
    """Confere a chave na corretora sem guardar nada. Chave com permissão de operar ou sacar vem com ok=false."""
    _vault_key(settings)  # função desligada sem FX_CONNECTIONS_KEY, mesmo sem gravar
    creds = Credentials(body.api_key.get_secret_value().strip(), body.api_secret.get_secret_value().strip())
    return _key_check_out(_check_key(request, body.institution.strip().lower(), creds))


@router.post(
    "/openfinance/consent",
    operation_id="start_openfinance_consent",
    responses={501: {"description": "provedor configurado, sem integração nesta versão"}},
)
def start_openfinance_consent(settings: SettingsDep, body: OpenFinanceConsentIn | None = None) -> ConnectionOut:
    """Inicia o consentimento Open Finance. Hoje só responde 503 (não configurado) ou 501 (sem integração).
    Nunca recebe credencial de banco: o titular conclui no fluxo do agregador."""
    try:
        require_openfinance(settings)
    except OpenFinanceNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    except OpenFinanceNotIntegrated as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from None
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="consentimento ainda não implementado")


@router.post("/{connection_id}/sync", operation_id="sync_connection")
def sync_connection(
    connection_id: str, request: Request, settings: SettingsDep, db: DbDep, data_mode: DataModeDep
) -> ConnectionOut:
    """Relê saldos com a chave guardada e confere de novo as permissões. Nenhuma ordem é enviada."""
    row = get_connection_or_404(db, connection_id, data_mode)
    if row.kind != "readonly_key" or not row.ciphertext:
        raise HTTPException(status_code=422, detail="só conexões readonly_key sincronizam saldos")
    key = _vault_key(settings)
    try:
        creds = open_credentials(key, row.id, row.institution, row.ciphertext)
    except (VaultError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="cofre: não foi possível decifrar a chave guardada; confira FX_CONNECTIONS_KEY",
        ) from None
    check = _check_key(request, row.institution, creds)
    row.updated_at = utcnow()
    if check.ok:
        row.status = "active"
        row.last_error = None
        row.balances = balances_snapshot(check)
        row.last_synced_at = row.updated_at
    else:
        row.status = "error"
        row.last_error = "; ".join(check.reasons)[:200]
    db.flush()
    return to_out(row)


@router.post(
    "/{connection_id}/statement",
    operation_id="import_connection_statement",
)
def import_connection_statement(
    connection_id: str, body: StatementImportIn, db: DbDep, data_mode: DataModeDep
) -> StatementImportOut:
    """Importa extrato CSV (com mapeamento de colunas) ou OFX. Arquivo com erro é recusado por inteiro."""
    row = get_connection_or_404(db, connection_id, data_mode)
    if row.kind != "statement":
        raise HTTPException(status_code=422, detail="importação de extrato só em conexões do tipo statement")
    try:
        if body.format == "csv":
            if body.mapping is None:
                raise HTTPException(status_code=422, detail="CSV exige mapping (colunas de data, descrição e valor)")
            m = body.mapping
            mapping = CsvMapping(
                date=m.date,
                description=m.description,
                amount=m.amount,
                currency=m.currency,
                date_format=m.date_format,
                delimiter=m.delimiter,
            )
            transactions = parse_csv(body.content, mapping, body.default_currency)
        else:
            transactions = parse_ofx(body.content, body.default_currency)
    except StatementError as exc:
        raise HTTPException(status_code=422, detail=exc.errors[:20]) from None

    result = import_transactions(db, row, transactions)
    log.info("extrato importado: connection=%s novos=%d repetidos=%d", row.id, result.imported, result.duplicates)
    return StatementImportOut(
        connection_id=row.id,
        format=body.format,
        imported=result.imported,
        duplicates=result.duplicates,
        account_id=result.account_id,
        balance_delta=result.balance_delta,
        account_balance_free=result.account_balance_free,
    )


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_connection",
)
def delete_connection(connection_id: str, db: DbDep, data_mode: DataModeDep) -> Response:
    """Apaga a conexão, o ciphertext da chave e os lançamentos importados. A conta vinculada não muda."""
    row = get_connection_or_404(db, connection_id, data_mode)
    db.delete(row)
    db.flush()
    log.info("conexão apagada: id=%s", connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
