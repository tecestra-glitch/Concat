"use client";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { CITY_LABEL } from "@/lib/api/types";
import { useSources } from "@/lib/queries";
import { DEMO_CAPITALS } from "@/lib/api/demo-data";

export interface MarketFilters {
  city: string;
  base: string;
  source: string;
  capital: string;
}

export const DEFAULT_FILTERS: MarketFilters = { city: "all", base: "all", source: "all", capital: "5000" };

export function Filters({ value, onChange, showCapital = true }: { value: MarketFilters; onChange: (v: MarketFilters) => void; showCapital?: boolean }) {
  const { data: sources } = useSources();
  const set = (k: keyof MarketFilters) => (v: string) => onChange({ ...value, [k]: v });
  return (
    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap" role="group" aria-label="Filtros">
      <Field label="Cidade">
        <Select value={value.city} onValueChange={set("city")}>
          <SelectTrigger aria-label="Cidade" className="sm:w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas</SelectItem>
            {(["CDE", "ASU", "PJC"] as const).map((c) => <SelectItem key={c} value={c}>{CITY_LABEL[c]}</SelectItem>)}
            <SelectItem value="digital">Digital (sem cidade)</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="Moeda">
        <Select value={value.base} onValueChange={set("base")}>
          <SelectTrigger aria-label="Moeda" className="sm:w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas</SelectItem>
            <SelectItem value="USD">USD</SelectItem>
            <SelectItem value="BRL">BRL</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="Provedor">
        <Select value={value.source} onValueChange={set("source")}>
          <SelectTrigger aria-label="Provedor" className="sm:w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            {(sources ?? []).map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </Field>
      {showCapital && (
        <Field label="Orçamento">
          <Select value={value.capital} onValueChange={set("capital")}>
            <SelectTrigger aria-label="Orçamento" className="sm:w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DEMO_CAPITALS.map((c) => <SelectItem key={c} value={String(c)}>R$ {c.toLocaleString("pt-BR")}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
