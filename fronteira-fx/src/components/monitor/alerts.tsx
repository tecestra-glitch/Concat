"use client";
/**
 * Alertas (módulo notify): regras avaliadas sobre o stream e histórico de envios por canal.
 * Em modo demonstração as regras criadas/alteradas vivem só no estado deste componente e nada é enviado.
 */
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BellRing, Plus, Send } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Input, Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useSettings } from "@/lib/settings";
import { formatAge, formatDateTime } from "@/lib/format";
import { CITY_LABEL } from "@/lib/api/types";
import {
  ALERT_CHANNELS,
  ALERT_CHANNEL_LABEL,
  ALERT_KINDS,
  ALERT_KIND_LABEL,
  ALERT_PAIRS,
  formatClock,
  formatInterval,
  formatThreshold,
  isRatioKind,
  validateTarget,
  validateThreshold,
  watchApi,
  type AlertChannel,
  type AlertEvent,
  type AlertKind,
  type AlertRule,
  type AlertRuleInput,
} from "@/lib/api/watch";
import { cn } from "@/lib/utils";
import { useAlertEvents, useAlertRules, watchKeys } from "./use-watch";
import { useTicker } from "./use-ticker";

const COOLDOWNS = [60, 300, 600, 1800, 3600];

const TARGET_HELP: Record<Exclude<AlertChannel, "ui">, { label: string; placeholder: string; help: string }> = {
  telegram: { label: "Chat do Telegram", placeholder: "123456789 ou @canal", help: "chat_id numérico ou @canal. O token do bot fica só no backend, por variável de ambiente." },
  webhook: { label: "URL do webhook", placeholder: "https://…", help: "Receberá um POST JSON com o AlertEvent. Use https sempre que possível." },
  email: { label: "E-mail de destino", placeholder: "voce@exemplo.com", help: "O SMTP é configurado só no backend; nada de credenciais no navegador." },
};

export function Alerts() {
  const { mode } = useSettings();
  const qc = useQueryClient();
  const rulesQ = useAlertRules();
  const eventsQ = useAlertEvents({});
  // Demo mode: created rules, edited rules and test events live only here (nothing is persisted or sent).
  const [localRules, setLocalRules] = React.useState<AlertRule[]>([]);
  const [overrides, setOverrides] = React.useState<Record<string, AlertRule>>({});
  const [localEvents, setLocalEvents] = React.useState<AlertEvent[]>([]);

  const rules = React.useMemo(() => [...localRules, ...(rulesQ.data ?? [])].map((r) => overrides[r.id] ?? r), [localRules, rulesQ.data, overrides]);
  const events = React.useMemo(() => [...localEvents, ...(eventsQ.data ?? [])], [localEvents, eventsQ.data]);
  const ruleName = React.useCallback((id: string) => rules.find((r) => r.id === id)?.name ?? id, [rules]);

  const create = useMutation({
    mutationFn: (input: AlertRuleInput) => watchApi.createRule(mode, input),
    onSuccess: (rule) => {
      if (mode === "demo") setLocalRules((l) => [rule, ...l]);
      else void qc.invalidateQueries({ queryKey: watchKeys.rules(mode) });
    },
  });
  const update = useMutation({
    mutationFn: ({ rule, patch }: { rule: AlertRule; patch: Partial<AlertRuleInput> }) => watchApi.updateRule(mode, rule, patch),
    onMutate: ({ rule, patch }) => setOverrides((o) => ({ ...o, [rule.id]: { ...rule, ...patch } })),
    onSuccess: (saved) => {
      if (mode === "demo") return;
      qc.setQueryData<AlertRule[]>(watchKeys.rules(mode), (old) => old?.map((r) => (r.id === saved.id ? saved : r)));
      setOverrides((o) => {
        const next = { ...o };
        delete next[saved.id];
        return next;
      });
    },
    onError: (_e, { rule }) =>
      setOverrides((o) => {
        const next = { ...o };
        delete next[rule.id];
        return next;
      }),
  });
  const test = useMutation({
    mutationFn: (rule: AlertRule) => watchApi.testRule(mode, rule),
    onSuccess: (ev) => {
      if (mode === "demo") setLocalEvents((l) => [ev, ...l]);
      else void qc.invalidateQueries({ queryKey: ["alerts", "events"] });
    },
  });

  const enabled = rules.filter((r) => r.enabled).length;
  return (
    <div className="space-y-4">
      <PageHeader title="Alertas" description="Regras avaliadas sobre o stream (ROI de ciclo, movimento de cotação, fonte fora do ar, nova oportunidade) e o histórico de envios por canal.">
        <NewRuleDialog onCreate={(input) => create.mutate(input)} pending={create.isPending} />
      </PageHeader>
      {mode === "demo" && (
        <p role="note" data-testid="alerts-demo-note" className="text-xs text-warn">
          Demonstração: regras e testes ficam só nesta sessão e nenhuma mensagem é enviada.
        </p>
      )}
      {create.isError && <p role="alert" className="text-sm text-loss">Falha ao criar regra: {(create.error as Error).message}</p>}
      {update.isError && <p role="alert" className="text-sm text-loss">Falha ao atualizar regra: {(update.error as Error).message}</p>}
      {test.isError && <p role="alert" className="text-sm text-loss">Falha ao testar regra: {(test.error as Error).message}</p>}

      <Card data-testid="alert-rules">
        <CardHeader className="flex-row items-start justify-between gap-2">
          <div>
            <CardTitle>Regras</CardTitle>
            <CardDescription>Limites em percentual (ratio) ou minutos; o cooldown evita repetir o mesmo alerta em sequência.</CardDescription>
          </div>
          <Badge variant={enabled ? "gain" : "outline"}>{enabled} ativa{enabled === 1 ? "" : "s"}</Badge>
        </CardHeader>
        <CardContent className="p-2 sm:p-2">
          {rulesQ.isLoading ? (
            <Skeleton className="h-32" />
          ) : rulesQ.isError ? (
            <p role="alert" className="p-4 text-sm text-loss">Falha ao carregar regras: {(rulesQ.error as Error).message}</p>
          ) : (
            <RuleList rules={rules} onToggle={(rule, on) => update.mutate({ rule, patch: { enabled: on } })} onTest={(rule) => test.mutate(rule)} testingId={test.isPending ? test.variables?.id : undefined} />
          )}
        </CardContent>
      </Card>

      <Card data-testid="alert-events">
        <CardHeader>
          <CardTitle>Eventos</CardTitle>
          <CardDescription>Cada disparo registra canal, entrega e mensagem. Falhas de entrega ficam visíveis com o erro do canal.</CardDescription>
        </CardHeader>
        <CardContent>
          {eventsQ.isLoading && <Skeleton className="h-32" />}
          {eventsQ.isError && <p role="alert" className="text-sm text-loss">Falha ao carregar eventos: {(eventsQ.error as Error).message}</p>}
          {!eventsQ.isLoading && !eventsQ.isError && <EventList events={events} ruleName={ruleName} />}
        </CardContent>
      </Card>
    </div>
  );
}

