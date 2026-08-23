/**
 * Layout del dashboard — sidebar persistente + área de contenido.
 * El sidebar nunca se re-renderiza al navegar entre páginas.
 */

import Link from "next/link";
import {
  LayoutDashboard,
  Tv2,
  Users,
  ImagePlay,
  Send,
  ListOrdered,
  Calendar,
  History,
  BarChart2,
  Settings,
  Zap,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard",     label: "Dashboard",   icon: LayoutDashboard },
  { href: "/canales",       label: "Canales",     icon: Tv2 },
  { href: "/grupos",        label: "Grupos",      icon: Users },
  { href: "/biblioteca",    label: "Biblioteca",  icon: ImagePlay },
  { href: "/publicar",      label: "Publicar",    icon: Send,     highlight: true },
  { href: "/cola",          label: "Cola",        icon: ListOrdered },
  { href: "/calendario",    label: "Calendario",  icon: Calendar },
  { href: "/historial",     label: "Historial",   icon: History },
  { href: "/analiticas",    label: "Analíticas",  icon: BarChart2 },
  { href: "/configuracion", label: "Configuración", icon: Settings },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* ── Sidebar ─────────────────────────────────────────────────── */}
      <aside className="w-56 flex-shrink-0 border-r flex flex-col bg-card">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b">
          <Zap className="h-5 w-5 text-primary mr-2" />
          <span className="font-bold text-lg tracking-tight">Viral Hub</span>
        </div>

        {/* Navegación */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon, highlight }) => (
            <Link
              key={href}
              href={href}
              className={`
                flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium
                transition-colors hover:bg-accent hover:text-accent-foreground
                ${highlight ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground" : "text-muted-foreground"}
              `}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          ))}
        </nav>

        {/* Footer del sidebar */}
        <div className="p-3 border-t">
          <div className="flex items-center gap-2 px-2 py-1">
            <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center text-xs font-semibold">
              U
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">Usuario</p>
              <p className="text-xs text-muted-foreground truncate">workspace</p>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Área principal ───────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
