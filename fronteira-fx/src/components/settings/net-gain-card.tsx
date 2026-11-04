"use client";
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { api } from "@/lib/api/client";
import { formatThreshold, watchApi, type AlertRule, type AlertRuleInput } from "@/lib/api/watch";
import { useSettings } from "@/lib/settings";
import { useAlertRules } from "@/components/monitor/use-watch";
import { watchKeys } from "@/components/monitor/use-watch";
import { findNetGainRule, netGainFormFromRule, netGainRuleFromForm, NET_GAIN_COOLDOWN_S, type NetGainCurrency, type NetGainForm } from "./net-gain-alert";

/** Limite do alerta de ganho líquido por ciclo: uma regra só, na moeda escolhida. Nunca dispara com custo incompleto. */
export function NetGainAlertCard() {
  const rules = useAlertRules();
  // O aviso de «salvo» fica aqui: o formulário é recriado quando a regra chega do servidor.
  const [notice, setNotice] = React.useState<string | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Alerta de oportunidade</CardTitle>
        <CardDescription>Avisa quando um ciclo tiver ganho líquido igual ou acima do limite, na moeda que você escolher. Ciclos com custo não informado nunca disparam.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {rules.isLoading ? (
          <TableSkeleton rows={2} cols={2} />
        ) : rules.isError ? (
          <ErrorState title="As regras de alerta não carregaram" error={rules.error} onRetry={() => void rules.refetch()} />
        ) : (
          <NetGainFormFields key={findNetGainRule(rules.data)?.id ?? "nova"} rule={findNetGainRule(rules.data)} onSaved={() => setNotice("Limite salvo.")} onEdit={() => setNotice(null)} />
        )}
        {notice && <p role="status" className="text-xs text-gain">{notice}</p>}
      </CardContent>
    </Card>
  );
}

function NetGainFormFields({ rule, onSaved, onEdit }: { rule: AlertRule | undefined; onSaved: () => void; onEdit: () => void }) {
  const { mode } = useSettings();
  const qc = useQueryClient();
  const [form, setForm] = React.useState<NetGainForm>(() => netGainFormFromRule(rule));
  const [error, setError] = React.useState<string | null>(null);
  const save = useMutation({
    mutationFn: (input: AlertRuleInput) =>
      rule
        ? // PATCH: só o que muda; o tipo e o canal da regra não são reenviados.
          api.updateRule(mode, rule.id, { name: input.name, threshold: input.threshold, params: input.params, enabled: input.enabled })
        : watchApi.createRule(mode, input),
    onSuccess: () => {
      onSaved();
      void qc.invalidateQueries({ queryKey: watchKeys.rules(mode) });
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Não foi possível salvar o limite."),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onEdit();
    const r = netGainRuleFromForm(form);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    setError(null);
    save.mutate(r.input);
  };

  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={submit} aria-label="Limite do alerta de ganho líquido">
      <div className="grid gap-1 sm:col-span-2">
        <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="net-gain-status">
          {rule ? (
            <>
              <Badge variant={rule.enabled ? "gain" : "outline"}>{rule.enabled ? "Ligado" : "Desligado"}</Badge>
              <span>
                Aviso quando o ganho líquido for de pelo menos <span className="tnum font-semibold">{formatThreshold("cycle_net_gain", rule.threshold, rule.params?.currency)}</span>.
              </span>
            </>
          ) : (
            <Badge variant="outline">Sem limite</Badge>
          )}
        </p>
      </div>
      <div className="grid gap-1">
        <Label htmlFor="ng-currency">Moeda do limite</Label>
        <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v as NetGainCurrency })}>
          <SelectTrigger id="ng-currency" aria-label="Moeda do limite"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="BRL">BRL (real)</SelectItem>
            <SelectItem value="USD">USD (dólar)</SelectItem>
            <SelectItem value="PYG">PYG (guarani)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-1">
        <Label htmlFor="ng-threshold">Ganho líquido mínimo</Label>
        <Input id="ng-threshold" inputMode="decimal" placeholder="ex.: 20 ou 1.250,50" value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} autoComplete="off" aria-describedby="ng-help" />
      </div>
      <div className="flex items-center justify-between gap-2 sm:col-span-2">
        <Label htmlFor="ng-enabled" className="text-foreground">Alerta ligado</Label>
        <Switch id="ng-enabled" checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
      </div>
      <p id="ng-help" className="text-xs text-muted sm:col-span-2">
        Vale o valor líquido, depois de tarifas, IOF, spread e deslocamento. Repete no máximo a cada {NET_GAIN_COOLDOWN_S / 60} min. Se a conta não convertir para a moeda escolhida, o aviso não dispara.
      </p>
      {error && <p role="alert" className="text-xs text-loss sm:col-span-2">{error}</p>}
      <div className="sm:col-span-2">
        <Button type="submit" disabled={save.isPending}>{save.isPending ? "Salvando…" : rule ? "Salvar limite" : "Criar limite"}</Button>
      </div>
    </form>
  );
}
