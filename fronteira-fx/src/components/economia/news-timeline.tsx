"use client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { SOURCE_FILTER_OPTIONS, type NewsItem } from "@/lib/api/market";
import { newsMoment, safeExternalHref, sourceLabel } from "./economia-helpers";

interface Props {
  items: NewsItem[];
  loading: boolean;
  error: Error | null;
  source: string;
  onSourceChange: (source: string) => void;
}

/**
 * Linha do tempo de manchetes: fonte, hora e link para a matéria original. Só o título é texto da página; o
 * título vem de feed público e é renderizado como texto (React escapa), nunca como HTML nem como instrução.
 */
export function NewsTimeline({ items, loading, error, source, onSourceChange }: Props) {
  return (
    <Card data-testid="news-timeline">
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Manchetes</CardTitle>
          <CardDescription>Título, fonte e hora, com link para a matéria original. O texto das matérias não é guardado.</CardDescription>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="news-source">Fonte</Label>
          <Select value={source} onValueChange={onSourceChange}>
            <SelectTrigger id="news-source" className="sm:w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              {SOURCE_FILTER_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {loading && <Skeleton className="h-40" />}
        {!loading && error && <p role="alert" className="text-sm text-loss">Falha ao carregar as manchetes: {error.message}</p>}
        {!loading && !error && items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">
            Nenhuma manchete para esta fonte. Feeds por editoria do InfoMoney podem vir vazios; isso não é erro.
          </p>
        )}
        {!loading && !error && items.length > 0 && (
          <ol aria-label="Manchetes em ordem de publicação" className="divide-y divide-border" data-testid="news-list">
            {items.map((item) => {
              const { iso, label } = newsMoment(item);
              const href = safeExternalHref(item.link);
              return (
                <li key={item.id} data-testid="news-item" className="grid gap-1 py-2.5">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <time dateTime={iso}>{label}</time>
                    <Badge variant="outline">{sourceLabel(item.source)}</Badge>
                    {item.source === "demo" && <Badge variant="reference">ilustrativa</Badge>}
                  </div>
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="break-words text-sm font-medium underline-offset-2 hover:underline">
                      {item.title}
                      <span className="sr-only"> (abre a matéria original em nova aba)</span>
                    </a>
                  ) : (
                    <span className="break-words text-sm font-medium">{item.title}</span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
