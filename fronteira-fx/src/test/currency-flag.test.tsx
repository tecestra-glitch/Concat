import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CurrencyFlag, PairFlags, countryOfCode, type FlagCode } from "@/components/ui/currency-flag";
import { sourceCountry } from "@/lib/api/source-country";
import type { Source } from "@/lib/api/types";

const CODES: FlagCode[] = ["BRL", "USD", "PYG", "ARS", "EUR"];

describe("CurrencyFlag", () => {
  it("cada moeda com bandeira renderiza um SVG aria-hidden e o código como texto", () => {
    for (const code of CODES) {
      const html = renderToStaticMarkup(<CurrencyFlag code={code} />);
      expect(html, code).toMatch(/<svg[^>]*aria-hidden="true"/);
      expect(html, code).toContain(`>${code}<`);
    }
  });

  it("USDT usa o ícone próprio e não tem bandeira", () => {
    const html = renderToStaticMarkup(<CurrencyFlag code="USDT" />);
    expect(countryOfCode("USDT")).toBeNull();
    expect(html).toContain("#26a17b");
    expect(html).not.toContain("#b22234");
    expect(html).toContain(">USDT<");
  });

  it("PairFlags mantém o nome do par em texto contínuo (USD/PYG)", () => {
    const html = renderToStaticMarkup(<PairFlags base="USD" quote="PYG" />);
    expect(html.replace(/<[^>]+>/g, "")).toBe("USD/PYG");
  });

  it("países: PY é azul ao fundo; BR tem losango amarelo", () => {
    expect(renderToStaticMarkup(<CurrencyFlag code="PYG" />)).toContain("#d52b1e");
    expect(renderToStaticMarkup(<CurrencyFlag code="BRL" />)).toContain("#ffdf00");
  });
});

const base: Source = {
  id: "x",
  name: "X",
  kind: "exchange_house",
  method: "html",
  integration: "html",
  url: "https://example.invalid",
  health: "ok",
  last_success_at: null,
  last_error: null,
  capabilities: [],
  limitations: [],
  coverage: { cities: [], currencies: ["USD"] },
  poll_interval_s: 300,
  data_mode: "real",
};

describe("sourceCountry", () => {
  it("banco paraguaio (cidade ASU, PYG e USD) é PY", () => {
    expect(sourceCountry({ ...base, coverage: { cities: ["ASU"], currencies: ["PYG", "USD"] } })).toBe("PY");
  });

  it("fonte sem cidade e só USD não tem país", () => {
    expect(sourceCountry(base)).toBeNull();
  });

  it("moeda PYG sozinha não é sinal de país (remessadora BRL/PYG sem cidade fica sem bandeira)", () => {
    expect(sourceCountry({ ...base, id: "westernunion", coverage: { cities: [], currencies: ["BRL", "PYG"] } })).toBeNull();
    expect(sourceCountry({ ...base, coverage: { cities: [], currencies: ["PYG"] } })).toBeNull();
  });

  it("fontes paraguaias pelo id, mesmo sem cidade na cobertura (BCP e banco demo PY)", () => {
    expect(sourceCountry({ ...base, id: "bcp", coverage: { cities: [], currencies: ["USD", "BRL", "PYG"] } })).toBe("PY");
    expect(sourceCountry({ ...base, id: "banco-demo-py", coverage: { cities: [], currencies: ["USD", "BRL", "PYG"] } })).toBe("PY");
  });

  it("fonte com cidade paraguaia mas sem coverage completa segue a regra da cidade", () => {
    expect(sourceCountry({ ...base, id: "novo-banco", coverage: { cities: ["PJC"], currencies: ["PYG"] } })).toBe("PY");
  });

  it("nenhuma fonte de fora do Paraguai recebe bandeira PY", () => {
    for (const id of ["nomad", "revolut", "westernunion"]) {
      expect(sourceCountry({ ...base, id, coverage: { cities: [], currencies: ["BRL", "USD"] } })).toBeNull();
    }
  });
});
