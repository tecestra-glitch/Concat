import { SourceIntegrationSchema } from "./schemas";
import type { SourceIntegration } from "./types";

/** Rótulo do selo de integração da fonte (ver docs/integracoes.md). */
export const INTEGRATION_LABEL: Record<SourceIntegration, string> = {
  api_oficial: "API oficial",
  endpoint_interno: "Endpoint interno",
  html: "HTML",
  navegador: "Navegador",
};

/** Rótulo para um valor vindo da API; valor desconhecido volta como veio, nunca quebra a tela. */
export function integrationLabel(value: string): string {
  const parsed = SourceIntegrationSchema.safeParse(value);
  return parsed.success ? INTEGRATION_LABEL[parsed.data] : value;
}
