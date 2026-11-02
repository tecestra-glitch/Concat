import type { Metadata } from "next";
import { Accounts } from "@/components/accounts";
export const metadata: Metadata = { title: "Contas e cartões" };
export default function Page() {
  return <Accounts />;
}
