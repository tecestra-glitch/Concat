import type { Metadata } from "next";
import { Noticias } from "@/components/triangulador/noticias";
export const metadata: Metadata = { title: "Notícias" };
export default function Page() {
  return <Noticias />;
}