function KindBadge({ kind }: { kind: AlertKind }) {
  const tone: Record<AlertKind, "accent" | "warn" | "loss" | "gain"> = { cycle_roi: "gain", quote_move: "accent", source_down: "loss", opportunity_new: "warn" };
  return <Badge variant={tone[kind] ?? "outline"}>{ALERT_KIND_LABEL[kind] ?? kind}</Badge>;
}

function ChannelBadge({ channel }: { channel: AlertChannel }) {
  return <Badge variant="outline">{ALERT_CHANNEL_LABEL[channel] ?? channel}</Badge>;
}

function paramsText(r: AlertRule): string {
  if (!r.params) return "—";
  const parts: string[] = [];
  if (r.params.pair) parts.push(r.params.pair);
  if (r.params.city !== undefined) parts.push(r.params.city ? (CITY_LABEL as Record<string, string>)[r.params.city] ?? r.params.city : "Digital");
  return parts.join(" · ") || "—";
}

interface RuleListProps {
  rules: AlertRule[];
  onToggle: (rule: AlertRule, on: boolean) => void;
  onTest: (rule: AlertRule) => void;
  testingId?: string;
}

/** Table from `md` up, cards below. */
function RuleList({ rules, onToggle, onTest, testingId }: RuleListProps) {
  if (rules.length === 0) return <p className="p-4 text-center text-sm text-muted">Nenhuma regra. Crie a primeira em «Nova regra».</p>;
  return (
    <>
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Regra</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead className="text-right">Limite</TableHead>
              <TableHead>Parâmetros</TableHead>
              <TableHead>Canal</TableHead>
              <TableHead className="text-right">Cooldown</TableHead>
              <TableHead>Ativa</TableHead>
              <TableHead><span className="sr-only">Ações</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rules.map((r) => (
              <TableRow key={r.id} data-testid="alert-rule" data-rule={r.id} className={cn(!r.enabled && "opacity-70")}>
                <TableCell className="font-medium">{r.name}</TableCell>
                <TableCell><KindBadge kind={r.kind} /></TableCell>
                <TableCell className="tnum text-right">{formatThreshold(r.kind, r.threshold)}</TableCell>
                <TableCell className="text-xs text-muted">{paramsText(r)}</TableCell>
                <TableCell>
                  <div className="flex flex-col gap-0.5">
                    <ChannelBadge channel={r.channel} />
                    {r.target && <span className="tnum max-w-[14rem] truncate text-[11px] text-muted" title={r.target}>{r.target}</span>}
                  </div>
                </TableCell>
                <TableCell className="tnum text-right">{formatInterval(r.cooldown_s)}</TableCell>
                <TableCell><Switch checked={r.enabled} aria-label={`Ativar regra ${r.name}`} onCheckedChange={(on) => onToggle(r, on)} /></TableCell>
                <TableCell className="text-right">
                  <Button type="button" size="sm" variant="secondary" disabled={testingId === r.id} aria-label={`Testar: ${r.name}`} onClick={() => onTest(r)}>
                    <Send aria-hidden /> {testingId === r.id ? "Enviando…" : "Testar"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="grid gap-2 md:hidden" aria-label="Regras de alerta">
        {rules.map((r) => (
          <li key={r.id} data-testid="alert-rule" data-rule={r.id} className={cn("rounded-md border border-border bg-surface p-3 text-sm", !r.enabled && "opacity-70")}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium">{r.name}</p>
                <div className="mt-1 flex flex-wrap gap-1"><KindBadge kind={r.kind} /><ChannelBadge channel={r.channel} /></div>
              </div>
              <Switch checked={r.enabled} aria-label={`Ativar regra ${r.name}`} onCheckedChange={(on) => onToggle(r, on)} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
              <div><dt className="text-muted">Limite</dt><dd className="tnum">{formatThreshold(r.kind, r.threshold)}</dd></div>
              <div><dt className="text-muted">Cooldown</dt><dd className="tnum">{formatInterval(r.cooldown_s)}</dd></div>
              <div><dt className="text-muted">Parâmetros</dt><dd>{paramsText(r)}</dd></div>
              <div className="min-w-0"><dt className="text-muted">Destino</dt><dd className="tnum truncate" title={r.target ?? undefined}>{r.target ?? "—"}</dd></div>
            </dl>
            <div className="mt-3 flex justify-end">
              <Button type="button" size="sm" variant="secondary" disabled={testingId === r.id} aria-label={`Testar: ${r.name}`} onClick={() => onTest(r)}>
                <Send aria-hidden /> {testingId === r.id ? "Enviando…" : "Testar"}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function DeliveredBadge({ e }: { e: AlertEvent }) {
  if (e.delivered) return <Badge variant="gain">entregue</Badge>;
  return <Badge variant={e.error?.startsWith("demonstração") || e.error === "regra desativada" ? "outline" : "loss"}>{e.error?.startsWith("demonstração") ? "não enviado" : "falhou"}</Badge>;
}

function EventList({ events, ruleName }: { events: AlertEvent[]; ruleName: (id: string) => string }) {
  const now = useTicker();
  if (events.length === 0) return <p className="py-6 text-center text-sm text-muted">Nenhum alerta disparado ainda.</p>;
  return (
    <ol aria-live="polite" aria-relevant="additions" aria-label="Eventos de alerta" className="divide-y divide-border">
      {events.map((e) => (
        <li key={e.id} data-testid="alert-event" className="grid gap-x-4 gap-y-1 py-2.5 text-sm sm:grid-cols-[9.5rem_1fr]">
          <time dateTime={e.ts} title={formatDateTime(e.ts)} className="tnum text-xs text-muted">
            {formatClock(e.ts)} <span aria-hidden>·</span> {now === 0 ? "…" : formatAge(e.ts, now)}
          </time>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{ruleName(e.rule_id)}</span>
              <ChannelBadge channel={e.channel} />
              <DeliveredBadge e={e} />
            </div>
            <p className="break-words text-foreground/90">{e.message}</p>
            {e.error && !e.delivered && <p className="text-xs text-muted">{e.error}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------------------------
// Create rule dialog
// ---------------------------------------------------------------------------------------------

interface RuleForm {
  name: string;
  kind: AlertKind;
  threshold: string;
  pair: string;
  city: string;
  channel: AlertChannel;
  target: string;
  cooldown: string;
}

const EMPTY_FORM: RuleForm = { name: "", kind: "cycle_roi", threshold: "", pair: "USD/PYG", city: "CDE", channel: "ui", target: "", cooldown: "600" };

function NewRuleDialog({ onCreate, pending }: { onCreate: (input: AlertRuleInput) => void; pending: boolean }) {
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState<RuleForm>(EMPTY_FORM);
  const set = <K extends keyof RuleForm>(k: K, v: RuleForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  const nameOk = form.name.trim().length >= 3;
  const th = validateThreshold(form.kind, form.threshold);
  const tg = validateTarget(form.channel, form.target);
  const valid = nameOk && th.ok && tg.ok;
  const ratio = isRatioKind(form.kind);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!th.ok || !tg.ok || !nameOk) return;
    onCreate({
      name: form.name.trim(),
      kind: form.kind,
      threshold: th.value,
      params: form.kind === "quote_move" ? { pair: form.pair, city: form.city === "digital" ? null : form.city } : null,
      channel: form.channel,
      target: tg.value,
      cooldown_s: Number(form.cooldown),
      enabled: true,
    });
    setOpen(false);
    setForm(EMPTY_FORM);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setForm(EMPTY_FORM); }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus aria-hidden /> Nova regra</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><BellRing className="size-4 text-accent" aria-hidden /> Nova regra de alerta</DialogTitle>
          <DialogDescription>Defina o gatilho, o limite e o canal. Segredos de canal (token, SMTP) nunca passam pelo navegador.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3" noValidate>
          <div className="grid gap-1">
            <Label htmlFor="rule-name">Nome</Label>
            <Input id="rule-name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="ex.: ciclo acima de 0,2 %" aria-invalid={form.name !== "" && !nameOk} aria-describedby="rule-name-help" required />
            <p id="rule-name-help" className="text-xs text-muted">Pelo menos 3 caracteres; aparece na mensagem enviada.</p>
            {form.name !== "" && !nameOk && <p role="alert" className="text-xs text-loss">Dê um nome com pelo menos 3 caracteres.</p>}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1">
              <Label htmlFor="rule-kind">Tipo</Label>
              <Select value={form.kind} onValueChange={(v) => set("kind", v as AlertKind)}>
                <SelectTrigger id="rule-kind"><SelectValue /></SelectTrigger>
                <SelectContent>{ALERT_KINDS.map((k) => <SelectItem key={k} value={k}>{ALERT_KIND_LABEL[k]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="rule-threshold">{ratio ? "Limite (%)" : "Tempo fora do ar (min)"}</Label>
              <Input id="rule-threshold" inputMode="decimal" value={form.threshold} onChange={(e) => set("threshold", e.target.value)} placeholder={ratio ? "0,25" : "15"} aria-invalid={form.threshold !== "" && !th.ok} aria-describedby="rule-threshold-help" required />
              <p id="rule-threshold-help" className="text-xs text-muted">{ratio ? "Percentual mínimo; 0,25 equivale a 0,25 % (ratio 0,0025)." : "Minutos sem coleta bem-sucedida antes de alertar."}</p>
              {form.threshold !== "" && !th.ok && <p role="alert" className="text-xs text-loss">{th.error}</p>}
            </div>
          </div>
          {form.kind === "quote_move" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor="rule-pair">Par</Label>
                <Select value={form.pair} onValueChange={(v) => set("pair", v)}>
                  <SelectTrigger id="rule-pair"><SelectValue /></SelectTrigger>
                  <SelectContent>{ALERT_PAIRS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid gap-1">
                <Label htmlFor="rule-city">Cidade</Label>
                <Select value={form.city} onValueChange={(v) => set("city", v)}>
                  <SelectTrigger id="rule-city"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(["CDE", "ASU", "PJC"] as const).map((c) => <SelectItem key={c} value={c}>{CITY_LABEL[c]}</SelectItem>)}
                    <SelectItem value="digital">Digital (sem cidade)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1">
              <Label htmlFor="rule-channel">Canal</Label>
              <Select value={form.channel} onValueChange={(v) => set("channel", v as AlertChannel)}>
                <SelectTrigger id="rule-channel"><SelectValue /></SelectTrigger>
                <SelectContent>{ALERT_CHANNELS.map((c) => <SelectItem key={c} value={c}>{ALERT_CHANNEL_LABEL[c]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="rule-cooldown">Cooldown</Label>
              <Select value={form.cooldown} onValueChange={(v) => set("cooldown", v)}>
                <SelectTrigger id="rule-cooldown"><SelectValue /></SelectTrigger>
                <SelectContent>{COOLDOWNS.map((c) => <SelectItem key={c} value={String(c)}>{formatInterval(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          {form.channel !== "ui" && (
            <div className="grid gap-1">
              <Label htmlFor="rule-target">{TARGET_HELP[form.channel].label}</Label>
              <Input id="rule-target" value={form.target} onChange={(e) => set("target", e.target.value)} placeholder={TARGET_HELP[form.channel].placeholder} inputMode={form.channel === "email" ? "email" : form.channel === "webhook" ? "url" : "text"} aria-invalid={form.target !== "" && !tg.ok} aria-describedby="rule-target-help" required />
              <p id="rule-target-help" className="text-xs text-muted">{TARGET_HELP[form.channel].help}</p>
              {form.target !== "" && !tg.ok && <p role="alert" className="text-xs text-loss">{tg.error}</p>}
            </div>
          )}
          <Button type="submit" disabled={!valid || pending}>{pending ? "Salvando…" : "Criar regra"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
