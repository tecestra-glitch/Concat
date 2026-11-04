// Trilha de passos com o tempo desde o início da execução: `amount=5000@41.2s`.
// O relógio é injetado, então os testes controlam o tempo sem esperar de verdade.

export type Clock = () => number;

export function startedClock(now: () => number = () => Date.now()): Clock {
  const t0 = now();
  return () => now() - t0;
}

export class Trail {
  readonly steps: string[] = [];

  constructor(private readonly elapsedMs: Clock = startedClock()) {}

  add(label: string): void {
    this.steps.push(`${label}@${(Math.max(0, this.elapsedMs()) / 1000).toFixed(1)}s`);
  }

  /** Só os rótulos, sem o tempo (para comparar a sequência de passos em testes). */
  labels(): string[] {
    return this.steps.map((s) => s.replace(/@\d+\.\ds$/, ""));
  }
}
