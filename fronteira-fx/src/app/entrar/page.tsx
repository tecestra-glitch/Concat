import type { Metadata } from "next";
import { cookies } from "next/headers";
import { connection } from "next/server";
import { redirect } from "next/navigation";
import { SESSION_COOKIE } from "@/lib/server/session-token";
import { sessionValidNow } from "@/lib/server/login";
import { loginConfig, safeNextPath } from "@/lib/server/site-login";
import { FxCard } from "@/components/ui/fx/fx-card";
import { Input } from "@/components/ui/input";
import { SubmitButton } from "./submit-button";

export const metadata: Metadata = { title: "Entrar" };

type Search = { para?: string | string[]; erro?: string | string[] };

const MENSAGENS: Record<string, string> = {
  erro: "Não foi possível entrar. Confira a senha e tente de novo.",
  limite: "Muitas tentativas. Aguarde alguns minutos e tente de novo.",
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function EntrarPage({ searchParams }: { searchParams: Promise<Search> }) {
  // Renderiza sob demanda: a configuração (env) e o cookie não podem ser fixados no build.
  await connection();
  const config = loginConfig();
  // Sem login configurado não há o que entrar: a página só existe quando o login está ligado.
  if (config.kind !== "enabled") redirect("/");

  const params = await searchParams;
  const para = safeNextPath(first(params.para));
  const jaLogado = sessionValidNow((await cookies()).get(SESSION_COOKIE)?.value, config.secret);
  if (jaLogado) redirect(para);

  const erro = first(params.erro);
  const mensagem = erro ? MENSAGENS[erro] ?? MENSAGENS.erro : null;

  return (
    <main id="conteudo" className="grid min-h-dvh place-items-center px-4 py-10">
      <FxCard className="w-full max-w-sm p-6 sm:p-7">
        <div className="mb-6 flex items-center gap-2">
          <span aria-hidden className="inline-block size-2.5 rounded-sm bg-accent" />
          <h1 className="text-title font-semibold tracking-tight">Fronteira FX</h1>
        </div>
        <p className="mb-5 text-body text-muted">Entre para abrir o terminal.</p>

        <form method="post" action="/api/sessao/entrar" className="grid gap-4">
          <input type="hidden" name="para" value={para} />
          <div className="grid gap-1.5">
            <label htmlFor="senha" className="text-body font-medium">
              Senha
            </label>
            <Input
              id="senha"
              name="senha"
              type="password"
              autoComplete="current-password"
              required
              autoFocus
              maxLength={1024}
              spellCheck={false}
              aria-invalid={mensagem ? true : undefined}
              aria-describedby={mensagem ? "entrar-erro" : undefined}
            />
          </div>

          <label htmlFor="lembrar" className="inline-flex min-h-11 cursor-pointer items-center gap-2.5 text-body sm:min-h-8">
            <input
              id="lembrar"
              name="lembrar"
              type="checkbox"
              defaultChecked
              className="size-4 accent-[var(--accent)] focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            />
            <span>Lembrar por 30 dias</span>
          </label>

          {mensagem ? (
            <p id="entrar-erro" role="alert" className="rounded-control bg-loss-soft px-3 py-2 text-body text-loss">
              {mensagem}
            </p>
          ) : null}

          <SubmitButton />
        </form>
      </FxCard>
    </main>
  );
}
