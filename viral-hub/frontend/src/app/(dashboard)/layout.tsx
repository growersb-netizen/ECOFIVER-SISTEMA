"use client";

/**
 * Layout del dashboard — sidebar persistente + área de contenido.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  LogOut,
} from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { Logo } from "@/components/Logo";

const NAV_ITEMS = [
  { href: "/dashboard",     label: "Dashboard",    icon: LayoutDashboard },
  { href: "/canales",       label: "Canales",      icon: Tv2 },
  { href: "/grupos",        label: "Grupos",       icon: Users },
  { href: "/biblioteca",    label: "Biblioteca",   icon: ImagePlay },
  { href: "/publicar",      label: "Publicar",     icon: Send, highlight: true },
  { href: "/cola",          label: "Cola",         icon: ListOrdered },
  { href: "/calendario",    label: "Calendario",   icon: Calendar },
  { href: "/historial",     label: "Historial",    icon: History },
  { href: "/analiticas",    label: "Analíticas",   icon: BarChart2 },
  { href: "/configuracion", label: "Configuración", icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, workspace, logout } = useAuthStore();

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)
    : "U";

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* ── Sidebar ─────────────────────────────────────────────────── */}
      <aside className="w-56 flex-shrink-0 border-r flex flex-col bg-card">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b">
          <Logo size={28} className="text-lg" />
        </div>

        {/* Navegación */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
          {NAV_ITEMS.map(({ href, label, icon: Icon, highlight }) => {
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={`
                  flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium
                  transition-colors
                  ${highlight
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  }
                `}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Footer del sidebar — usuario + workspace */}
        <div className="p-3 border-t">
          <div className="flex items-center gap-2 px-2 py-1 group">
            <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary shrink-0">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{user?.full_name ?? "—"}</p>
              <p className="text-xs text-muted-foreground truncate">{workspace?.name ?? "—"}</p>
            </div>
            <button
              onClick={() => { logout(); window.location.href = "/login"; }}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground shrink-0"
              title="Cerrar sesión"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
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
