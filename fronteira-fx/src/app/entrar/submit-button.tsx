"use client";
import * as React from "react";
import { useFormStatus } from "react-dom";
import { Button } from "@/components/ui/button";

/** Botão do formulário de entrada: mostra o estado enquanto o servidor confere a senha (há atraso fixo). */
export function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" className="w-full max-sm:h-11" disabled={pending} aria-busy={pending || undefined}>
      {pending ? "Entrando…" : "Entrar"}
    </Button>
  );
}
