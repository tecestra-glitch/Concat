import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * DS9: o contêiner de rolagem é focável e nomeado (`scrollLabel`) para quem navega por teclado;
 * cabeçalho em 12 px; linhas com ≥ 40 px abaixo de 640 px.
 */
export function Table({ className, scrollLabel, ...props }: React.HTMLAttributes<HTMLTableElement> & { scrollLabel?: string }) {
  return (
    <div className="relative w-full overflow-x-auto" tabIndex={scrollLabel ? 0 : undefined} role={scrollLabel ? "region" : undefined} aria-label={scrollLabel}>
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}
export function TableHeader(props: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className="[&_tr]:border-b" {...props} />;
}
export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}
export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-border transition-colors hover:bg-surface-2/60 data-[state=selected]:bg-surface-2", className)} {...props} />;
}
export function TableHead({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("h-9 px-2 text-left align-middle text-xs font-medium tracking-wide text-muted", className)} {...props} />;
}
export function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-2 py-1.5 align-middle max-sm:py-2.5", className)} {...props} />;
}
export function TableCaption({ className, ...props }: React.HTMLAttributes<HTMLTableCaptionElement>) {
  return <caption className={cn("py-2 text-left text-xs text-muted", className)} {...props} />;
}
