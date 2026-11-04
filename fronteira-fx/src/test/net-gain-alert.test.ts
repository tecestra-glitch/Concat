import { describe, expect, it } from "vitest";
import { formatThreshold, isRatioKind, validateThreshold } from "@/lib/api/watch";
import { findNetGainRule, netGainFormFromRule, netGainRuleFromForm, NET_GAIN_RULE_NAME } from "@/components/settings/net-gain-alert";
import type { AlertRule } from "@/lib/api/watch";

const rule = (over: Partial<AlertRule> = {}): AlertRule => ({
  id: "r-ng",
  name: NET_GAIN_RULE_NAME,
  kind: "cycle_net_gain",
  threshold: "20",
  params: { currency: "BRL" },
  channel: "ui",
  target: null,
  cooldown_s: 600,
  enabled: true,
  data_mode: "demo",
  ...over,
});

describe("alerta de ganho líquido por ciclo (limite em dinheiro, não em ROI)", () => {
  it("o limite não é uma porcentagem: validação e formato em dinheiro na moeda da regra", () => {
    expect(isRatioKind("cycle_net_gain")).toBe(false);
    expect(validateThreshold("cycle_net_gain", "1.250,5")).toEqual({ ok: true, value: "1250.5" });
    expect(validateThreshold("cycle_net_gain", "0")).toEqual({ ok: true, value: "0" });
    expect(validateThreshold("cycle_net_gain", "-1").ok).toBe(false);
    expect(validateThreshold("cycle_net_gain", "abc").ok).toBe(false);
    expect(formatThreshold("cycle_net_gain", "20", "BRL")).toBe("R$ 20,00");
    expect(formatThreshold("cycle_net_gain", "600000", "PYG")).toBe("₲ 600.000");
  });

  it("formulário → regra: sempre ui, cooldown de 10 min, moeda em params", () => {
    const r = netGainRuleFromForm({ currency: "USD", threshold: "15", enabled: true });
    expect(r).toEqual({ ok: true, input: { name: NET_GAIN_RULE_NAME, kind: "cycle_net_gain", threshold: "15", params: { currency: "USD" }, channel: "ui", target: null, cooldown_s: 600, enabled: true } });
    expect(netGainRuleFromForm({ currency: "BRL", threshold: "", enabled: true }).ok).toBe(false);
  });

  it("encontra a regra existente e preenche o formulário a partir dela", () => {
    const other = rule({ id: "x", kind: "cycle_roi", params: null, threshold: "0.002" });
    expect(findNetGainRule([other])).toBeUndefined();
    expect(findNetGainRule([other, rule()])?.id).toBe("r-ng");
    expect(netGainFormFromRule(rule({ threshold: "1250.5", params: { currency: "PYG" } }))).toEqual({ currency: "PYG", threshold: "1250,5", enabled: true });
    expect(netGainFormFromRule(undefined)).toEqual({ currency: "BRL", threshold: "", enabled: true });
  });
});
