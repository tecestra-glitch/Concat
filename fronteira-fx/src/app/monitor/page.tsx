import type { Metadata } from "next";
import { Monitor } from "@/components/monitor/monitor";
export const metadata: Metadata = { title: "Monitor ao vivo" };
export default function Page() {
  return <Monitor />;
}
