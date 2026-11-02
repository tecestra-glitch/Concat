import { isRatioKind, validateTarget, validateThreshold, type AlertChannel, type AlertKind, type AlertRule, type AlertRuleInput } from "@/lib/api/watch";
import { toNumber } from "@/lib/format";

export interface RuleForm {
  name: string;
  kind: AlertKind;
  threshold: string;
  pair: string;
  city: string;
  channel: AlertChannel;
  target: string;
  cooldown: string;
  enabled: boolean;
  /** Limite tal como está salvo; reenviado intacto se o campo não for editado (evita arredondar 90 s → 120 s). */
  originalThreshold?: string;
}

export const EMPTY_RULE_FORM: RuleForm = { name: "", kind: "cycle_roi", threshold: "", pair: "USD/PYG", city: "CDE", channel: "ui", target: "", cooldown: "600", enabled: true };

/** Limite armazenado → texto do formulário: ratio vira percentual pt-BR ("0.002" → "0,2"); segundos viram minutos. */
export function thresholdToForm(kind: AlertKind, threshold: string): string {
  const n = toNumber(threshold);
  if (n === null) return "";
  if (isRatioKind(kind)) return String(Math.round(n * 1e8) / 1e6).replace(".", ",");
  return String(Math.round(n / 60));
}

export function ruleToForm(r: AlertRule): RuleForm {
  return {
    name: r.name,
    kind: r.kind,
    threshold: thresholdToForm(r.kind, r.threshold),
    pair: r.params?.pair ?? EMPTY_RULE_FORM.pair,
    city: r.params && r.params.city !== undefined ? (r.params.city ?? "digital") : EMPTY_RULE_FORM.city,
    channel: r.channel,
    target: r.target ?? "",
    cooldown: String(r.cooldown_s),
    enabled: r.enabled,
    originalThreshold: r.threshold,
  };
}

/** `null` quando o formulário não passa na validação (nome ≥ 3, limite e destino válidos). */
export function formToInput(f: RuleForm): AlertRuleInput | null {
  const th = validateThreshold(f.kind, f.threshold);
  const tg = validateTarget(f.channel, f.target);
  if (f.name.trim().length < 3 || !th.ok || !tg.ok) return null;
  const untouched = f.originalThreshold !== undefined && thresholdToForm(f.kind, f.originalThreshold) === f.threshold;
  return {
    name: f.name.trim(),
    kind: f.kind,
    threshold: untouched ? f.originalThreshold! : th.value,
    // Q-04: «Digital (sem cidade)» is the explicit value "digital" (only city-less quotes); null would mean any city.
    params: f.kind === "quote_move" ? { pair: f.pair, city: f.city } : null,
    channel: f.channel,
    target: tg.value,
    cooldown_s: Number(f.cooldown),
    enabled: f.enabled,
  };
}
