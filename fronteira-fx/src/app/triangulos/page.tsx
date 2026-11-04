import type { Metadata } from "next";
import { Triangulos } from "@/components/triangulador/triangulos";
export const metadata: Metadata = { title: "Triângulos" };
export default function Page() {
  return <Triangulos />;
}
