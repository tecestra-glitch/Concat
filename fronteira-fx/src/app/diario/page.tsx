import type { Metadata } from "next";
import { Journal } from "@/components/journal";
export const metadata: Metadata = { title: "Diário" };
export default function Page() {
  return <Journal />;
}
