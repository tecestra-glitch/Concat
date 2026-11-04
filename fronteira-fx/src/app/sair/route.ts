/**
 * POST de sair: apaga o cookie de sessão. Só POST (GET não existe aqui e responde 405), com checagem de Origin.
 */
import { signOut } from "@/lib/server/login";

export async function POST(req: Request): Promise<Response> {
  return signOut(req);
}
