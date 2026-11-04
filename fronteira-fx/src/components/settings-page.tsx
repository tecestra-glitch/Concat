"use client";
import { useSettings } from "@/lib/settings";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { API_BASE, modeConflict } from "@/lib/api/client";
import { capitalOptions } from "@/lib/api/capitals";
import { useBackendHealth } from "@/lib/queries";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { MODE_LABEL, MODE_TONE } from "@/components/ui/labels";
import { useLive } from "@/lib/live";
import { formatMoney } from "@/lib/format";
import { NetGainAlertCard } from "./settings/net-gain-card";
import { PremissasCard } from "./settings/premissas-card";

const MODE_HELP: Record<string, string> = {
  auto: "Segue o modo do backend quando ele responde; demonstração enquanto não houver API.",
  real: "Cotações e operações do backend real; nada é inventado nem misturado.",
  simulation: "Exige um backend à parte em DATA_MODE=simulation: o que for gravado ali nunca toca os dados reais.",
  demo: "Dados ilustrativos isolados; nenhuma cotação é atual ou executável.",
};
const BACKEND_LABEL = { unknown: "verificando", available: "disponível", unavailable: "indisponível" } as const;
const BACKEND_TONE: Record<string, BadgeVariant> = { unknown: "outline", available: "gain", unavailable: "loss" };
const STREAM_LABEL = { connected: "conectado", reconnecting: "reconectando", offline: "offline", demo: "demonstração" } as const;

export function SettingsPage() {
  const { settings, update, mode, backend } = useSettings();
  const health = useBackendHealth();
  const live = useLive();
  const capitals = capitalOptions(mode, settings.defaultCapital);
  // SEC-01: any mismatch counts, simulation included; the backend refuses those calls (409).
  const conflict = !!health.data && modeConflict(mode, health.data.data_mode);
  return (
    <div className="space-y-4">
      <PageHeader title="Configurações" description="Modo de dados, orçamento padrão e moeda de avaliação. Segredos do backend nunca ficam no navegador." />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Modo de dados</CardTitle><CardDescription>Real, simulação (instância à parte) e demonstração isolada não se misturam.</CardDescription></CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="mode">Preferência</Label>
              <Select value={settings.modePreference} onValueChange={(v) => update({ modePreference: v as typeof settings.modePreference })}>
                <SelectTrigger id="mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Automático</SelectItem>
                  <SelectItem value="real">Real</SelectItem>
                  <SelectItem value="simulation">Simulação</SelectItem>
                  <SelectItem value="demo">Demonstração</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted" id="mode-help">{MODE_HELP[settings.modePreference]}</p>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted">Modo efetivo</dt><dd><Badge variant={MODE_TONE[mode]} data-testid="effective-mode">{MODE_LABEL[mode]}</Badge></dd>
              <dt className="text-muted">Backend</dt><dd className="flex flex-wrap items-center gap-2"><Badge variant={BACKEND_TONE[backend]} data-testid="backend-status">{BACKEND_LABEL[backend]}</Badge><span className="tnum truncate text-xs text-muted">{API_BASE}</span></dd>
              <dt className="text-muted">Saúde da API</dt>
              <dd>
                {health.isLoading ? <Badge variant="outline">verificando…</Badge> : health.data ? <Badge variant={conflict ? "warn" : "gain"}>{health.data.status} · {MODE_LABEL[health.data.data_mode] ?? health.data.data_mode}{health.data.version ? ` · v${health.data.version}` : ""}</Badge> : <Badge variant="outline">não conectada</Badge>}
                {conflict && <p className="mt-1 text-xs text-warn" data-testid="mode-conflict">O backend está em modo «{MODE_LABEL[health.data!.data_mode]}», diferente do modo «{MODE_LABEL[mode]}» pedido: as chamadas são recusadas (409) para não misturar dados. Escolha «Automático» ou aponte para uma instância nesse modo.</p>}
              </dd>
              <dt className="text-muted">Stream</dt><dd><Badge variant="outline">{STREAM_LABEL[live.state]}</Badge></dd>
            </dl>
            <p className="text-xs text-muted">A chave da API fica só no servidor (proxy em {API_BASE}); o navegador nunca a recebe.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Simulação</CardTitle><CardDescription>Valores padrão para o simulador e os rankings.</CardDescription></CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="cap">Orçamento padrão</Label>
              <Select value={String(settings.defaultCapital)} onValueChange={(v) => update({ defaultCapital: Number(v) })}>
                <SelectTrigger id="cap"><SelectValue /></SelectTrigger>
                <SelectContent>{capitals.map((c) => <SelectItem key={c} value={String(c)}>{formatMoney(c, "BRL")}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="val">Moeda de avaliação</Label>
              <Select value={settings.valuationCurrency} onValueChange={(v) => update({ valuationCurrency: v as typeof settings.valuationCurrency })}>
                <SelectTrigger id="val"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="BRL">BRL</SelectItem><SelectItem value="USD">USD</SelectItem><SelectItem value="PYG">PYG</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="poll">Fallback de snapshot</Label>
              <Select value={String(settings.pollFallbackSeconds)} onValueChange={(v) => update({ pollFallbackSeconds: Number(v) })}>
                <SelectTrigger id="poll"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="30">30 s</SelectItem><SelectItem value="60">60 s</SelectItem><SelectItem value="120">120 s</SelectItem></SelectContent>
              </Select>
              <p className="text-xs text-muted">Só é usado enquanto o stream estiver caído.</p>
            </div>
          </CardContent>
        </Card>
        <NetGainAlertCard />
      </div>
      <PremissasCard />
    </div>
  );
}
