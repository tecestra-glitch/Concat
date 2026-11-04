/**
 * POST do formulário de entrada. A lógica (CSRF por Origin, limite de tentativas, atraso fixo, cookie assinado)
 * está em `src/lib/server/login.ts`. Responde sempre 303 para `/entrar` ou para o destino.
 */
import { attemptLogin } from "@/lib/server/login";

export async function POST(req: Request): Promise<Response> {
  return attemptLogin(req);
}
