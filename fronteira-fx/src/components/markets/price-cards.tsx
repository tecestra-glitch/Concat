"use client";
import { Landmark } from "lucide-react";
import type { Currency, Quote, Source } from "@/lib/api/types";
import { MODALITY_LABEL } from "@/lib/api/types";
import { PairFlags } from "@/components/ui/currency-flag";
import { formatRateFixed } from "@/components/ui/rate";
import { pickCardContext } from "./price-context";

const PAIRS: { base: Currency; quote: Currency }[] = [
  { base: "USD", quote: "PYG" },
  { base: "BRL", quote: "PYG" },
  { base: "USD", quote: "BRL" },
];

/**
 * Faixa de cotações no topo de Mercados (ME1): um cartão por par, com bandeiras, melhor compra e melhor venda (cada
 * uma com a casa), contagem e modalidade; a referência (BCP) vai como texto, sem caixa extra.
 * Melhor compra / melhor venda por par dentro de UM contexto (modalidade). A referência nunca é melhor preço;
 * cotações por montante ficam fora. Até 96 px de altura em lg (medido no e2e de Mercados).
 */
export function PriceCards({ quotes, sources }: { quotes: Quote[]; sources: Source[] }) {
  const name = (id: string) => sources.find((s) => s.id === id)?.name ?? id;
  return (
    <section aria-label="Cotações por par" className="grid grid-cols-1 gap-px overflow-hidden rounded-surface border border-border bg-border sm:grid-cols-3">
      {PAIRS.map((p) => {
        const ctx = pickCardContext(quotes, p);
        return (
          <article key={`${p.base}${p.quote}`} data-testid={`price-card-${p.base}${p.quote}`} className="grid min-w-0 content-center gap-1 bg-surface px-3 py-1.5">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <h2 className="shrink-0 text-label font-semibold">
                <PairFlags base={p.base} quote={p.quote} />
              </h2>
              <span className="min-w-0 truncate text-caption text-muted">{p.quote} por 1 {p.base}</span>
            </div>
            <div className="grid min-w-0 gap-x-4 gap-y-1 min-[1200px]:grid-cols-2">
              <Stat label="Compra" value={ctx.bestBuy ? formatRateFixed(ctx.bestBuy.buy, p.quote) : "—"} sub={ctx.bestBuy ? name(ctx.bestBuy.source_id) : "sem cotação"} />
              <Stat label="Venda" value={ctx.bestSell ? formatRateFixed(ctx.bestSell.sell, p.quote) : "—"} sub={ctx.bestSell ? name(ctx.bestSell.source_id) : "sem cotação"} />
            </div>
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-caption text-muted">
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
                <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap" title={`${name(ctx.reference.source_id)}: referência de mercado, não executável`}>
                  <Landmark className="size-3" aria-hidden /> ≈ {name(ctx.reference.source_id)} {formatRateFixed(ctx.reference.buy, p.quote, { reference: true })}
                </span>
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
    <p className="grid min-w-0" title={`${label}: ${sub}`}>
      <span className="truncate text-caption text-muted">
        {label} · {sub}
      </span>
      <span className="fx-num justify-self-start text-body font-semibold text-foreground">{value}</span>
    </p>
  );
}
