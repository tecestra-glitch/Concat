import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ConnectionsView, NO_PASSWORD_BANNER } from "@/components/connections/connections-view";
import { API_KEY_STEPS } from "@/components/connections/api-key-dialog";
import type { Connection } from "@/lib/api/connections";

const noop = () => undefined;
const conn: Connection = { id: "c1", institution: "binance", label: "Binance", kind: "readonly_key", status: "active", data_mode: "demo", account_id: null, key_hint: "mnop", balances: null, last_error: null, last_synced_at: null, created_at: "2026-11-04T09:00:00.000Z", updated_at: "2026-11-04T09:00:00.000Z" };

function render(aggregatorConfigured: boolean, connections: Connection[] = []) {
  return renderToStaticMarkup(
    <ConnectionsView mode="demo" aggregatorConfigured={aggregatorConfigured} connections={connections} onOpenFinance={noop} onApiKey={noop} onStatement={noop} onDelete={noop} />,
  );
}

describe("tela de conexões (visual)", () => {
  it("mostra o banner de não pedir senha", () => {
    const html = render(false);
    expect(html).toContain(NO_PASSWORD_BANNER);
    expect(html).toContain('data-testid="no-password-banner"');
  });

  it("nenhum campo de senha de banco na tela", () => {
    expect(render(false)).not.toMatch(/type="password"/);
    expect(render(true, [conn])).not.toMatch(/type="password"/);
  });

  it("lista os quatro grupos e as instituições", () => {
    const html = render(false);
    for (const t of ["Bancos do Brasil", "Contas globais", "Paraguai", "Corretoras de cripto"]) expect(html).toContain(t);
    for (const n of ["Nubank", "Banco do Brasil", "Revolut", "Sudameris", "Binance", "OKX"]) expect(html).toContain(n);
  });

  it("sem agregador, Open Finance fica desabilitado com aviso de contratação", () => {
    const html = render(false);
    expect(html).toContain("Precisa contratar um agregador de Open Finance");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Autorizar pelo Open Finance/);
  });

  it("com agregador, o botão de Open Finance fica habilitado e sem aviso", () => {
    const html = render(true);
    expect(html).not.toContain("Precisa contratar um agregador");
    expect(html).not.toMatch(/<button[^>]*disabled=""[^>]*>Autorizar pelo Open Finance/);
  });

  it("saldo manual leva para Contas", () => {
    expect(render(false)).toContain('href="/contas"');
  });

  it("mostra só os últimos 4 caracteres da chave, nunca a chave", () => {
    const html = render(false, [conn]);
    expect(html).toContain("••••mnop");
    expect(html).toContain("Desconectar Binance");
  });

  it("passo a passo de chave deixa claro o que não marcar", () => {
    const steps = API_KEY_STEPS.join(" ");
    expect(steps).toMatch(/DESMARCADOS operar/);
    expect(steps).toMatch(/Nunca cole sua senha de login/);
  });
});
