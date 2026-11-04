import type { Metadata } from "next";
import { MercadoGlobal } from "@/components/triangulador/mercado-global";
export const metadata: Metadata = { title: "Mercado global" };
export default function Page() {
  return <MercadoGlobal />;
}
