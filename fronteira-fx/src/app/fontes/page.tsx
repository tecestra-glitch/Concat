import type { Metadata } from "next";
import { Sources } from "@/components/sources";
export const metadata: Metadata = { title: "Fontes" };
export default function Page() {
  return <Sources />;
}
