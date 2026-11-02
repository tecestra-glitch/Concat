import type { Metadata } from "next";
import { Alerts } from "@/components/monitor/alerts";
export const metadata: Metadata = { title: "Alertas" };
export default function Page() {
  return <Alerts />;
}
