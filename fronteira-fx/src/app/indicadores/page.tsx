import type { Metadata } from "next";
import { Indicadores } from "@/components/triangulador/indicadores";
export const metadata: Metadata = { title: "Indicadores" };
export default function Page() {
  return <Indicadores />;
}
