import { BookOpenText, Building2, CandlestickChart, Database, LayoutDashboard, Settings, Sparkles, Calculator, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Visão geral", short: "Início", icon: LayoutDashboard },
  { href: "/mercados", label: "Mercados", short: "Mercados", icon: CandlestickChart },
  { href: "/oportunidades", label: "Oportunidades", short: "Oportun.", icon: Sparkles },
  { href: "/simulador", label: "Simulador", short: "Simular", icon: Calculator },
  { href: "/contas", label: "Contas e cartões", short: "Contas", icon: Building2 },
  { href: "/fontes", label: "Fontes", short: "Fontes", icon: Database },
  { href: "/diario", label: "Diário", short: "Diário", icon: BookOpenText },
  { href: "/configuracoes", label: "Configurações", short: "Config.", icon: Settings },
];
