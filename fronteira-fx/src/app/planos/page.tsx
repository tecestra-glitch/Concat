import type { Metadata } from "next";
import { PlansList } from "@/components/planos/plans-list";
export const metadata: Metadata = { title: "Planos" };
export default function Page() {
  return <PlansList />;
}
