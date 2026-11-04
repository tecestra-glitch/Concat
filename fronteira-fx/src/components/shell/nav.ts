import { Activity, BellRing, BookOpenText, Brain, Building2, Calculator, CandlestickChart, Database, LayoutDashboard, Library, Settings, Sparkles, TrendingUp, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Início", short: "Início", icon: LayoutDashboard },
  { href: "/mercados", label: "Mercados", short: "Mercados", icon: CandlestickChart },
  { href: "/pregao", label: "Pregão", short: "Pregão", icon: TrendingUp },
  { href: "/oportunidades", label: "Oportunidades", short: "Oportun.", icon: Sparkles },
  { href: "/simulador", label: "Simulador", short: "Simular", icon: Calculator },
  { href: "/contas", label: "Contas e cartões", short: "Contas", icon: Building2 },
  { href: "/fontes", label: "Fontes", short: "Fontes", icon: Database },
  { href: "/monitor", label: "Monitor ao vivo", short: "Monitor", icon: Activity },
  { href: "/alertas", label: "Alertas", short: "Alertas", icon: BellRing },
  { href: "/diario", label: "Diário", short: "Diário", icon: BookOpenText },
  { href: "/conhecimento", label: "Conhecimento", short: "Saber", icon: Library },
  { href: "/memoria", label: "Memória", short: "Memória", icon: Brain },
  { href: "/configuracoes", label: "Configurações", short: "Config.", icon: Settings },
];

/** Barra inferior do celular: 4 itens fixos; todos os outros ficam no menu «Mais». */
export const MOBILE_PRIMARY = 4;

export function splitNav(nav: NavItem[] = NAV): { primary: NavItem[]; more: NavItem[] } {
  return { primary: nav.slice(0, MOBILE_PRIMARY), more: nav.slice(MOBILE_PRIMARY) };
}

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
