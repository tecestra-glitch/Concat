import { describe, expect, it } from "vitest";
import type { AlertRule } from "@/lib/api/watch";
import { formToInput, ruleToForm } from "./rule-form";

const rule: AlertRule = { id: "r1", name: "ciclo > 0,2 %", kind: "cycle_roi", threshold: "0.002", params: null, channel: "telegram", target: "123456789", cooldown_s: 600, enabled: true, data_mode: "real" };

describe("rule-form (edição completa de regra)", () => {
  it("ratio vira percentual pt-BR no formulário e volta igual", () => {
    const f = ruleToForm(rule);
    expect(f.threshold).toBe("0,2");
    expect(f.target).toBe("123456789");
    const input = formToInput(f);
    expect(input).toEqual({ name: rule.name, kind: "cycle_roi", threshold: "0.002", params: null, channel: "telegram", target: "123456789", cooldown_s: 600, enabled: true });
  });
  it("source_down guarda segundos e edita em minutos", () => {
    const f = ruleToForm({ ...rule, kind: "source_down", threshold: "900", channel: "ui", target: null });
    expect(f.threshold).toBe("15");
    expect(formToInput(f)?.threshold).toBe("900");
  });
  it("quote_move preserva par e cidade; «Digital (sem cidade)» viaja como city=digital (Q-04)", () => {
    // null no backend significa «qualquer cidade»; regras antigas com null são lidas como digital
    for (const city of [null, "digital"]) {
      const f = ruleToForm({ ...rule, kind: "quote_move", params: { pair: "BRL/PYG", city } });
      expect(f.pair).toBe("BRL/PYG");
      expect(f.city).toBe("digital");
      expect(formToInput(f)?.params).toEqual({ pair: "BRL/PYG", city: "digital" });
    }
    const cde = ruleToForm({ ...rule, kind: "quote_move", params: { pair: "USD/PYG", city: "CDE" } });
    expect(formToInput(cde)?.params).toEqual({ pair: "USD/PYG", city: "CDE" });
  });
  it("limite original não múltiplo de 60 s é preservado quando o campo não foi tocado", () => {
    const f = ruleToForm({ ...rule, kind: "source_down", threshold: "90", channel: "ui", target: null });
    expect(f.threshold).toBe("2");
    expect(formToInput(f)?.threshold).toBe("90");
    expect(formToInput({ ...f, threshold: "3" })?.threshold).toBe("180");
  });
  it("formulário inválido devolve null", () => {
    expect(formToInput({ ...ruleToForm(rule), threshold: "abc" })).toBeNull();
    expect(formToInput({ ...ruleToForm(rule), name: "ab" })).toBeNull();
  });
});
