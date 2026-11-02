"use client";
import type { ReactElement } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Delta } from "@/components/pregao/delta";
import { formatAge, formatRate, toNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { diffPct, impliedBrlPyg, type ImpliedCross, type Leg } from "@/lib/pregao/cross";

export interface CrossRateCardProps {
  house: string;
  usdPyg: Leg | null;
  usdBrl: Leg | null;
  /** BRL/PYG publicado pela mesma casa. */
  direct: Leg | null;
  /** ms epoch; 0 = sem relógio (no servidor). */
  now: number;
  className?: string;
}

export function crossState(p: Pick<CrossRateCardProps, "usdPyg" | "usdBrl">): "empty" | "ready" {
  return p.usdPyg === null || p.usdBrl === null ? "empty" : "ready";
}

/** PYG inteiro para valores calculados (§0.10): arredonda antes de `formatRate`. Nulo vira "—". */
export function fmtPyg(v: string | null): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return formatRate(Math.round(n), "PYG");
}

/** A perna mais antiga entre as duas; data inválida vai para `formatAge` como "sem dados". */
function oldestCapturedAt(legs: ImpliedCross["legs"]): string {
  const a = legs.usdPyg.captured_at;
  const b = legs.usdBrl.captured_at;
  const ta = Date.parse(a);
  const tb = Date.parse(b);
  if (Number.isNaN(ta)) return a;
  if (Number.isNaN(tb)) return b;
  return ta <= tb ? a : b;
}

interface ReadyBodyProps {
  implied: ImpliedCross;
  direct: Leg | null;
  now: number;
}

function ReadyBody({ implied, direct, now }: ReadyBodyProps): ReactElement {
  const footer =
    now > 0
      ? `Cálculo local com as cotações de ${formatAge(oldestCapturedAt(implied.legs), now)}. Nenhuma casa oferece este preço.`
      : "Cálculo local com as cotações publicadas pela casa. Nenhuma casa oferece este preço.";
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
        <dt className="text-muted">Implícito (via USD)</dt>
        <dd className="tnum flex flex-wrap gap-x-4">
          <span>
            <span className="text-muted">Compra </span>
            <span className="text-foreground">{fmtPyg(implied.buy)}</span>
          </span>
          <span>
            <span className="text-muted">Venda </span>
            <span className="text-foreground">{fmtPyg(implied.sell)}</span>
          </span>
        </dd>

        <dt className="text-muted">Direto</dt>
        <dd className="tnum flex flex-wrap gap-x-4">
          {direct === null ? (
            <span className="text-muted">não publicado</span>
          ) : (
            <>
              <span>
                <span className="text-muted">Compra </span>
                <span className="text-foreground">{formatRate(direct.buy, "PYG")}</span>
              </span>
              <span>
                <span className="text-muted">Venda </span>
                <span className="text-foreground">{formatRate(direct.sell, "PYG")}</span>
              </span>
            </>
          )}
        </dd>

        <dt className="text-muted">Diferença</dt>
        <dd className="flex flex-wrap gap-x-4">
          <span className="inline-flex items-center gap-1">
            <span className="text-muted">Compra</span>
            <Delta value={diffPct(direct?.buy ?? null, implied.buy)} />
            <span className="sr-only">direto em relação ao implícito</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="text-muted">Venda</span>
            <Delta value={diffPct(direct?.sell ?? null, implied.sell)} />
            <span className="sr-only">direto em relação ao implícito</span>
          </span>
        </dd>
      </dl>
      <p className="text-xs text-muted">{footer}</p>
    </>
  );
}

/** Cartão informativo do cruzamento BRL/PYG via USD dentro de uma casa; nada aqui é executável. */
export function CrossRateCard({ house, usdPyg, usdBrl, direct, now, className }: CrossRateCardProps): ReactElement {
  const state = crossState({ usdPyg, usdBrl });
  const implied = usdPyg !== null && usdBrl !== null ? impliedBrlPyg(usdPyg, usdBrl, new Date(now)) : null;
  const stale = implied !== null && now > 0 && implied.stale;
  return (
    <Card className={cn("flex flex-col gap-3 p-4", className)} data-testid="pregao-cross" data-state={state}>
      <CardHeader className="flex-row flex-wrap items-center gap-2 space-y-0 p-0">
        <CardTitle className="text-sm">BRL/PYG cruzado via USD</CardTitle>
        {implied !== null && implied.incomplete ? <Badge variant="warn">incompleto</Badge> : null}
        {stale ? <Badge variant="warn">pernas antigas</Badge> : null}
        <CardDescription className="w-full">{`${house} — informativo, não executável`}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-0">
        {implied === null ? (
          <p className="text-sm text-muted">Esta casa não publica as duas pernas em USD.</p>
        ) : (
          <ReadyBody implied={implied} direct={direct} now={now} />
        )}
      </CardContent>
    </Card>
  );
}
