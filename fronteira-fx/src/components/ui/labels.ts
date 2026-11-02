import type { BadgeVariant } from "./badge";
import type { DataMode, Health } from "@/lib/api/types";

/** Rótulos pt-BR compartilhados pelas telas (um lugar só, para não divergirem). */
export const MODE_LABEL: Record<DataMode, string> = { real: "real", simulation: "simulação", demo: "demonstração" };
export const MODE_TONE: Record<DataMode, BadgeVariant> = { real: "gain", simulation: "accent", demo: "warn" };
export const HEALTH_LABEL: Record<Health, string> = { ok: "ok", degraded: "degradada", stale: "antiga", blocked: "bloqueada", unknown: "desconhecida" };
export const HEALTH_TONE: Record<Health, BadgeVariant> = { ok: "gain", degraded: "warn", stale: "warn", blocked: "loss", unknown: "outline" };
