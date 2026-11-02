"use client";
import { Landmark } from "lucide-react";
import type { Currency, Quote, Source } from "@/lib/api/types";
import { MODALITY_LABEL } from "@/lib/api/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatRateFixed } from "@/components/ui/rate";
import { pickCardContext } from "./price-context";

const PAIRS: { base: Currency; quote: Currency }[] = [
  { base: "USD", quote: "PYG" },
  { base: "BRL", quote: "PYG" },
  { base: "USD", quote: "BRL" },
];

/**
 * Melhor compra / melhor venda por par dentro de UM contexto (modalidade). A referência (BCP) aparece
 * à parte com "≈" e nunca como melhor preço; cotações por montante ficam fora.
 */
export function PriceCards({ quotes, sources }: { quotes: Quote[]; sources: Source[] }) {
  const name = (id: string) => sources.find((s) => s.id === id)?.name ?? id;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {PAIRS.map((p) => {
        const ctx = pickCardContext(quotes, p);
        return (
          <Card key={`${p.base}${p.quote}`} data-testid={`price-card-${p.base}${p.quote}`}>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="tnum text-base">{p.base}/{p.quote}</CardTitle>
              <CardDescription>{p.quote} por 1 {p.base}</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <Stat label="Melhor compra" value={ctx.bestBuy ? formatRateFixed(ctx.bestBuy.buy, p.quote) : "—"} sub={ctx.bestBuy ? name(ctx.bestBuy.source_id) : "sem cotação neste contexto"} />
              <Stat label="Melhor venda" value={ctx.bestSell ? formatRateFixed(ctx.bestSell.sell, p.quote) : "—"} sub={ctx.bestSell ? name(ctx.bestSell.source_id) : "sem cotação neste contexto"} />
              <div className="col-span-2 flex flex-wrap items-center justify-between gap-1 text-xs text-muted">
                <span>
                  {ctx.modality ? (
                    <>
                      {ctx.count} cotaç{ctx.count === 1 ? "ão" : "ões"} · {MODALITY_LABEL[ctx.modality]}
                      {ctx.otherModalities.length > 0 && <span> · outras: {ctx.otherModalities.map((m) => MODALITY_LABEL[m]).join(", ")}</span>}
                    </>
                  ) : (
                    "sem cotação executável"
                  )}
                </span>
                {ctx.reference && (
                  <Badge variant="reference" title={`${name(ctx.reference.source_id)} — referência de mercado, não executável`}>
                    <Landmark className="size-3" aria-hidden /> ≈ {name(ctx.reference.source_id)} {formatRateFixed(ctx.reference.buy, p.quote, { reference: true })}
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className="tnum text-xl font-semibold">{value}</p>
      <p className="truncate text-xs text-muted">{sub}</p>
    </div>
  );
}
