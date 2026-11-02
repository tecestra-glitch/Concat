import type { Metadata } from "next";
import { KnowledgeSearch } from "@/components/knowledge/knowledge-search";
export const metadata: Metadata = { title: "Conhecimento" };
export default function Page() {
  return <KnowledgeSearch />;
}
