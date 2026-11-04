import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PREMISSAS_RAILS, PREMISSAS_TRANSPORT, premissaStatus } from "@/lib/api/premissas";

const CITY: Record<string, string> = { CDE: "Ciudad del Este", ASU: "Asunción", PJC: "Pedro Juan Caballero", ENC: "Encarnación", FOZ: "Foz do Iguaçu", PPO: "Ponta Porã" };
const MODE: Record<string, string> = { car: "carro", bus: "ônibus", taxi: "táxi", walk: "a pé", flight: "avião" };
const RAIL_PLACE: Record<string, string> = { br_bank: "Banco BR", py_bank: "Banco PY", revolut: "Revolut", nomad: "Nomad", exchange_house: "Casa de câmbio", cash: "Dinheiro (caixa eletrônico)" };
const check = (p: { verified: boolean; source_url: string | null; checked_at: string | null }) => premissaStatus(p);

/** Premissas do cruzamento só para leitura: de onde vem cada custo e o que ainda não foi verificado. */
export function PremissasCard() {
  return (
    <Card data-testid="premissas">
      <CardHeader>
        <CardTitle>Premissas do cruzamento</CardTitle>
        <CardDescription>
          Tempos e custos que o motor usa para deslocamento entre cidades e para transferências entre contas. Só leitura. Um valor marcado como «não verificado» aparece sem custo confirmado e deixa o ciclo incompleto.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <section aria-labelledby="prem-transport">
          <h3 id="prem-transport" className="mb-2 text-sm font-semibold">Deslocamento entre cidades</h3>
          <Table scrollLabel="Premissas de deslocamento (rola para o lado)">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Trecho</TableHead>
                <TableHead>Meio</TableHead>
                <TableHead className="text-right">Tempo</TableHead>
                <TableHead>Custo</TableHead>
                <TableHead>Fronteira</TableHead>
                <TableHead>Fonte</TableHead>
                <TableHead>Conferido em</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PREMISSAS_TRANSPORT.map((r) => {
                const s = check(r);
                return (
                  <TableRow key={r.id} data-testid="premissa-route">
                    <TableCell className="font-medium">{CITY[r.from_city] ?? r.from_city} → {CITY[r.to_city] ?? r.to_city}</TableCell>
                    <TableCell>{MODE[r.mode] ?? r.mode}</TableCell>
                    <TableCell className="tnum text-right">{r.minutes} min</TableCell>
                    <TableCell><Badge variant={s.verified ? "gain" : "incomplete"}>{r.cost === null ? "não verificado" : "informado"}</Badge></TableCell>
                    <TableCell>{r.border ? "sim" : "não"}</TableCell>
                    <TableCell className="max-w-[16rem] break-words text-xs text-muted">{s.source}</TableCell>
                    <TableCell className="text-xs text-muted">{r.checked_at ?? "—"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </section>
        <section aria-labelledby="prem-rails">
          <h3 id="prem-rails" className="mb-2 text-sm font-semibold">Trilhos de transferência</h3>
          <Table scrollLabel="Premissas de trilhos (rola para o lado)">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>De → para</TableHead>
                <TableHead>Moeda</TableHead>
                <TableHead className="text-right">Tempo</TableHead>
                <TableHead>Tarifa e IOF</TableHead>
                <TableHead>Fonte</TableHead>
                <TableHead>Conferido em</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PREMISSAS_RAILS.map((r) => {
                const s = check(r);
                const conversion = r.currency !== r.to_currency ? ` → ${r.to_currency}` : "";
                return (
                  <TableRow key={r.id} data-testid="premissa-rail">
                    <TableCell className="font-medium">{RAIL_PLACE[r.from] ?? r.from} → {RAIL_PLACE[r.to] ?? r.to}</TableCell>
                    <TableCell>{r.currency}{conversion}</TableCell>
                    <TableCell className="tnum text-right">{r.minutes} min</TableCell>
                    <TableCell><Badge variant={s.verified ? "gain" : "incomplete"}>{s.verified ? "verificado" : "não verificado"}</Badge></TableCell>
                    <TableCell className="max-w-[16rem] break-words text-xs text-muted">{s.source}</TableCell>
                    <TableCell className="text-xs text-muted">{r.checked_at ?? "—"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </section>
      </CardContent>
    </Card>
  );
}
