"use client";
/**
 * Layout compartido del panel admin — sidebar + topbar + content area.
 * Usado por todas las páginas autenticadas.
 */
import { useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { apiClient } from "@/lib/api";

const NAV = [
  { href: "/dashboard", icon: "◈", label: "Dashboard" },
  { href: "/dashboard/products", icon: "📦", label: "Productos" },
  { href: "/dashboard/orders", icon: "🛒", label: "Órdenes" },
  { href: "/dashboard/coupons", icon: "🎟", label: "Cupones" },
  { href: "/dashboard/crm", icon: "👥", label: "CRM / Leads" },
  { href: "/dashboard/whatsapp", icon: "💬", label: "WhatsApp" },
  { href: "/dashboard/ai", icon: "✨", label: "IA Generativa" },
  { href: "/dashboard/social", icon: "📱", label: "Redes Sociales" },
  { href: "/dashboard/ml", icon: "🛍️", label: "MercadoLibre" },
  { href: "/dashboard/affiliates", icon: "🔗", label: "Afiliadas" },
  { href: "/dashboard/coaches", icon: "🏋️", label: "Coaches" },
  { href: "/dashboard/blog", icon: "📝", label: "Blog & Email" },
  { href: "/dashboard/settings", icon: "⚙️", label: "Configuración" },
];

const NEON = "#00FF87";

export function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [userName, setUserName] = useState("…");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    apiClient.getMe()
      .then(u => setUserName(u.name || u.email))
      .catch(() => router.push("/login"));
  }, [router]);

  const handleLogout = async () => {
    await apiClient.logout();
    router.push("/login");
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "#06080F", color: "#E8EDFF", fontFamily: "'DM Sans', sans-serif" }}>
      {/* Sidebar */}
      <aside style={{
        width: sidebarOpen ? "220px" : "60px",
        background: "#0A0C18",
        borderRight: "1px solid #1A1F35",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.2s",
        flexShrink: 0,
        overflow: "hidden",
      }}>
        {/* Logo */}
        <div style={{ padding: "1.25rem 1rem", borderBottom: "1px solid #1A1F35", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ width: 32, height: 32, background: `linear-gradient(135deg, ${NEON}, #00F5FF)`, borderRadius: 8, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 900, fontSize: "1rem", color: "#06080F" }}>F</div>
          {sidebarOpen && <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "1rem", letterSpacing: "0.05em", color: NEON }}>FITNESS OS</span>}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "0.5rem", overflowY: "auto" }}>
          {NAV.map(item => {
            const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return (
              <a key={item.href} href={item.href} style={{
                display: "flex", alignItems: "center", gap: "0.65rem",
                padding: "0.55rem 0.75rem", borderRadius: "8px", marginBottom: "2px",
                color: active ? NEON : "#6B7494",
                background: active ? `${NEON}12` : "transparent",
                textDecoration: "none", fontSize: "0.85rem",
                transition: "all 0.15s",
                whiteSpace: "nowrap",
              }}>
                <span style={{ fontSize: "1rem", flexShrink: 0 }}>{item.icon}</span>
                {sidebarOpen && <span>{item.label}</span>}
              </a>
            );
          })}
        </nav>

        {/* User */}
        <div style={{ padding: "1rem", borderTop: "1px solid #1A1F35" }}>
          {sidebarOpen && (
            <div style={{ fontSize: "0.75rem", color: "#4A5070", marginBottom: "0.5rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {userName}
            </div>
          )}
          <button onClick={handleLogout} style={{
            width: "100%", padding: "0.4rem 0.5rem", background: "transparent",
            border: "1px solid #FF2D9C33", borderRadius: "6px", color: "#FF2D9C",
            fontSize: "0.75rem", cursor: "pointer",
          }}>
            {sidebarOpen ? "Cerrar sesión" : "×"}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Topbar */}
        <header style={{ height: 52, background: "#0A0C18", borderBottom: "1px solid #1A1F35", display: "flex", alignItems: "center", padding: "0 1.5rem", gap: "1rem", flexShrink: 0 }}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} style={{ background: "none", border: "none", color: "#6B7494", cursor: "pointer", fontSize: "1.25rem", padding: 0, lineHeight: 1 }}>
            ☰
          </button>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: "0.8rem", color: "#4A5070" }}>
            {new Date().toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" })}
          </span>
        </header>

        {/* Content */}
        <main style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
