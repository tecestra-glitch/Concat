/**
 * O EventSource não expõe o status HTTP de uma falha. Quando o stream nem chega a abrir, uma requisição comum
 * ao mesmo endereço diz se a API desligou o stream de propósito (404 na instância serverless da Vercel, ver
 * `refuse_on_serverless` no backend). Só 404 conta: rede caída, 5xx ou 410 seguem o caminho normal de
 * reconexão. A conexão é abortada assim que o status chega, para nunca ficar um segundo stream aberto.
 */
export async function probeStreamOff(url: string, fetchImpl: typeof fetch = fetch): Promise<boolean> {
  const ctrl = new AbortController();
  try {
    const res = await fetchImpl(url, {
      signal: ctrl.signal,
      headers: { accept: "text/event-stream" },
      credentials: "same-origin",
      cache: "no-store",
    });
    return res.status === 404;
  } catch {
    return false;
  } finally {
    ctrl.abort();
  }
}
