import type { Metadata } from "next";
import { Simulator } from "@/components/simulator/simulator";
import { PageHeader } from "@/components/shell/page-header";
export const metadata: Metadata = { title: "Simulador" };
export default function Page() {
  return (
    <div className="space-y-4">
      <PageHeader title="Simulador de rotas" description="Compare rotas e ciclos entre contas e dinheiro físico. taxa efetiva = crédito líquido ÷ débito total · lucro = valor final − capital · ROI = lucro ÷ capital." />
      <Simulator />
    </div>
  );
}
