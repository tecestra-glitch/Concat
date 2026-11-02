"use client";
import { useSettings } from "@/lib/settings";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { API_URL } from "@/lib/api/client";
import { useBackendHealth } from "@/lib/queries";
import { Badge } from "@/components/ui/badge";
import { useLive } from "@/lib/live";

export function SettingsPage() {
  const { settings, update, mode } = useSettings();
  const health = useBackendHealth();
  const live = useLive();
  return (
    <div className="space-y-4">
      <PageHeader title="Configurações" description="Modo de dados, orçamento padrão e moeda de avaliação. Segredos do backend nunca ficam no navegador." />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Modo de dados</CardTitle><CardDescription>Monitoramento real, simulação sobre dados reais e demonstração isolada não se misturam.</CardDescription></CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="mode">Preferência</Label>
              <Select value={settings.modePreference} onValueChange={(v) => update({ modePreference: v as typeof settings.modePreference })}>
                <SelectTrigger id="mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Automático (real se API configurada)</SelectItem>
                  <SelectItem value="real">Real (exige API)</SelectItem>
                  <SelectItem value="demo">Demonstração</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-muted">Modo efetivo</dt><dd><Badge variant={mode === "demo" ? "warn" : "gain"}>{mode === "demo" ? "demonstração" : "real"}</Badge></dd>
              <dt className="text-muted">API</dt><dd className="tnum truncate text-xs">{API_URL || "não configurada (NEXT_PUBLIC_API_URL)"}</dd>
              <dt className="text-muted">Saúde da API</dt><dd>{health.data ? <Badge variant="gain">{health.data.status} · {health.data.data_mode}</Badge> : <Badge variant="outline">não conectada</Badge>}</dd>
              <dt className="text-muted">Stream</dt><dd><Badge variant="outline">{live.state}</Badge></dd>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Simulação</CardTitle><CardDescription>Valores padrão para o simulador e os rankings.</CardDescription></CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="cap">Orçamento padrão</Label>
              <Select value={String(settings.defaultCapital)} onValueChange={(v) => update({ defaultCapital: Number(v) })}>
                <SelectTrigger id="cap"><SelectValue /></SelectTrigger>
                <SelectContent>{[5000, 10000, 25000, 50000].map((c) => <SelectItem key={c} value={String(c)}>R$ {c.toLocaleString("pt-BR")}</SelectItem>)}</SelectContent>
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
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
