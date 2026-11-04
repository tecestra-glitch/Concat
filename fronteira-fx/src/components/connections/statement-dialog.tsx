"use client";
/**
 * Importação de extrato CSV/OFX. A tela checa extensão, tamanho e o mapeamento de colunas do CSV; o conteúdo é dado
 * não confiável e é lido pelo servidor. Em demonstração nada sai do navegador.
 */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { CSV_DATE_FORMATS, CSV_DELIMITERS, statementFormat, type CsvMapping } from "@/lib/api/connections";
import type { CatalogInstitution } from "@/lib/api/connections-catalog";
import type { Mode } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { useSubmitState } from "@/components/ui/use-submit";
import { statementFileError } from "./connections-form";

const DELIMITER_LABEL: Record<(typeof CSV_DELIMITERS)[number], string> = { ",": "Vírgula (,)", ";": "Ponto e vírgula (;)", "\t": "Tabulação" };

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
  const [mapping, setMapping] = React.useState<CsvMapping>({ date: "Data", description: "Descrição", amount: "Valor", currency: null, date_format: "%d/%m/%Y", delimiter: "," });
  const submit = useSubmitState();
  const error = statementFileError(file);
  const isCsv = file ? statementFormat(file.name) === "csv" : false;
  const mappingError = isCsv && (!mapping.date.trim() || !mapping.description.trim() || !mapping.amount.trim()) ? "Informe o nome das colunas de data, descrição e valor." : null;

  const onSubmit = async () => {
    setAttempted(true);
    if (!file || error || mappingError) return;
    const ok = await submit.run(async () => {
      await api.importStatement(mode, inst.id, `${inst.name} extrato`, file, isCsv ? { ...mapping, date: mapping.date.trim(), description: mapping.description.trim(), amount: mapping.amount.trim() } : null);
      await qc.invalidateQueries({ queryKey: ["connections", mode] });
    }, "Não foi possível importar o extrato.");
    if (ok) onDone();
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Importar extrato: {inst.name}</DialogTitle>
        <DialogDescription>Envie um arquivo CSV ou OFX exportado pela instituição. Até 512 KB. O servidor lê as linhas; esta tela não interpreta o conteúdo.</DialogDescription>
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

      {isCsv && (
        <fieldset className="grid gap-3 rounded-control border border-border p-3" data-testid="statement-mapping">
          <legend className="px-1 text-caption text-muted">Como ler o CSV (nomes das colunas no arquivo)</legend>
          <div className="grid gap-1.5">
            <Label htmlFor="map-data">Coluna da data</Label>
            <Input id="map-data" value={mapping.date} onChange={(e) => setMapping({ ...mapping, date: e.target.value })} maxLength={64} aria-invalid={attempted && !mapping.date.trim()} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="map-desc">Coluna da descrição</Label>
            <Input id="map-desc" value={mapping.description} onChange={(e) => setMapping({ ...mapping, description: e.target.value })} maxLength={64} aria-invalid={attempted && !mapping.description.trim()} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="map-amount">Coluna do valor</Label>
            <Input id="map-amount" value={mapping.amount} onChange={(e) => setMapping({ ...mapping, amount: e.target.value })} maxLength={64} aria-invalid={attempted && !mapping.amount.trim()} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="map-date-format">Formato da data</Label>
            <select id="map-date-format" className="h-10 rounded-control border border-border bg-surface px-3 text-body" value={mapping.date_format} onChange={(e) => setMapping({ ...mapping, date_format: e.target.value as CsvMapping["date_format"] })}>
              {CSV_DATE_FORMATS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="map-delimiter">Separador</Label>
            <select id="map-delimiter" className="h-10 rounded-control border border-border bg-surface px-3 text-body" value={mapping.delimiter} onChange={(e) => setMapping({ ...mapping, delimiter: e.target.value as CsvMapping["delimiter"] })}>
              {CSV_DELIMITERS.map((d) => (
                <option key={d} value={d}>{DELIMITER_LABEL[d]}</option>
              ))}
            </select>
          </div>
          {attempted && mappingError && <p role="alert" className="text-caption text-loss">{mappingError}</p>}
        </fieldset>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onDone} disabled={submit.pending}>Cancelar</Button>
        <Button onClick={() => void onSubmit()} disabled={submit.pending}>{submit.pending ? "Importando…" : "Importar extrato"}</Button>
      </div>
    </>
  );
}
