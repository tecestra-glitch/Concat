import type { Metadata } from "next";
import { Opportunities } from "@/components/opportunities/opportunities";
export const metadata: Metadata = { title: "Oportunidades" };
export default function Page() {
  return <Opportunities />;
}
