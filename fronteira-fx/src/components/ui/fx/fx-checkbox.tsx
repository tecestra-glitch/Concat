"use client";
/**
 * Crédito Uiverse.io: slug `checkbox-circular`; elemento faxriddin20_wicked-bobcat-36; autor faxriddin20; licença MIT; link https://uiverse.io/faxriddin20/wicked-bobcat-36
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
/**
 * Caixa circular. Elemento Uiverse «checkbox-circular» (faxriddin20), MIT, Uiverse.io. O `input` fica visualmente
 * oculto (sr-only), não `display: none`, para continuar acessível por teclado. Marcado: --gain.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export interface FxCheckboxProps {
  id: string;
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export function FxCheckbox({ id, label, checked, onCheckedChange, disabled = false, className }: FxCheckboxProps) {
  return (
    <label htmlFor={id} className={cn("inline-flex min-h-11 cursor-pointer items-center gap-2 text-body sm:min-h-8", disabled && "cursor-not-allowed opacity-50", className)}>
      <input id={id} type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onCheckedChange(e.target.checked)} />
      <span
        aria-hidden
        className="peer-focus-visible:outline-ring relative grid size-5 shrink-0 place-items-center rounded-full border-2 border-control-border transition-colors duration-(--motion-fast) peer-checked:border-gain peer-checked:bg-gain-soft peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2"
      >
        <span className="size-2 rounded-full bg-gain opacity-0 transition-opacity duration-150 peer-checked:opacity-100" />
      </span>
      <span>{label}</span>
    </label>
  );
}
