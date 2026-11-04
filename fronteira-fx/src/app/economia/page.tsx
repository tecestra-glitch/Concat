import type { Metadata } from "next";
import { Economia } from "@/components/economia/economia";
export const metadata: Metadata = { title: "Economia e cripto" };
export default function Page() {
  return <Economia />;
}
