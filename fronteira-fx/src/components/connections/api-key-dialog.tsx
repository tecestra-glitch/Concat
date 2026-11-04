"use client";
/**
 * Diálogo de chave de API só leitura. Decisão de segurança: o SEGREDO usa `type="password"`, porque a máscara por CSS
 * (`-webkit-text-security`) não é garantida em todos os navegadores e deixaria o segredo em claro. Por isso o app tem,
 * além do login, este campo de segredo (e só ele): nenhum campo de senha de banco existe. A chave pública fica em texto
 * mascarado por CSS. Nada disso é guardado: depois de salvar a tela só mantém os últimos 4 caracteres. A chave é
 * validada no servidor antes de salvar, e uma chave que pode operar ou sacar é recusada.
 */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { apiKeyRefusal, type ApiKeyValidation } from "@/lib/api/connections";

import type { CatalogInstitution } from "@/lib/api/connections-catalog";
import type { Mode } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { useSubmitState } from "@/components/ui/use-submit";
import { EMPTY_API_KEY_FORM, hasApiKeyErrors, validateApiKeyForm, type ApiKeyForm } from "./connections-form";

export const API_KEY_STEPS = [
  "Entre no site ou no app oficial da instituição. Não use link recebido por mensagem.",
  "Abra a área de chaves de API (costuma ficar em configurações de segurança ou de API).",
  "Crie uma chave nova. Dê um nome que lembre o Fronteira FX.",
  "Marque somente leitura (por exemplo: ler saldo e histórico). Deixe DESMARCADOS operar, negociar, trocar, sacar e transferir.",
  "Se a instituição pedir restrição de IP, restrinja se puder.",
  "Copie a chave e o segredo e cole aqui. Nunca cole sua senha de login.",
];

export function ApiKeyDialog({ open, onOpenChange, inst, mode }: { open: boolean; onOpenChange: (o: boolean) => void; inst: CatalogInstitution | null; mode: Mode }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        {inst && <ApiKeyForm key={inst.id} inst={inst} mode={mode} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function ApiKeyForm({ inst, mode, onDone }: { inst: CatalogInstitution; mode: Mode; onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = React.useState<ApiKeyForm>(EMPTY_API_KEY_FORM);
  const [attempted, setAttempted] = React.useState(false);
  const [validation, setValidation] = React.useState<ApiKeyValidation | null>(null);
  const validate = useSubmitState();
  const save = useSubmitState();
  const errors = validateApiKeyForm(form);
  const refusal = validation ? apiKeyRefusal(validation) : null;
  const canSave = validation !== null && refusal === null && !hasApiKeyErrors(errors);
  const showErr = (k: keyof ApiKeyForm) => (attempted ? errors[k] : undefined);

  const update = (patch: Partial<ApiKeyForm>) => {
    setForm((f) => ({ ...f, ...patch }));
    setValidation(null);
    validate.clear();
  };

  const onValidate = async () => {
    setAttempted(true);
    if (hasApiKeyErrors(errors)) return;
    await validate.run(async () => {
      setValidation(await api.validateApiKey(mode, { institution: inst.id, api_key: form.apiKey.trim(), api_secret: form.apiSecret.trim() }));
    }, "Não foi possível validar a chave.");
  };

  const onSave = async () => {
    if (!canSave) return;
    const ok = await save.run(async () => {
      await api.createApiKeyConnection(mode, { institution: inst.id, label: `${inst.name} leitura`, api_key: form.apiKey.trim(), api_secret: form.apiSecret.trim() });
      await qc.invalidateQueries({ queryKey: ["connections", mode] });
    }, "Não foi possível salvar a conexão.");
    if (ok) {
      // Limpa os campos antes de fechar: o segredo não fica em memória de tela.
      setForm(EMPTY_API_KEY_FORM);
      onDone();
    }
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Chave de API só leitura: {inst.name}</DialogTitle>
        <DialogDescription>O Fronteira FX nunca pede a senha do seu banco. Use só a chave e o segredo criados na área de API.</DialogDescription>
      </DialogHeader>

      <ol className="list-decimal space-y-1.5 pl-5 text-caption text-muted" data-testid="api-key-steps">
        {API_KEY_STEPS.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>

      <form className="grid gap-3" noValidate onSubmit={(e) => e.preventDefault()}>
        <div className="grid gap-1.5">
          <Label htmlFor="api-key-chave">Chave de API</Label>
          <Input
            id="api-key-chave"
            name="api-key"
            type="text"
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            value={form.apiKey}
            onChange={(e) => update({ apiKey: e.target.value })}
            aria-invalid={!!showErr("apiKey")}
            aria-describedby="api-key-chave-erro"
            className="fx-mask font-mono"
          />
          {showErr("apiKey") && <p id="api-key-chave-erro" role="alert" className="text-caption text-loss">{showErr("apiKey")}</p>}
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="api-key-segredo">Segredo da API</Label>
          <Input
            id="api-key-segredo"
            name="api-secret"
            type="password"
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            data-lpignore="true"
            data-1p-ignore="true"
            data-bwignore="true"
            data-form-type="other"
            value={form.apiSecret}
            onChange={(e) => update({ apiSecret: e.target.value })}
            aria-invalid={!!showErr("apiSecret")}
            aria-describedby="api-key-segredo-erro"
            className="font-mono"
          />
          {showErr("apiSecret") && <p id="api-key-segredo-erro" role="alert" className="text-caption text-loss">{showErr("apiSecret")}</p>}
          <p className="text-caption text-muted">O segredo fica oculto pelo próprio navegador e não é mostrado de volta depois de salvo.</p>
        </div>

        <label className="flex items-start gap-2 text-body">
          <input
            type="checkbox"
            className="mt-1 size-4 accent-accent"
            checked={form.readOnlyConfirmed}
            onChange={(e) => update({ readOnlyConfirmed: e.target.checked })}
            aria-invalid={!!showErr("readOnlyConfirmed")}
            aria-describedby="api-key-confirmacao-erro"
          />
          <span>Criei esta chave só com leitura. Operar e sacar estão desmarcados.</span>
        </label>
        {showErr("readOnlyConfirmed") && <p id="api-key-confirmacao-erro" role="alert" className="text-caption text-loss">{showErr("readOnlyConfirmed")}</p>}

        {validation && refusal === null && (
          <div role="status" className="rounded-control border border-gain/40 bg-gain/10 p-3 text-caption" data-testid="api-key-ok">
            <p className="font-medium">Chave aprovada: só leitura.</p>
            <ul className="mt-1 grid gap-0.5 text-muted">
              <li>Leitura: sim</li>
              <li>Operar: não</li>
              <li>Sacar: não</li>
            </ul>
          </div>
        )}
        {refusal && (
          <p role="alert" className="rounded-control border border-loss/40 bg-loss/10 p-3 text-caption text-loss" data-testid="api-key-refused">
            Chave recusada. {refusal}
          </p>
        )}
        {validate.error && <p role="alert" className="text-caption text-loss">{validate.error}</p>}
        {save.error && <p role="alert" className="text-caption text-loss">{save.error}</p>}
      </form>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onDone} disabled={save.pending}>Cancelar</Button>
        <Button variant="secondary" onClick={() => void onValidate()} disabled={validate.pending || save.pending}>
          {validate.pending ? "Validando…" : "Validar chave"}
        </Button>
        <Button onClick={() => void onSave()} disabled={!canSave || save.pending}>
          {save.pending ? "Salvando…" : "Salvar conexão"}
        </Button>
      </div>
    </>
  );
}
