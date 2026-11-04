"use client";
/**
 * Início (`/`): candles do par principal e as melhores oportunidades, lado a lado em lg+ e empilhados no celular, com
 * o gráfico vindo antes da lista (dev/ui/spec-reforma-ui.md, seção 5a). A "Visão geral" deixou de existir como tela.
 */
import * as React from "react";
import type { PairKey } from "@/lib/pregao/types";
import { HomeCandles } from "./home-candles";
import { HomeOpportunities } from "./home-opportunities";

/** Par principal da home (o mesmo par de abertura do pregão). */
export const HOME_PAIR: PairKey = "USD/PYG";

export function Home() {
  const [pair, setPair] = React.useState<PairKey>(HOME_PAIR);
  return (
    <div data-testid="home-root" className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <HomeCandles pair={pair} onPairChange={setPair} />
      <HomeOpportunities />
    </div>
  );
}
