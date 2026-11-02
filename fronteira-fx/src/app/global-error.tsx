"use client";
/** Último recurso: substitui o layout raiz, então não há Tailwind nem fontes carregadas — estilos inline. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="pt-BR">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0b1020", color: "#e6eaf3", minHeight: "100dvh", display: "grid", placeItems: "center", padding: 24 }}>
        <main style={{ maxWidth: 480, textAlign: "center" }}>
          <h1 style={{ fontSize: 20, marginBottom: 8 }}>O Fronteira FX parou de responder</h1>
          <p style={{ fontSize: 14, color: "#94a3b8", marginBottom: 16 }}>
            Um erro impediu a aplicação inteira de renderizar. Nada foi executado nas suas contas.
            {error.digest ? ` Referência: ${error.digest}.` : ""}
          </p>
          <button type="button" onClick={reset} style={{ background: "#60a5fa", color: "#0b1020", border: 0, borderRadius: 8, padding: "8px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer" }}>
            Recarregar
          </button>
        </main>
      </body>
    </html>
  );
}
