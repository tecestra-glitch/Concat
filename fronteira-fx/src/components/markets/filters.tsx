"use client";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { CITY_LABEL } from "@/lib/api/types";
import { useSources } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { capitalOptions } from "@/lib/api/capitals";
import { formatMoney } from "@/lib/format";

export interface MarketFilters {
  city: string;
  base: string;
  source: string;
  capital: string;
  /** Montante do simulador (string decimal) ou "all". Vai para a API como `amount`. */
  amount: string;
}

export const DEFAULT_FILTERS: MarketFilters = { city: "all", base: "all", source: "all", capital: "5000", amount: "all" };

/**
 * `city = "digital"` nunca sai como `city` na query: o cliente (`api.quotes`) remove o valor e aplica
 * `city === null` localmente; aqui a opção só existe para o usuário.
 */
export function Filters({ value, onChange, showCapital = true, showAmount = false, idPrefix = "f" }: { value: MarketFilters; onChange: (v: MarketFilters) => void; showCapital?: boolean; showAmount?: boolean; idPrefix?: string }) {
  const { data: sources } = useSources();
  const { mode, settings } = useSettings();
  const capitals = capitalOptions(mode, settings.defaultCapital);
  const set = (k: keyof MarketFilters) => (v: string) => onChange({ ...value, [k]: v });
  const id = (k: string) => `${idPrefix}-${k}`;
  return (
    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap" role="group" aria-label="Filtros">
      <Field label="Cidade" id={id("city")}>
        <Select value={value.city} onValueChange={set("city")}>
          <SelectTrigger id={id("city")} aria-label="Cidade" className="sm:w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas</SelectItem>
            {(["CDE", "ASU", "PJC"] as const).map((c) => <SelectItem key={c} value={c}>{CITY_LABEL[c]}</SelectItem>)}
            <SelectItem value="digital">Digital (sem cidade)</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="Moeda" id={id("base")}>
        <Select value={value.base} onValueChange={set("base")}>
          <SelectTrigger id={id("base")} aria-label="Moeda" className="sm:w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas</SelectItem>
            <SelectItem value="USD">USD</SelectItem>
            <SelectItem value="BRL">BRL</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="Provedor" id={id("source")}>
        <Select value={value.source} onValueChange={set("source")}>
          <SelectTrigger id={id("source")} aria-label="Provedor" className="sm:w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            {(sources ?? []).map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </Field>
      {showCapital && (
        <Field label="Orçamento" id={id("capital")}>
          <Select value={value.capital} onValueChange={set("capital")}>
            <SelectTrigger id={id("capital")} aria-label="Orçamento" className="sm:w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              {capitals.map((c) => <SelectItem key={c} value={String(c)}>{formatMoney(c, "BRL")}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
      )}
      {showAmount && (
        <Field label="Montante" id={id("amount")}>
          <Select value={value.amount} onValueChange={set("amount")}>
            <SelectTrigger id={id("amount")} aria-label="Montante" className="sm:w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {capitals.map((c) => <SelectItem key={c} value={String(c)}>{formatMoney(c, "BRL")}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
      )}
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
