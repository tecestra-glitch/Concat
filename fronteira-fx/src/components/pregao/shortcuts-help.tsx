"use client";
import type { ReactElement } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { HotkeyBinding } from "@/lib/pregao/use-hotkeys";

const GROUP_ORDER: HotkeyBinding["group"][] = ["Gráfico", "Par", "Ajuda"];

/** Agrupa os atalhos na ordem Gráfico, Par, Ajuda. Grupos sem itens não aparecem. */
export function groupBindings(bindings: readonly HotkeyBinding[]): { group: HotkeyBinding["group"]; items: HotkeyBinding[] }[] {
  return GROUP_ORDER.map((group) => ({ group, items: bindings.filter((b) => b.group === group) })).filter((g) => g.items.length > 0);
}

/** Rótulo visível da tecla: "Escape" vira "Esc"; as demais ficam como estão. */
export function keyLabel(key: string): string {
  return key === "Escape" ? "Esc" : key;
}

/** Lista `<dl>` de atalhos. Puro, por isso testável com renderToStaticMarkup (D45). */
export function ShortcutsList({ bindings }: { bindings: readonly HotkeyBinding[] }): ReactElement {
  return (
    <dl data-testid="pregao-shortcuts-list" className="grid gap-3">
      {groupBindings(bindings).map(({ group, items }) => (
        <div key={group}>
          <h4 className="text-xs font-medium text-muted">{group}</h4>
          {items.map((b) => (
            <div key={b.key} className="flex items-center gap-3">
              <dt>
                <kbd className="tnum rounded border border-border bg-surface-2 px-1.5 text-xs">{keyLabel(b.key)}</kbd>
              </dt>
              <dd className="text-sm">{b.description}</dd>
            </div>
          ))}
        </div>
      ))}
    </dl>
  );
}

export interface ShortcutsHelpProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bindings: readonly HotkeyBinding[];
}

/** Diálogo de ajuda: foco preso, retorno de foco e Esc vêm do Radix. */
export function ShortcutsHelp({ open, onOpenChange, bindings }: ShortcutsHelpProps): ReactElement {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="pregao-shortcuts">
        <DialogHeader>
          <DialogTitle>Atalhos do teclado</DialogTitle>
          <DialogDescription>Os atalhos não funcionam enquanto um campo de texto está em foco.</DialogDescription>
        </DialogHeader>
        <ShortcutsList bindings={bindings} />
      </DialogContent>
    </Dialog>
  );
}
