import type { Metadata } from "next";
import { ConnectionsScreen } from "@/components/connections/connections-screen";
export const metadata: Metadata = { title: "Conexões" };
export default function Page() {
  return <ConnectionsScreen />;
}
