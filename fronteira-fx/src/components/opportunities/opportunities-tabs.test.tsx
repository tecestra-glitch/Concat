import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Opportunities } from "@/components/opportunities/opportunities";
import { SettingsProvider } from "@/lib/settings";

function html(): string {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <SettingsProvider>
        <Opportunities />
      </SettingsProvider>
    </QueryClientProvider>,
  );
}

describe("Oportunidades: modo celular na tela", () => {
  it("explica a regra e oferece a aba Presencial (opcional)", () => {
    const out = html();
    expect(out).toContain("Pelo celular: aqui entram só as rotas que dá para fazer inteiras no app");
    expect(out).toContain("Presencial (opcional)");
  });
});
