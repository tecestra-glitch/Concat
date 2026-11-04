"use client";
/**
 * Importação de extrato CSV/OFX. A tela só checa extensão e tamanho; o conteúdo é dado não confiável e é lido pelo
 * servidor. Em demonstração nada sai do navegador.
 */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { CatalogInstitution } from "@/lib/api/connections-catalog";
import type { Mode } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/input";
import { useSubmitState } from "@/components/ui/use-submit";
import { statementFileError } from "./connections-form";

export function StatementDialog({ open, onOpenChange, inst, mode }: { open: boolean; onOpenChange: (o: boolean) => void; inst: CatalogInstitution | null; mode: Mode }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {inst && <StatementForm key={inst.id} inst={inst} mode={mode} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function StatementForm({ inst, mode, onDone }: { inst: CatalogInstitution; mode: Mode; onDone: () => void }) {
  const qc = useQueryClient();
  const [file, setFile] = React.useState<File | null>(null);
  const [attempted, setAttempted] = React.useState(false);
  const submit = useSubmitState();
  const error = statementFileError(file);

  const onSubmit = async () => {
    setAttempted(true);
    if (!file || error) return;
    const ok = await submit.run(async () => {
      await api.importStatement(mode, inst.id, inst.name, file);
      await qc.invalidateQueries({ queryKey: ["connections", mode] });
    }, "Não foi possível importar o extrato.");
    if (ok) onDone();
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Importar extrato: {inst.name}</DialogTitle>
        <DialogDescription>Envie um arquivo CSV ou OFX exportado pela instituição. Até 5 MB. O servidor lê as linhas; esta tela não interpreta o conteúdo.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <Label htmlFor="statement-file">Arquivo de extrato (.csv ou .ofx)</Label>
        <input
          id="statement-file"
          name="statement"
          type="file"
          accept=".csv,.ofx,text/csv,application/x-ofx"
          className="block w-full text-body file:mr-3 file:rounded-control file:border file:border-border file:bg-surface-2 file:px-3 file:py-2"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            submit.clear();
          }}
          aria-invalid={attempted && !!error}
          aria-describedby="statement-file-erro"
        />
        {attempted && error && <p id="statement-file-erro" role="alert" className="text-caption text-loss">{error}</p>}
        {submit.error && <p role="alert" className="text-caption text-loss">{submit.error}</p>}
        {mode === "demo" && <p className="text-caption text-warn">Demonstração: o arquivo não sai do navegador e nenhuma linha é lida.</p>}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onDone} disabled={submit.pending}>Cancelar</Button>
        <Button onClick={() => void onSubmit()} disabled={submit.pending}>{submit.pending ? "Importando…" : "Importar extrato"}</Button>
      </div>
    </>
  );
}
