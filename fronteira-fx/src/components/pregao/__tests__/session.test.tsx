import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { HouseSession } from "@/lib/pregao/types";
import { SessionClock, clockText } from "@/components/pregao/session-clock";
import { MarketStatus, formatCountdown, summarizeSessions } from "@/components/pregao/market-status";

// 2026-11-02T15:04Z é 12:04 em Assunção (America/Asuncion) e em Brasília (America/Sao_Paulo), ambas UTC−3.
const now = Date.UTC(2026, 10, 2, 15, 4);
const minutesAfter = (min: number) => now + min * 60_000;

function session(overrides: Partial<HouseSession> & Pick<HouseSession, "source_id" | "status">): HouseSession {
  return {
    name: overrides.source_id,
    city: null,
    tz: "America/Asuncion",
    channel: "physical",
    reference: false,
    opens_at: null,
    closes_at: null,
    next_change_at: null,
    data_mode: "real",
    ...overrides,
  };
}

describe("clockText", () => {
  it("formata HH:mm no fuso pedido", () => {
    expect(clockText(now, "America/Asuncion")).toBe("12:04");
    expect(clockText(now, "America/Sao_Paulo")).toBe("12:04");
  });

  it("mostra travessão quando now é 0 (servidor)", () => {
    expect(clockText(0, "UTC")).toBe("—:—");
  });

  it("mostra 00:00 à meia-noite local, nunca 24:00", () => {
    // 2026-11-02T03:00Z é 00:00 em Assunção.
    expect(clockText(Date.UTC(2026, 10, 2, 3, 0), "America/Asuncion")).toBe("00:00");
  });
});

describe("SessionClock", () => {
  it("renderiza uma <time> por zona, com ISO em datetime e horário local", () => {
    const html = renderToStaticMarkup(<SessionClock now={now} />);
    expect(html).toContain('data-testid="pregao-clock"');
    expect(html.match(/<time dateTime="2026-11-02T15:04:00\.000Z">12:04<\/time>/g)).toHaveLength(2);
    expect(html).toContain("Assunção / CDE");
    expect(html).toContain("Brasília");
    expect(html).toContain('data-tz="America/Asuncion"');
    expect(html).toContain('data-tz="America/Sao_Paulo"');
  });

  it("mostra a próxima referência BCP no horário de Assunção", () => {
    const html = renderToStaticMarkup(<SessionClock now={now} referenceNext="2026-11-03T11:00:00Z" />);
    expect(html).toContain("Referência BCP");
    expect(html).toContain("próxima mudança às 08:00");
  });

  it("mostra 'sem horário' quando não há próxima referência", () => {
    const html = renderToStaticMarkup(<SessionClock now={now} referenceNext={null} />);
    expect(html).toContain("sem horário");
  });

  it("com now === 0 mostra travessão e nenhum <time>", () => {
    const html = renderToStaticMarkup(<SessionClock now={0} />);
    expect(html).toContain("—:—");
    expect(html).not.toContain("<time");
  });
});

describe("summarizeSessions", () => {
  it("ignora referências e conta os status das casas", () => {
    const summary = summarizeSessions(
      [
        session({ source_id: "chaco", status: "open", city: "CDE" }),
        session({ source_id: "norte", status: "closed", city: "ASU" }),
        session({ source_id: "bcp", status: "open", reference: true }),
      ],
      now,
    );
    expect(summary).toMatchObject({ open: 1, pre: 0, closed: 1, unknown: 0, total: 2, digitalOpen: 0, digitalTotal: 0, badge: "gain", label: "aberto" });
  });

  it("digitais não entram no 'aberto' nem nas casas físicas: só digitais abertas dão 'só digitais' neutro", () => {
    const summary = summarizeSessions(
      [session({ source_id: "chaco", status: "closed", city: "CDE" }), session({ source_id: "nomad", status: "open", channel: "digital" })],
      now,
    );
    expect(summary).toMatchObject({ open: 0, total: 1, closed: 1, digitalOpen: 1, digitalTotal: 1, badge: "outline", label: "só digitais" });
  });

  it("'aberto' (verde) exige física aberta; digitais abertas ao lado não mudam o selo", () => {
    const summary = summarizeSessions(
      [session({ source_id: "chaco", status: "open", city: "CDE" }), session({ source_id: "nomad", status: "open", channel: "digital" })],
      now,
    );
    expect(summary).toMatchObject({ open: 1, digitalOpen: 1, badge: "gain", label: "aberto" });
  });

  it("só digitais, sem nenhuma física no par: 'só digitais' e total físico zero", () => {
    const summary = summarizeSessions([session({ source_id: "nomad", status: "open", channel: "digital" })], now);
    expect(summary).toMatchObject({ total: 0, digitalTotal: 1, badge: "outline", label: "só digitais" });
  });

  it("com só casas sem horário, o rótulo é 'sem horário' e nunca 'fechado'", () => {
    const summary = summarizeSessions([session({ source_id: "x", status: "unknown" })], now);
    expect(summary.label).toBe("sem horário");
    expect(summary.label).not.toBe("fechado");
  });

  it("com pré-abertura e nenhuma aberta, o rótulo é 'pré-abertura' em warn", () => {
    const summary = summarizeSessions([session({ source_id: "x", status: "pre" })], now);
    expect(summary).toMatchObject({ badge: "warn", label: "pré-abertura" });
  });

  it("sem sessões, total é 0 e o rótulo é 'sem horário'", () => {
    expect(summarizeSessions([], now)).toMatchObject({ total: 0, label: "sem horário", badge: "outline" });
  });

  it("nextChangeAt é a menor mudança futura entre as casas, sem referências", () => {
    const summary = summarizeSessions(
      [
        session({ source_id: "chaco", status: "open", next_change_at: new Date(minutesAfter(120)).toISOString() }),
        session({ source_id: "norte", status: "closed", next_change_at: new Date(minutesAfter(30)).toISOString() }),
        session({ source_id: "passada", status: "closed", next_change_at: new Date(minutesAfter(-5)).toISOString() }),
        session({ source_id: "bcp", status: "open", reference: true, next_change_at: new Date(minutesAfter(1)).toISOString() }),
      ],
      now,
    );
    expect(summary.nextChangeAt).toBe(new Date(minutesAfter(30)).toISOString());
  });

  it("com now === 0, nextChangeAt é null", () => {
    const summary = summarizeSessions([session({ source_id: "chaco", status: "open", next_change_at: new Date(minutesAfter(10)).toISOString() })], 0);
    expect(summary.nextChangeAt).toBeNull();
  });
});

