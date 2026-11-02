#!/usr/bin/env python3
"""Cruzamento de câmbio: ciclos e rotas no grafo de posições (moeda@venue).

Uso:
  python3 cruzar.py entrada.json [--json] [--max-arestas N] [--roi-minimo X]
  python3 cruzar.py entrada.json --de BRL@brbank --para PYG@ueno [--json]

Sem dependências externas. Decimal em tudo; arredondamento só na exibição.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, getcontext

getcontext().prec = 28
ZERO, ONE = Decimal(0), Decimal(1)
ORDEM = {"cotada": 0, "estimada": 1, "incompleta": 2}
LIMIAR_PRESENCIAL = Decimal("0.01")


@dataclass(frozen=True)
class Aresta:
    de: str
    para: str
    taxa: Decimal
    custo_pct: Decimal = ZERO
    custo_fixo: Decimal = ZERO
    minutos: int = 0
    via: str = ""
    confianca: str = "estimada"
    evidencia: str | None = None
    min_in: Decimal | None = None
    max_in: Decimal | None = None

    def aplicar(self, valor: Decimal) -> Decimal | None:
        if self.min_in is not None and valor < self.min_in:
            return None
        if self.max_in is not None and valor > self.max_in:
            return None
        return valor * (ONE - self.custo_pct) * self.taxa - self.custo_fixo

    def dicionario(self) -> dict:
        return {"de": self.de, "para": self.para, "taxa": str(self.taxa), "custo_pct": str(self.custo_pct),
                "custo_fixo": str(self.custo_fixo), "minutos": self.minutos, "via": self.via,
                "confianca": self.confianca, "evidencia": self.evidencia}


def dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v))


def pior(a: str, b: str) -> str:
    return a if ORDEM.get(a, 1) >= ORDEM.get(b, 1) else b


def presencial(no: str) -> bool:
    venue = no.split("@", 1)[1] if "@" in no else no
    return venue.startswith("cash:") or ":" in venue


def montar(entrada: dict) -> tuple[list[Aresta], dict[str, Decimal]]:
    arestas: list[Aresta] = []
    for q in entrada.get("cotacoes", []):
        if q.get("tipo") == "referencia":
            continue
        venue = f"{q['fonte']}:{q['cidade']}" if q.get("cidade") else str(q["fonte"])
        base, cotada = q["base"], q["cotada"]
        minutos = 0 if q.get("modalidade") == "dinheiro" else 1
        conf = "cotada" if q.get("tipo") == "executavel" else "estimada"
        pct = sum((dec(t["valor"]) or ZERO) / Decimal(100) for t in q.get("taxas", []) if "%" in str(t.get("rotulo", "")))
        montante = dec(q.get("montante"))
        ev = q.get("evidencia")
        compra, venda = dec(q.get("compra")), dec(q.get("venda"))
        if compra and compra > 0:
            arestas.append(Aresta(f"{base}@{venue}", f"{cotada}@{venue}", compra, pct, ZERO, minutos,
                                  f"{q['fonte']} compra {base}", conf, ev, montante, montante))
        if venda and venda > 0:
            arestas.append(Aresta(f"{cotada}@{venue}", f"{base}@{venue}", ONE / venda, pct, ZERO, minutos,
                                  f"{q['fonte']} vende {base}", conf, ev))
    for t in entrada.get("transferencias", []):
        arestas.append(Aresta(t["de"], t["para"], dec(t.get("taxa", "1")) or ONE, dec(t.get("custo_pct")) or ZERO,
                              dec(t.get("custo_fixo")) or ZERO, int(t.get("minutos", 0)), t.get("via", ""),
                              t.get("confianca", "estimada"), t.get("evidencia"), dec(t.get("min")), dec(t.get("max"))))
    saldos = {k: dec(v) for k, v in entrada.get("saldos", {}).items() if dec(v) and dec(v) > 0}
    return arestas, saldos


def resultado(inicio: str, caminho: list[str], usadas: list[Aresta], entrada: Decimal, saida: Decimal, minutos: int, conf: str) -> dict:
    ganho = saida - entrada
    roi = ganho / entrada if entrada else ZERO
    return {"inicio": inicio, "caminho": caminho, "arestas": [a.dicionario() for a in usadas], "entrada": str(entrada),
            "saida": str(saida), "ganho": str(ganho), "roi": str(roi), "roi_dia": str(roi * (Decimal(1440) / Decimal(max(1, minutos)))),
            "minutos": minutos, "confianca": conf, "canal": "presencial" if any(presencial(n) for n in caminho) else "digital"}


def ciclos(arestas: list[Aresta], saldos: dict[str, Decimal], max_arestas: int, roi_minimo: Decimal | None) -> list[dict]:
    saida_de: dict[str, list[Aresta]] = defaultdict(list)
    for a in arestas:
        saida_de[a.de].append(a)
    achados: list[dict] = []

    def anda(inicio, no, valor, caminho, usadas, minutos, conf):
        if len(usadas) >= max_arestas:
            return
        for a in saida_de.get(no, []):
            if a.para == inicio:
                if not usadas:
                    continue
                final = a.aplicar(valor)
                if final is None:
                    continue
                r = resultado(inicio, [*caminho, inicio], [*usadas, a], saldos[inicio], final, minutos + a.minutos, pior(conf, a.confianca))
                if roi_minimo is None or Decimal(r["roi"]) >= roi_minimo:
                    achados.append(r)
                continue
            if a.para in caminho:
                continue
            prox = a.aplicar(valor)
            if prox is None or prox <= 0:
                continue
            anda(inicio, a.para, prox, [*caminho, a.para], [*usadas, a], minutos + a.minutos, pior(conf, a.confianca))

    for inicio, valor in saldos.items():
        anda(inicio, inicio, valor, [inicio], [], 0, "cotada")
    return achados


def rotas(arestas: list[Aresta], saldos: dict[str, Decimal], de: str, para: str, max_arestas: int) -> list[dict]:
    saida_de: dict[str, list[Aresta]] = defaultdict(list)
    for a in arestas:
        saida_de[a.de].append(a)
    valor0 = saldos.get(de)
    if valor0 is None:
        raise SystemExit(f"sem saldo em {de}: informe em 'saldos'")
    achados: list[dict] = []

    def anda(no, valor, caminho, usadas, minutos, conf):
        if no == para and usadas:
            achados.append(resultado(de, caminho, usadas, valor0, valor, minutos, conf))
            return
        if len(usadas) >= max_arestas:
            return
        for a in saida_de.get(no, []):
            if a.para in caminho:
                continue
            prox = a.aplicar(valor)
            if prox is None or prox <= 0:
                continue
            anda(a.para, prox, [*caminho, a.para], [*usadas, a], minutos + a.minutos, pior(conf, a.confianca))

    anda(de, valor0, [de], [], 0, "cotada")
    return achados


def classificar(itens: list[dict], chave_valor: str) -> list[dict]:
    """Aplica o ranking: digital > 0 entra; presencial precisa de ganho > 0 e ROI >= melhor digital + 1 p.p."""
    melhor_digital = max((Decimal(i[chave_valor]) for i in itens if i["canal"] == "digital"), default=None)
    for i in itens:
        valor = Decimal(i[chave_valor])
        ganho = Decimal(i["ganho"])
        if i["canal"] == "digital":
            i["ranking_principal"] = ganho > 0
            i["motivo"] = "digital com ganho líquido positivo" if ganho > 0 else "digital sem ganho líquido"
        else:
            if ganho <= 0:
                i["ranking_principal"], i["motivo"] = False, "presencial sem ganho líquido após custos"
            elif melhor_digital is None:
                i["ranking_principal"], i["motivo"] = True, "presencial sem digital comparável"
            else:
                limiar = melhor_digital + LIMIAR_PRESENCIAL
                i["ranking_principal"] = valor >= limiar
                i["motivo"] = (f"presencial supera melhor digital em ≥ 1 p.p. ({pct(valor)} vs {pct(melhor_digital)})" if i["ranking_principal"]
                               else f"presencial abaixo do limite: precisa ROI ≥ {pct(limiar)}")
        if i["confianca"] == "incompleta":
            i["motivo"] += "; estimativa incompleta (custo essencial desconhecido)"
    itens.sort(key=lambda i: Decimal(i[chave_valor]), reverse=True)
    return itens


def pct(x: Decimal) -> str:
    v = x * 100
    casas = 2
    while casas < 6 and v != 0 and abs(v) * (Decimal(10) ** casas) < 10:
        casas += 1
    return f"{v:,.{casas}f} %".replace(",", "X").replace(".", ",").replace("X", ".")


def dinheiro(x: Decimal, moeda: str) -> str:
    casas = 0 if moeda == "PYG" else 2
    while casas < 8 and x != 0 and abs(x) * (Decimal(10) ** casas) < 10:
        casas += 1
    s = f"{abs(x):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    simbolo = {"BRL": "R$", "USD": "US$", "PYG": "₲"}.get(moeda, moeda)
    return f"{'−' if x < 0 else '+' if x > 0 else ''}{simbolo} {s}"


def tabela(itens: list[dict], titulo: str) -> str:
    linhas = [f"### {titulo}", "", "| # | Início | Caminho | Saldo usado | Ganho | ROI | ROI/dia | Prazo | Confiança | Canal | Ranking |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, i in enumerate(itens, 1):
        moeda = i["inicio"].split("@")[0]
        prazo = f"{Decimal(i['minutos']) / 1440:.1f} d".replace(".", ",") if i["minutos"] >= 1440 else f"{i['minutos']} min"
        linhas.append(f"| {n} | {i['inicio']} | {' → '.join(i['caminho'])} | {dinheiro(Decimal(i['entrada']), moeda).lstrip('+')} | "
                      f"{dinheiro(Decimal(i['ganho']), moeda)} | {pct(Decimal(i['roi']))} | {pct(Decimal(i['roi_dia']))} | {prazo} | "
                      f"{i['confianca']} | {i['canal']} | {'principal' if i['ranking_principal'] else 'secundário'} — {i['motivo']} |")
    if len(itens) == 0:
        linhas.append("| — | nenhum resultado | | | | | | | | | |")
    return "\n".join(linhas)


def referencia_mercado(entrada: dict, moeda_de: str, moeda_para: str) -> Decimal | None:
    """Taxa de mercado (BCP ou similar) entre moeda_de e moeda_para, sem intermediário."""
    for q in entrada.get("cotacoes", []):
        if q.get("tipo") != "referencia":
            continue
        if q["base"] == moeda_de and q["cotada"] == moeda_para:
            v = dec(q.get("compra") or q.get("venda"))
            if v and v > 0:
                return v
        if q["base"] == moeda_para and q["cotada"] == moeda_de:
            v = dec(q.get("venda") or q.get("compra"))
            if v and v > 0:
                return ONE / v
    return None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("entrada")
    p.add_argument("--json", action="store_true", help="saída JSON em vez de tabela")
    p.add_argument("--max-arestas", type=int, default=None)
    p.add_argument("--roi-minimo", type=str, default=None)
    p.add_argument("--de", help="nó de origem para rotas abertas (remessa)")
    p.add_argument("--para", help="nó de destino para rotas abertas")
    a = p.parse_args(argv)
    with open(a.entrada, encoding="utf-8") as f:
        entrada = json.load(f)
    arestas, saldos = montar(entrada)
    max_arestas = a.max_arestas or int(entrada.get("max_arestas", 6))
    roi_min = dec(a.roi_minimo) if a.roi_minimo is not None else dec(entrada.get("roi_minimo"))
    ignoradas = [q for q in entrada.get("cotacoes", []) if q.get("tipo") == "referencia"]
    if (a.de is None) != (a.para is None):
        p.error("--de e --para andam juntos")
    if a.de:
        itens = rotas(arestas, saldos, a.de, a.para, max_arestas)
        for i in itens:
            i["taxa_efetiva"] = str(Decimal(i["saida"]) / Decimal(i["entrada"]))
        # Para rotas, a medida é a taxa efetiva; "ganho" e "roi" passam a ser a economia relativa
        # à referência: melhor rota digital, senão referência de mercado (BCP), senão a melhor rota.
        melhor_dig = max((Decimal(i["taxa_efetiva"]) for i in itens if i["canal"] == "digital"), default=None)
        moeda_de, moeda_para = a.de.split("@")[0], a.para.split("@")[0]
        ref_bcp = referencia_mercado(entrada, moeda_de, moeda_para)
        if melhor_dig is not None:
            ref, nome_ref = melhor_dig, "melhor rota digital"
        elif ref_bcp is not None:
            ref, nome_ref = ref_bcp, "referência de mercado (não executável)"
        else:
            ref, nome_ref = max((Decimal(i["taxa_efetiva"]) for i in itens), default=ONE), "melhor rota encontrada"
        for i in itens:
            te = Decimal(i["taxa_efetiva"])
            economia = (te / ref - 1) if ref else ZERO
            i["economia_vs_referencia"] = str(economia)
            i["referencia"] = {"nome": nome_ref, "taxa": str(ref)}
            i["ganho"] = str(economia * Decimal(i["entrada"]))  # economia equivalente na moeda de origem
            i["roi"] = str(economia)
            i["roi_dia"] = str(economia * (Decimal(1440) / Decimal(max(1, i["minutos"]))))
        titulo = (f"Rotas {a.de} → {a.para} (taxa efetiva = saída ÷ entrada; economia relativa à {nome_ref}"
                  f" = {moeda_para} {ref:,.4f} por 1 {moeda_de})")
        itens = classificar(itens, "roi")
        for i in itens:
            if i["canal"] == "digital" and Decimal(i["taxa_efetiva"]) == melhor_dig:
                i["ranking_principal"], i["motivo"] = True, "melhor rota digital (referência)"
    else:
        itens = classificar(ciclos(arestas, saldos, max_arestas, roi_min), "roi")
        chave, titulo = "roi", "Ciclos a partir do saldo estacionado"
    if a.json:
        print(json.dumps({"itens": itens, "referencias_ignoradas": [f"{q['fonte']} {q['base']}/{q['cotada']}" for q in ignoradas],
                          "nos_com_saldo": {k: str(v) for k, v in saldos.items()}, "arestas": len(arestas)}, ensure_ascii=False, indent=2))
    else:
        print(tabela(itens, titulo))
        if ignoradas:
            print("\nReferências de mercado ignoradas como aresta (não executáveis): " + ", ".join(f"{q['fonte']} {q['base']}/{q['cotada']}" for q in ignoradas))
        print(f"\nNós com saldo: {', '.join(f'{k}={v}' for k, v in saldos.items())} · {len(arestas)} arestas · máx. {max_arestas} arestas por ciclo")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
