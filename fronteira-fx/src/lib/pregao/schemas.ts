/**
 * Validação zod 4 das respostas do pregão (§2.1). Só forma: nenhum arredondamento, nenhuma conversão.
 * Dinheiro continua string decimal; datas continuam string ISO.
 */
import { z } from "zod";
import type { Candle, CandleSeries, HouseHours, HouseSession, SessionStats } from "./types";

export const decStr = z.string().regex(/^-?\d+(\.\d+)?$/, "string decimal");
export const isoDate = z.string().refine((s) => !Number.isNaN(Date.parse(s)), "data ISO");
export const TimeframeSchema = z.enum(["15m", "1h", "4h", "1d"]);
export const PairKeySchema = z.enum(["USD/PYG", "BRL/PYG", "USD/BRL"]);
export const DataModeSchema = z.enum(["real", "simulation", "demo"]);
export const SessionStatusSchema = z.enum(["open", "closed", "pre", "unknown"]);
export const HouseChannelSchema = z.enum(["physical", "digital"]);
export const HouseCitySchema = z.enum(["CDE", "ASU", "PJC", "FOZ", "ENC"]);

export const CandleSchema = z.object({
  t: isoDate,
  o: decStr,
  h: decStr,
  l: decStr,
  c: decStr,
  n: z.int().min(1),
  spread_avg: decStr.nullable(),
  buy_c: decStr.nullable(),
  sell_c: decStr.nullable(),
  data_mode: DataModeSchema,
});
export const CandleSeriesSchema = z.object({ key: z.string().min(1), tf: TimeframeSchema, candles: z.array(CandleSchema), data_mode: DataModeSchema });
export const SessionStatsSchema = z.object({
  key: z.string().min(1),
  day_start: isoDate,
  open: decStr.nullable(),
  high: decStr.nullable(),
  low: decStr.nullable(),
  last: decStr.nullable(),
  last_at: isoDate.nullable(),
  change_abs: decStr.nullable(),
  change_pct: decStr.nullable(),
  n_quotes: z.int().min(0),
  spread_avg: decStr.nullable(),
  houses: z.int().min(0),
  data_mode: DataModeSchema,
});
export const SessionStatsListSchema = z.array(SessionStatsSchema);
const HhmmSchema = z.string().regex(/^\d{2}:\d{2}$/);
export const HouseWindowSchema = z.object({
  days: z.array(z.int().min(1).max(7)).min(1),
  opens: HhmmSchema,
  closes: HhmmSchema,
});
export const HouseHoursSchema = z.object({
  name: z.string().nullable().optional(),
  city: HouseCitySchema.nullable().optional(),
  channel: HouseChannelSchema.optional(),
  tz: z.string().min(1),
  days: z.array(z.int().min(1).max(7)),
  opens: HhmmSchema,
  closes: HhmmSchema,
  schedule: z.array(HouseWindowSchema).optional(),
  verified: z.boolean().optional(),
  source_url: z.string().nullable().optional(),
  checked_at: z.string().nullable().optional(),
});
export const HouseSessionSchema = z.object({
  source_id: z.string().min(1),
  name: z.string(),
  city: HouseCitySchema.nullable(),
  tz: z.string().nullable(),
  channel: HouseChannelSchema.nullable(),
  reference: z.boolean(),
  status: SessionStatusSchema,
  opens_at: isoDate.nullable(),
  closes_at: isoDate.nullable(),
  next_change_at: isoDate.nullable(),
  data_mode: DataModeSchema,
});
export const HouseSessionsSchema = z.array(HouseSessionSchema);

export type CandleJson = z.infer<typeof CandleSchema>;
export type CandleSeriesJson = z.infer<typeof CandleSeriesSchema>;
export type SessionStatsJson = z.infer<typeof SessionStatsSchema>;
export type HouseHoursJson = z.infer<typeof HouseHoursSchema>;
export type HouseSessionJson = z.infer<typeof HouseSessionSchema>;

// Garantia estática de que o JSON validado é atribuível aos tipos do contrato.
const _candle: Candle = {} as CandleJson;
const _series: CandleSeries = {} as CandleSeriesJson;
const _stats: SessionStats = {} as SessionStatsJson;
const _hours: HouseHours = {} as HouseHoursJson;
const _session: HouseSession = {} as HouseSessionJson;
void [_candle, _series, _stats, _hours, _session];
