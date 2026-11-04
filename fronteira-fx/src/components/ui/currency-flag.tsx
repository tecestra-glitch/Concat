import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Bandeiras em SVG (dev/ui/spec-reforma-ui.md, seção 5b-b). Geometria simples das bandeiras nacionais, de domínio
 * público: nenhuma arte de terceiros. Simplificações deliberadas: a bandeira PY não tem o brasão; a da UE usa
 * círculos no lugar das estrelas. Todo SVG é `aria-hidden`; o código da moeda é sempre texto ao lado.
 */
export type FlagCountry = "BR" | "US" | "PY" | "AR" | "EU";
export type FlagCode = "BRL" | "USD" | "PYG" | "ARS" | "EUR" | "USDT";

const COUNTRY_OF: Record<Exclude<FlagCode, "USDT">, FlagCountry> = { BRL: "BR", USD: "US", PYG: "PY", ARS: "AR", EUR: "EU" };

/** Bandeira de um código de moeda. USDT não tem bandeira (usa `CryptoIcon`): devolve `null`. */
export function countryOfCode(code: FlagCode): FlagCountry | null {
  return code === "USDT" ? null : COUNTRY_OF[code];
}

const W = 24;
const H = 16;

/** Estrelas da bandeira americana em grade simplificada (3 linhas de 5). */
const US_STARS = [1.5, 4, 6.5].flatMap((y) => [1.2, 3.1, 5, 6.9, 8.8].map((x) => ({ x, y })));

/** Círculos da bandeira europeia em anel (12, a cada 30°). */
const EU_CIRCLES = Array.from({ length: 12 }, (_, i) => {
  const a = (i * Math.PI) / 6;
  return { x: 12 + 4.6 * Math.cos(a), y: 8 + 4.6 * Math.sin(a) };
});

function Stripes({ colors }: { colors: readonly string[] }) {
  const h = H / colors.length;
  return (
    <>
      {colors.map((c, i) => (
        <rect key={i} x={0} y={i * h} width={W} height={h + 0.05} fill={c} />
      ))}
    </>
  );
}

function FlagShapes({ country }: { country: FlagCountry }) {
  switch (country) {
    case "BR":
      return (
        <>
          <rect x={0} y={0} width={W} height={H} fill="#009c3b" />
          <polygon points="12,1.5 22.5,8 12,14.5 1.5,8" fill="#ffdf00" />
          <circle cx={12} cy={8} r={3.4} fill="#002776" />
        </>
      );
    case "US": {
      const stripe = H / 13;
      return (
        <>
          {Array.from({ length: 13 }, (_, i) => (
            <rect key={i} x={0} y={i * stripe} width={W} height={stripe + 0.05} fill={i % 2 === 0 ? "#b22234" : "#ffffff"} />
          ))}
          <rect x={0} y={0} width={9.6} height={8.6} fill="#3c3b6e" />
          {US_STARS.map((s, i) => (
            <circle key={i} cx={s.x} cy={s.y} r={0.35} fill="#ffffff" />
          ))}
        </>
      );
    }
    case "PY":
      return <Stripes colors={["#d52b1e", "#ffffff", "#0038a8"]} />;
    case "AR":
      return (
        <>
          <Stripes colors={["#74acdf", "#ffffff", "#74acdf"]} />
          <circle cx={12} cy={8} r={1.6} fill="#f6b40e" />
        </>
      );
    case "EU":
      return (
        <>
          <rect x={0} y={0} width={W} height={H} fill="#003399" />
          {EU_CIRCLES.map((c, i) => (
            <circle key={i} cx={c.x} cy={c.y} r={0.6} fill="#ffcc00" />
          ))}
        </>
      );
  }
}

/** SVG da bandeira de um país (24 × 16). Decorativo: `aria-hidden`. */
export function FlagIcon({ country, className }: { country: FlagCountry; className?: string }) {
  return (
    <span aria-hidden="true" className={cn("inline-flex h-3.5 w-5 shrink-0 overflow-hidden rounded-chip ring-1 ring-black/10", className)}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" aria-hidden="true" focusable="false" preserveAspectRatio="none">
        <FlagShapes country={country} />
      </svg>
    </span>
  );
}

/** Ícone próprio do USDT (círculo verde com T). Não é bandeira. Decorativo. */
export function CryptoIcon({ className }: { className?: string }) {
  return (
    <span aria-hidden="true" className={cn("inline-flex size-3.5 shrink-0", className)}>
      <svg viewBox="0 0 16 16" width="100%" height="100%" aria-hidden="true" focusable="false">
        <circle cx={8} cy={8} r={8} fill="#26a17b" />
        <rect x={4.2} y={4} width={7.6} height={1.8} fill="#ffffff" />
        <rect x={7.1} y={4} width={1.8} height={8} fill="#ffffff" />
      </svg>
    </span>
  );
}

/** Código da moeda com a bandeira (ou o ícone do USDT) à esquerda. O código é sempre texto visível. */
export function CurrencyFlag({ code, className }: { code: FlagCode; className?: string }) {
  const country = countryOfCode(code);
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      {country ? <FlagIcon country={country} /> : <CryptoIcon />}
      <span className="font-medium">{code}</span>
    </span>
  );
}

/** Par com duas bandeiras separadas por "/". O nome acessível continua sendo o texto "USD/PYG". */
export function PairFlags({ base, quote, className }: { base: FlagCode; quote: FlagCode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap", className)}>
      <CurrencyFlag code={base} />
      <span className="text-muted">/</span>
      <CurrencyFlag code={quote} />
    </span>
  );
}