describe("formatCountdown", () => {
  it("mostra minutos abaixo de uma hora", () => {
    expect(formatCountdown(new Date(minutesAfter(10)).toISOString(), now)).toBe("10 min");
  });

  it("mostra horas e minutos com dois dígitos a partir de uma hora", () => {
    expect(formatCountdown(new Date(minutesAfter(130)).toISOString(), now)).toBe("2 h 10 min");
  });

  it("arredonda para cima: trinta segundos viram '1 min', nunca '0 min'", () => {
    expect(formatCountdown(new Date(now + 30_000).toISOString(), now)).toBe("1 min");
  });

  it("alvo no passado ou agora devolve 'agora'", () => {
    expect(formatCountdown(new Date(minutesAfter(-5)).toISOString(), now)).toBe("agora");
    expect(formatCountdown(new Date(now).toISOString(), now)).toBe("agora");
  });
});

describe("MarketStatus", () => {
  it("conta casas físicas do par e mostra o total com o badge gain, sem a palavra 'digitais' quando não há digitais", () => {
    const html = renderToStaticMarkup(
      <MarketStatus
        now={now}
        sessions={[
          session({ source_id: "chaco", status: "open", city: "CDE", next_change_at: new Date(minutesAfter(10)).toISOString() }),
          session({ source_id: "norte", status: "closed", city: "ASU" }),
          session({ source_id: "bcp", status: "open", reference: true }),
        ]}
      />,
    );
    expect(html).toContain('data-testid="pregao-market-status"');
    expect(html).toContain('data-badge="gain"');
    expect(html).toContain("1 de 2 casas físicas abertas · próxima mudança em 10 min");
    expect(html).not.toContain("digitais");
    expect(html).not.toContain('role="status"');
  });

  it("digitais aparecem à parte, depois das físicas, e não acendem o selo quando as físicas estão fechadas", () => {
    const html = renderToStaticMarkup(
      <MarketStatus
        now={now}
        sessions={[
          session({ source_id: "chaco", status: "closed", city: "CDE" }),
          session({ source_id: "norte", status: "closed", city: "ASU" }),
          session({ source_id: "nomad", status: "open", channel: "digital" }),
        ]}
      />,
    );
    expect(html).toContain('data-badge="outline"');
    expect(html).toContain("só digitais");
    expect(html).toContain("0 de 2 casas físicas abertas · 1 de 1 digitais abertas");
    expect(html).not.toContain('data-badge="gain"');
  });

  it("digital sem horário verificado não vira 'aberta' nem 'fechada': aparece como 'sem horário'", () => {
    const html = renderToStaticMarkup(
      <MarketStatus
        now={now}
        sessions={[
          session({ source_id: "chaco", status: "closed", city: "CDE" }),
          session({ source_id: "banco-demo-py", status: "unknown", channel: "digital" }),
          session({ source_id: "nomad", status: "unknown", channel: "digital" }),
        ]}
      />,
    );
    expect(html).toContain("0 de 1 casas físicas abertas · 0 de 2 digitais abertas (2 sem horário)");
    expect(html).not.toContain("só digitais");
    expect(html).not.toContain('data-badge="gain"');
  });

  it("enquanto as cotações carregam, não afirma que não há casas: mostra 'Carregando horários…'", () => {
    const html = renderToStaticMarkup(<MarketStatus now={now} sessions={[]} loading />);
    expect(html).toContain("Carregando horários");
    expect(html).not.toContain("nenhuma casa");
  });

  it("sem nenhuma casa com horário, diz isso em vez de '0 de 0'", () => {
    const html = renderToStaticMarkup(<MarketStatus now={now} sessions={[]} />);
    expect(html).toContain("nenhuma casa com horário informado");
    expect(html).not.toContain("0 de 0");
  });
});

describe("componentes puros", () => {
  it.each(["session-clock.tsx", "market-status.tsx"])("%s não lê o relógio nem usa efeitos", (file) => {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    expect(source).not.toMatch(/useNow|useEffect\(|Date\.now\(\)/);
  });
});
