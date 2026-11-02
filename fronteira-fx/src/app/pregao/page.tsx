import type { Metadata } from "next";
import { Pregao } from "@/components/pregao/pregao";
export const metadata: Metadata = { title: "Pregão" };
export default function Page() {
  return <Pregao />;
}
