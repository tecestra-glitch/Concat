import type { Metadata } from "next";
import { Overview } from "@/components/overview";

export const metadata: Metadata = { title: "Visão geral" };

export default function Page() {
  return <Overview />;
}
