import { describe, expect, it } from "vitest";
import { flashStep, type FlashState } from "./fx-flash";

const start = (value: string | number | null): FlashState => ({ value, cls: undefined, alt: false });

describe("flashStep (realce por célula que mudou)", () => {
  it("valor igual não gera realce", () => {
    const s = start("5880");
    expect(flashStep(s, "5880")).toBe(s);
    expect(flashStep(s, "5880").cls).toBeUndefined();
  });

  it("valor novo maior gera fx-flash-up; menor gera fx-flash-down", () => {
    expect(flashStep(start("5880"), "5900").cls).toBe("fx-flash-up-b");
    expect(flashStep(start("5880"), "5850").cls).toBe("fx-flash-down-b");
  });

  it("mudanças seguidas no mesmo sentido alternam o sufixo para reiniciar a animação", () => {
    const first = flashStep(start("100"), "101");
    const second = flashStep(first, "102");
    expect(first.cls).toBe("fx-flash-up-b");
    expect(second.cls).toBe("fx-flash-up");
    expect(flashStep(second, "103").cls).toBe("fx-flash-up-b");
  });

  it("aceita número e texto decimal como o mesmo valor", () => {
    expect(flashStep(start(5880), "5880").cls).toBeUndefined();
    expect(flashStep(start("5880.5"), "5881").cls).toBe("fx-flash-up-b");
  });

  it("primeira carga ou nulo nunca pisca", () => {
    expect(flashStep(start(null), "5880").cls).toBeUndefined();
    expect(flashStep(start("5880"), null).cls).toBeUndefined();
  });
});
