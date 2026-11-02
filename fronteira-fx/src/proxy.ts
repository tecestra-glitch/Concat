/**
 * Proxy do Next 16 (antigo middleware): Basic Auth opcional em todo o app (SEC-02).
 *
 * Com `FX_BASIC_AUTH="usuario:senha"` definido no servidor, toda página e todo `/api/fx` pedem credenciais;
 * o navegador as guarda e reenvia em cada requisição da mesma origem (fetch e EventSource). Sem a variável o
 * app passa direto — e o proxy `/api/fx` só injeta a chave da API se `FX_FRONTEND_PROTECTED=1`.
 */
import { NextResponse, type NextRequest } from "next/server";
import { BASIC_REALM, basicAuthMatches, basicAuthSetting } from "@/lib/server/frontend-auth";

export function proxy(request: NextRequest): NextResponse {
  const expected = basicAuthSetting();
  if (!expected || basicAuthMatches(request.headers.get("authorization"), expected)) return NextResponse.next();
  return new NextResponse("Autenticação necessária.", {
    status: 401,
    headers: { "www-authenticate": BASIC_REALM, "cache-control": "no-store", "content-type": "text/plain; charset=utf-8" },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
