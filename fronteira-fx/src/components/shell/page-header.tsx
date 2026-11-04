/**
 * Cabeçalho de página (G1, dev/ui/spec-reforma-ui.md). O título da rota é o `h1` da barra superior; aqui fica só a
 * descrição, sem repetir o título em um `h2`. `title` continua aceito para não quebrar as telas, mas não é desenhado.
 */
export function PageHeader({ description, children }: { title?: string; description?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>{description && <p className="text-body text-muted">{description}</p>}</div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
