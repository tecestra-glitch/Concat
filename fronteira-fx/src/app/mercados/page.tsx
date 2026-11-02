import type { Metadata } from "next";
import { Markets } from "@/components/markets/markets";
export const metadata: Metadata = { title: "Mercados" };
export default function Page() {
  return <Markets />;
}
