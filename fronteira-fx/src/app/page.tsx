import type { Metadata } from "next";
import { Home } from "@/components/home/home";

export const metadata: Metadata = { title: "Início" };

export default function Page() {
  return <Home />;
}
