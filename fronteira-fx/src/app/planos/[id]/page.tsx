import type { Metadata } from "next";
import { PlanView } from "@/components/planos/plan-view";
export const metadata: Metadata = { title: "Plano de execução" };
/** A rota depende do id do plano (dado de execução): não pré-renderiza; o servidor responde a cada pedido. */
export const instant = false;
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PlanView id={id} />;
}
