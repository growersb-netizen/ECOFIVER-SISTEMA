"use client";
/**
 * Layout compartido del panel admin — sidebar + topbar + content area.
 * Responsivo: en mobile el sidebar es un drawer overlay (full-width).
 * En desktop es colapsable (220px ↔ 60px).
 */
import { useState, useEffect, useCallback, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { apiClient } from "@/lib/api";

const NAV = [
  { href: "/dashboard",              icon: "◈",  label: "Dashboard" },
  { href: "/dashboard/products",     icon: "📦", label: "Productos" },
  { href: "/dashboard/orders",       icon: "🛒", label: "Órdenes" },
  { href: "/dashboard/coupons",      icon: "🎟", label: "Cupones" },
  { href: "/dashboard/crm",          icon: "👥", label: "CRM / Leads" },
  { href: "/dashboard/whatsapp",     icon: "💬", label: "WhatsApp" },
  { href: "/dashboard/ai",           icon: "✨", label: "IA Generativa" },
  { href: "/dashboard/social",       icon: "📱", label: "Redes Sociales" },
  { href: "/dashboard/mercadolibre", icon: "🛍️", label: "MercadoLibre" },
  { href: "/dashboard/affiliates",   icon: "🔗", label: "Afiliadas" },
  { href: "/dashboard/coaches",      icon: "🏋️", label: "Coaches" },
  { href: "/dashboard/blog",         icon: "📝", label: "Blog & Email" },
  { href: "/dashboard/settings",     icon: "⚙️", label: "Configuración" },
];

const NEON = "#00FF87";
const PINK = "#FF2D9C";

function useIsMobile() {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const check = () => setMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return mobile;
}

export function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isMobile = useIsMobile();
  const [userName, setUserName] = useState("…");
  // Desktop: true = 220px expandido, false = 60px colapsado
  // Mobile: true = drawer abierto, false = oculto
  const [open, setOpen] = useState(false);

  // En desktop arrancamos con el sidebar expandido
  useEffect(() => {
    if (!isMobile) setOpen(true);
  }, [isMobile]);

  useEffect(() => {
    apiClient.getMe()
      .then(u => setUserName(u.name || u.email))
      .catch(() => { window.location.href = "/login"; });
  }, []);

  const handleLogout = async () => {
    await apiClient.logout();
    window.location.href = "/login";
  };

  const closeIfMobile = useCallback(() => {
    if (isMobile) setOpen(false);
  }, [isMobile]);

  // Sidebar width para desktop
  const sidebarW = isMobile ? "280px" : open ? "220px" : "60px";

  return (
    <div style={{ display: "flex", height: "100dvh", background: "#06080F", color: "#E8EDFF", fontFamily: "'DM Sans', sans-serif", overflow: "hidden" }}>

      {/* ── Backdrop mobile ─────────────────────────────────────── */}
      {isMobile && open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)",
            zIndex: 40, backdropFilter: "blur(2px)",
          }}
        />
      )}

      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside style={{
        position: isMobile ? "fixed" : "relative",
        top: 0, left: 0, bottom: 0,
        width: sidebarW,
        background: "#0A0C18",
        borderRight: "1px solid #1A1F35",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.22s ease, transform 0.22s ease",
        flexShrink: 0,
        overflow: "hidden",
        zIndex: isMobile ? 50 : 1,
        transform: isMobile && !open ? "translateX(-100%)" : "translateX(0)",
      }}>
        {/* Logo */}
        <div style={{
          padding: "1.1rem 1rem",
          borderBottom: "1px solid #1A1F35",
          display: "flex", alignItems: "center", gap: "0.75rem",
          flexShrink: 0,
        }}>
          <div style={{
            width: 32, height: 32,
            background: `linear-gradient(135deg, ${NEON}, #00F5FF)`,
            borderRadius: 8, flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontWeight: 900, fontSize: "1rem", color: "#06080F",
          }}>F</div>
          {(open || isMobile) && (
            <span style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 700, fontSize: "1rem",
              letterSpacing: "0.05em", color: NEON,
              whiteSpace: "nowrap",
            }}>FITNESS OS</span>
          )}
          {/* Botón cerrar en mobile */}
          {isMobile && (
            <button
              onClick={() => setOpen(false)}
              style={{
                marginLeft: "auto", background: "none", border: "none",
                color: "#6B7494", fontSize: "1.3rem", cursor: "pointer",
                lineHeight: 1, padding: "4px",
              }}
              aria-label="Cerrar menú"
            >×</button>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "0.5rem", overflowY: "auto" }}>
          {NAV.map(item => {
            const active = pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return (
              <a
                key={item.href}
                href={item.href}
                onClick={closeIfMobile}
                style={{
                  display: "flex", alignItems: "center",
                  gap: (open || isMobile) ? "0.65rem" : 0,
                  justifyContent: (!open && !isMobile) ? "center" : "flex-start",
                  padding: (open || isMobile) ? "0.65rem 0.75rem" : "0.65rem 0",
                  borderRadius: "8px", marginBottom: "2px",
                  color: active ? NEON : "#6B7494",
                  background: active ? `${NEON}12` : "transparent",
                  textDecoration: "none", fontSize: "0.875rem",
                  transition: "all 0.15s",
                  whiteSpace: "nowrap",
                  minHeight: 44,  // touch target
                }}
              >
                <span style={{ fontSize: "1.1rem", flexShrink: 0 }}>{item.icon}</span>
                {(open || isMobile) && <span>{item.label}</span>}
              </a>
            );
          })}
        </nav>

        {/* User + logout */}
        <div style={{ padding: "1rem", borderTop: "1px solid #1A1F35", flexShrink: 0 }}>
          {(open || isMobile) && (
            <div style={{
              fontSize: "0.75rem", color: "#4A5070",
              marginBottom: "0.5rem",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {userName}
            </div>
          )}
          <button
            onClick={handleLogout}
            style={{
              width: "100%", padding: "0.5rem 0.5rem",
              background: "transparent",
              border: `1px solid ${PINK}33`, borderRadius: "6px",
              color: PINK, fontSize: "0.75rem", cursor: "pointer",
              minHeight: 40,
            }}
          >
            {(open || isMobile) ? "Cerrar sesión" : "×"}
          </button>
        </div>
      </aside>

      {/* ── Main (topbar + content) ─────────────────────────────── */}
      <div style={{
        flex: 1, display: "flex", flexDirection: "column",
        overflow: "hidden", minWidth: 0,
      }}>
        {/* Topbar */}
        <header style={{
          height: 52, background: "#0A0C18",
          borderBottom: "1px solid #1A1F35",
          display: "flex", alignItems: "center",
          padding: "0 1rem", gap: "0.75rem",
          flexShrink: 0, zIndex: 10,
        }}>
          {/* Hamburger */}
          <button
            onClick={() => setOpen(o => !o)}
            style={{
              background: "none", border: "none",
              color: "#6B7494", cursor: "pointer",
              fontSize: "1.3rem", padding: "4px",
              lineHeight: 1, flexShrink: 0, minWidth: 36, minHeight: 36,
            }}
            aria-label="Toggle menú"
          >
            {isMobile ? "☰" : open ? "◁" : "▷"}
          </button>

          {/* Título de sección actual */}
          <span style={{
            fontSize: "0.85rem", fontWeight: 600, color: "#A0AAC8",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {NAV.find(n => pathname === n.href || (n.href !== "/dashboard" && pathname.startsWith(n.href)))?.label ?? "Dashboard"}
          </span>

          <div style={{ flex: 1 }} />

          {/* Fecha — oculta en mobile muy pequeño */}
          <span style={{
            fontSize: "0.75rem", color: "#4A5070",
            display: isMobile ? "none" : "block",
            whiteSpace: "nowrap", flexShrink: 0,
          }}>
            {new Date().toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" })}
          </span>
        </header>

        {/* Content */}
        <main style={{
          flex: 1, overflowY: "auto",
          padding: isMobile ? "1rem 0.75rem" : "1.5rem",
        }}>
          {children}
        </main>
      </div>
    </div>
  );
}
