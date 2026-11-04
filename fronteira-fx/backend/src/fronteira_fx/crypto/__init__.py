"""Adaptadores de cripto somente leitura (ticker, livro de ofertas, VWAP e taxa por exchange).

Nada deste pacote envia ordem, cancela, saca ou acessa conta: o cliente HTTP só faz GET em caminhos
de dados públicos listados em cada adaptador (ver `guard.py`). Sem chave de API.
"""

from .types import Level, OrderBook, Side, Ticker, VenueFee, VwapFill
from .vwap import vwap_for_target

__all__ = ["Level", "OrderBook", "Side", "Ticker", "VenueFee", "VwapFill", "vwap_for_target"]
