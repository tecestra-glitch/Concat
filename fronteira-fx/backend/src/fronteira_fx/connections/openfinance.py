"""Estrutura do consentimento Open Finance. Desligada por padrão.

O consentimento passa por um agregador autorizado pelo Banco Central (ex.: pluggy), que redireciona o titular para o
próprio fluxo dele. Este app nunca pede, recebe, guarda nem repassa usuário e senha de banco. Nenhum provedor vem
implementado nesta versão: `INTEGRATED_PROVIDERS` começa vazio, então qualquer provedor configurado responde 501.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings

INTEGRATED_PROVIDERS: frozenset[str] = frozenset()


class OpenFinanceNotConfigured(RuntimeError):
    """Sem provedor (ou sem credenciais dele) no ambiente. Vira 503."""


class OpenFinanceNotIntegrated(RuntimeError):
    """Provedor configurado, mas sem integração nesta versão. Vira 501."""


@dataclass(frozen=True)
class OpenFinanceProvider:
    name: str


NOT_CONFIGURED_MESSAGE = (
    "Open Finance não configurado. Para ligar, contrate um agregador autorizado pelo Banco Central "
    "(ex.: pluggy), defina FX_OPENFINANCE_PROVIDER, FX_OPENFINANCE_CLIENT_ID e FX_OPENFINANCE_CLIENT_SECRET "
    "no backend e aguarde a integração do provedor. O app não coleta senha de banco em nenhum caso."
)


def require_openfinance(settings: Settings) -> OpenFinanceProvider:
    name = settings.openfinance_provider
    if not name or not settings.openfinance_client_id or not settings.openfinance_client_secret:
        raise OpenFinanceNotConfigured(NOT_CONFIGURED_MESSAGE)
    if name not in INTEGRATED_PROVIDERS:
        raise OpenFinanceNotIntegrated(f"provedor {name!r} ainda não integrado nesta versão")
    return OpenFinanceProvider(name=name)
