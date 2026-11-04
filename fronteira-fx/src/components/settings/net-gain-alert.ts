/**
 * Limite do alerta de ganho líquido por ciclo (Configurações). Regra única por moeda de medida: o formulário
 * cria a regra na primeira vez e depois só a atualiza. Puro, para ser testado sem DOM.
 */
import { validateThreshold, type AlertRule, type AlertRuleInput } from "@/lib/api/watch";

export const NET_GAIN_RULE_NAME = "Ganho líquido de ciclo";
/** Cooldown do alerta de ganho: 10 min entre disparos iguais (o padrão das regras de ciclo). */
export const NET_GAIN_COOLDOWN_S = 600;

export type NetGainCurrency = "BRL" | "USD" | "PYG";

export interface NetGainForm {
  currency: NetGainCurrency;
  /** Texto digitado em pt-BR ("20", "1.250,50"); o valor canônico sai de `validateThreshold`. */
  threshold: string;
  enabled: boolean;
}

export const EMPTY_NET_GAIN_FORM: NetGainForm = { currency: "BRL", threshold: "", enabled: true };

export function findNetGainRule(rules: AlertRule[] | undefined): AlertRule | undefined {
  return rules?.find((r) => r.kind === "cycle_net_gain");
}

/** Regra salva → formulário: o limite volta com vírgula decimal ("1250.5" → "1250,5"). */
export function netGainFormFromRule(rule: AlertRule | undefined): NetGainForm {
  if (!rule) return EMPTY_NET_GAIN_FORM;
  return {
    currency: rule.params?.currency ?? "BRL",
    threshold: rule.threshold.replace(".", ","),
    enabled: rule.enabled,
  };
}

export type NetGainResult = { ok: true; input: AlertRuleInput } | { ok: false; error: string };

/** Formulário → corpo de POST/PATCH. O canal é sempre a própria interface: não há destino a preencher. */
export function netGainRuleFromForm(f: NetGainForm): NetGainResult {
  const th = validateThreshold("cycle_net_gain", f.threshold);
  if (!th.ok) return { ok: false, error: th.error };
  return {
    ok: true,
    input: {
      name: NET_GAIN_RULE_NAME,
      kind: "cycle_net_gain",
      threshold: th.value,
      params: { currency: f.currency },
      channel: "ui",
      target: null,
      cooldown_s: NET_GAIN_COOLDOWN_S,
      enabled: f.enabled,
    },
  };
}
