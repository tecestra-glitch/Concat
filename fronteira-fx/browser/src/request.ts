import { z } from "zod";

// Only these keys are accepted. There is deliberately no URL field: the function only ever opens the fixed page.
export const WesternUnionRequest = z.strictObject({
  amount_brl: z
    .string()
    .regex(/^\d{1,6}(\.\d{1,2})?$/, "use decimal com ponto, até 2 casas")
    .refine((v) => {
      const n = Number(v);
      return n >= 1 && n <= 100000;
    }, "fora da faixa 1 a 100000"),
  payment: z.enum(["pix", "bank_transfer", "card"]),
  receive: z.enum(["bank_account", "cash_pickup"]),
  bank: z
    .string()
    .trim()
    .regex(/^[\p{L}\p{N} .'-]{1,60}$/u, "texto curto e simples")
    .optional(),
  screenshot: z.boolean().optional(),
});

export type WesternUnionRequest = z.infer<typeof WesternUnionRequest>;
