"use client";
import { Landmark } from "lucide-react";
import type { Currency, Quote, Source } from "@/lib/api/types";
import { MODALITY_LABEL } from "@/lib/api/types";
import { PairFlags } from "@/components/ui/currency-flag";
import { formatRateFixed } from "@/components/ui/rate";
import { Badge } from "@/components/ui/badge";
import { pickCardContext } from "./price-context";

const PAIRS: { base: Currency; quote: Currency }[] = [
  { base: "USD", quote: "PYG" },
  { base: "BRL", quote: "PYG" },
  { base: "USD", quote: "BRL" },
];

/**
 * Faixa de cotações no topo de Mercados (ME1): uma linha por par, com bandeiras (dev/ui/spec-reforma-ui.md).
 * Melhor compra / melhor venda por par dentro de UM contexto (modalidade). A referência (BCP) aparece à parte com "≈"
 * e nunca como melhor preço; cotações por montante ficam fora. Ocupa até ~96 px de altura em lg.
 */
export function PriceCards({ quotes, sources }: { quotes: Quote[]; sources: Source[] }) {
  const name = (id: string) => sources.find((s) => s.id === id)?.name ?? id;
  return (
    <section aria-label="Cotações por par" className="grid grid-cols-1 gap-px overflow-hidden rounded-surface border border-border bg-border sm:grid-cols-3">
      {PAIRS.map((p) => {
        const ctx = pickCardContext(quotes, p);
        return (
          <article key={`${p.base}${p.quote}`} data-testid={`price-card-${p.base}${p.quote}`} className="grid min-w-0 content-start gap-1.5 bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-body font-semibold">
                <PairFlags base={p.base} quote={p.quote} />
              </h2>
              <span className="text-caption text-muted">{p.quote} por 1 {p.base}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Melhor compra" value={ctx.bestBuy ? formatRateFixed(ctx.bestBuy.buy, p.quote) : "—"} sub={ctx.bestBuy ? name(ctx.bestBuy.source_id) : "sem cotação neste contexto"} />
              <Stat label="Melhor venda" value={ctx.bestSell ? formatRateFixed(ctx.bestSell.sell, p.quote) : "—"} sub={ctx.bestSell ? name(ctx.bestSell.source_id) : "sem cotação neste contexto"} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-1 text-caption text-muted">
              <span className="min-w-0 truncate">
                {ctx.modality ? (
                  <>
                    {ctx.count} cotaç{ctx.count === 1 ? "ão" : "ões"} · {MODALITY_LABEL[ctx.modality]}
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
          </article>
        );
      })}
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="min-w-0">
      <p className="text-caption text-muted">{label}</p>
      <p className="fx-num text-heading font-semibold text-foreground">{value}</p>
      <p className="truncate text-caption text-muted">{sub}</p>
    </div>
  );
}
