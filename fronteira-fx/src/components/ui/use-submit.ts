"use client";
import * as React from "react";

/**
 * Estado de envio de um diálogo: `pending` enquanto a promessa corre, `error` com a mensagem quando
 * falha. `run` resolve `true` só em sucesso, para o chamador fechar o diálogo DEPOIS do resultado.
 */
export function useSubmitState() {
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const run = React.useCallback(async (fn: () => Promise<unknown>, fallback = "Falha ao salvar."): Promise<boolean> => {
    setPending(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : fallback);
      return false;
    } finally {
      setPending(false);
    }
  }, []);
  const clear = React.useCallback(() => setError(null), []);
  return { pending, error, run, clear };
}
