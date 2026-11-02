"use client";
import type { Quote } from "@/lib/api/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatRate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";

/** Best buy / best sell per pair across the filtered quotes. */
export function PriceCards({ quotes }: { quotes: Quote[] }) {
  const pairs = [
    { base: "USD", quote: "PYG" },
    { base: "BRL", quote: "PYG" },
    { base: "USD", quote: "BRL" },
  ] as const;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {pairs.map((p) => {
        const list = quotes.filter((q) => q.base === p.base && q.quote === p.quote && q.kind !== "market_reference");
        const ref = quotes.find((q) => q.base === p.base && q.quote === p.quote && q.kind === "market_reference");
        const bestBuy = list.filter((q) => q.buy !== null).sort((a, b) => Number(b.buy) - Number(a.buy))[0];
        const bestSell = list.filter((q) => q.sell !== null).sort((a, b) => Number(a.sell) - Number(b.sell))[0];
        return (
          <Card key={`${p.base}${p.quote}`} data-testid={`price-card-${p.base}${p.quote}`}>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="tnum text-base">{p.base}/{p.quote}</CardTitle>
              <CardDescription>{p.quote} por 1 {p.base}</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <Stat label="Melhor compra" value={bestBuy ? formatRate(bestBuy.buy, p.quote) : "—"} sub={bestBuy ? bestBuy.source_id : "sem cotação"} tone="gain" />
              <Stat label="Melhor venda" value={bestSell ? formatRate(bestSell.sell, p.quote) : "—"} sub={bestSell ? bestSell.source_id : "sem cotação"} tone="loss" />
              <div className="col-span-2 flex items-center justify-between text-xs text-muted">
                <span>{list.length} cotações</span>
                {ref && <Badge variant="accent">Ref. BCP {formatRate(ref.buy, p.quote)}</Badge>}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: "gain" | "loss" }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p className={`tnum text-xl font-semibold ${tone === "gain" ? "text-gain" : "text-loss"}`}>{value}</p>
      <p className="truncate text-xs text-muted">{sub}</p>
    </div>
  );
}
