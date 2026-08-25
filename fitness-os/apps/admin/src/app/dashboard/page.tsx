"use client";
/**
 * Dashboard principal del panel de administración.
 * Muestra KPIs, últimas órdenes y estado del sistema.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

// ── Tipos simples ─────────────────────────────────────────────────
interface Stats {
  totalProducts: number;
  publishedProducts: number;
  totalOrders: number;
  pendingOrders: number;
  totalRevenue: number;
  totalLeads: number;
  newLeads: number;
  totalCustomers: number;
}

// ── Componente KPI Card ───────────────────────────────────────────
function KPICard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color: string }) {
  return (
    <div style={{
      background: "#0D0F1A",
      border: `1px solid ${color}22`,
      borderLeft: `3px solid ${color}`,
      borderRadius: "12px",
      padding: "1.25rem 1.5rem",
    }}>
      <p style={{ color: "#4A5070", fontSize: "0.75rem", letterSpacing: "0.1em", textTransform: "uppercase", margin: "0 0 0.5rem" }}>
        {label}
      </p>
      <p style={{ color: "#E8EDFF", fontSize: "2rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, margin: 0, lineHeight: 1 }}>
        {value}
      </p>
      {sub && <p style={{ color: "#4A5070", fontSize: "0.8rem", margin: "0.25rem 0 0" }}>{sub}</p>}
    </div>
  );
}

// ── Sidebar navigation item ───────────────────────────────────────
function NavItem({ label, href, active }: { label: string; href: string; active?: boolean }) {
  return (
    <a href={href} style={{
      display: "block",
      padding: "0.6rem 1rem",
      borderRadius: "8px",
      color: active ? "#00FF87" : "#A0AAC8",
      background: active ? "rgba(0,255,135,0.1)" : "transparent",
      textDecoration: "none",
      fontSize: "0.9rem",
      fontWeight: active ? 600 : 400,
      borderLeft: active ? "2px solid #00FF87" : "2px solid transparent",
      transition: "all 0.15s",
    }}>
      {label}
    </a>
  );
}

// ── Dashboard principal ───────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [user, setUser] = useState<{ name: string; email: string; role: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("fitness_access_token");
    if (!token) { router.push("/login"); return; }

    // Cargar usuario y stats básicas
    const apiUrl = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
    Promise.all([
      fetch(`${apiUrl}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } }),
    ])
      .then(async ([meRes]) => {
        if (!meRes.ok) { router.push("/login"); return; }
        const meData = await meRes.json() as { user: { name: string; email: string; role: string } };
        setUser(meData.user);

        // Stats mock mientras se conecta la DB real
        setStats({
          totalProducts: 0,
          publishedProducts: 0,
          totalOrders: 0,
          pendingOrders: 0,
          totalRevenue: 0,
          totalLeads: 0,
          newLeads: 0,
          totalCustomers: 0,
        });
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#07080F", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: "#00FF87", fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", letterSpacing: "0.1em" }}>
          CARGANDO...
        </p>
      </div>
    );
  }

  const formatCurrency = (n: number) =>
    new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 }).format(n);

  return (
    <div style={{
      display: "flex",
      minHeight: "100vh",
      background: "#07080F",
      color: "#E8EDFF",
      fontFamily: "'DM Sans', system-ui, sans-serif",
    }}>
      {/* ── Sidebar ─────────────────────────────────────────── */}
      <aside style={{
        width: "220px",
        flexShrink: 0,
        background: "#0A0B14",
        borderRight: "1px solid #1E2240",
        display: "flex",
        flexDirection: "column",
        padding: "1.5rem 1rem",
        position: "sticky",
        top: 0,
        height: "100vh",
      }}>
        {/* Brand */}
        <div style={{ marginBottom: "2rem", paddingLeft: "0.5rem" }}>
          <p style={{ fontSize: "0.65rem", letterSpacing: "0.2em", color: "#00F5FF", textTransform: "uppercase", marginBottom: "2px" }}>
            FITNESS BUSINESS OS
          </p>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem", fontWeight: 700, color: "#00FF87", margin: 0 }}>
            PANEL ADMIN
          </p>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
          <NavItem label="📊 Dashboard" href="/dashboard" active />
          <NavItem label="📦 Productos" href="/dashboard/products" />
          <NavItem label="🛒 Órdenes" href="/dashboard/orders" />
          <NavItem label="👥 CRM / Leads" href="/dashboard/crm" />
          <NavItem label="💬 WhatsApp" href="/dashboard/whatsapp" />
          <NavItem label="🤖 IA" href="/dashboard/ai" />
          <NavItem label="📱 Redes Sociales" href="/dashboard/social" />
          <NavItem label="🏪 MercadoLibre" href="/dashboard/mercadolibre" />
          <NavItem label="🔗 Afiliadas" href="/dashboard/affiliates" />
          <NavItem label="🏋️ Coaches" href="/dashboard/coaches" />
          <NavItem label="⚙️ Configuración" href="/dashboard/settings" />
        </nav>

        {/* User */}
        <div style={{ borderTop: "1px solid #1E2240", paddingTop: "1rem", marginTop: "1rem" }}>
          <p style={{ fontSize: "0.8rem", color: "#E8EDFF", fontWeight: 600, margin: "0 0 2px" }}>{user?.name}</p>
          <p style={{ fontSize: "0.72rem", color: "#4A5070", margin: "0 0 0.75rem" }}>{user?.role}</p>
          <button
            onClick={() => { localStorage.clear(); window.location.href = "/login"; }}
            style={{ fontSize: "0.75rem", color: "#4A5070", background: "none", border: "none", cursor: "pointer", padding: "0" }}
          >
            Cerrar sesión →
          </button>
        </div>
      </aside>

      {/* ── Contenido principal ─────────────────────────────── */}
      <main style={{ flex: 1, padding: "2rem", overflowX: "auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "2rem" }}>
          <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2rem", fontWeight: 800, color: "#E8EDFF", margin: 0 }}>
            DASHBOARD
          </h1>
          <p style={{ color: "#4A5070", fontSize: "0.85rem", marginTop: "4px" }}>
            Vista general del negocio · {new Date().toLocaleDateString("es-AR", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
          </p>
        </div>

        {/* KPIs */}
        {stats && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
            <KPICard label="Productos" value={stats.totalProducts} sub={`${stats.publishedProducts} publicados`} color="#00FF87" />
            <KPICard label="Órdenes" value={stats.totalOrders} sub={`${stats.pendingOrders} pendientes`} color="#00F5FF" />
            <KPICard label="Revenue Total" value={formatCurrency(stats.totalRevenue)} color="#FFE234" />
            <KPICard label="Leads" value={stats.totalLeads} sub={`${stats.newLeads} nuevos`} color="#FF2D9C" />
            <KPICard label="Clientes" value={stats.totalCustomers} color="#00FF87" />
          </div>
        )}

        {/* Estado del sistema */}
        <div style={{
          background: "#0D0F1A",
          border: "1px solid #1E2240",
          borderRadius: "12px",
          padding: "1.5rem",
          marginBottom: "2rem",
        }}>
          <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem", color: "#E8EDFF", margin: "0 0 1rem", letterSpacing: "0.05em" }}>
            ESTADO DEL SISTEMA
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem" }}>
            {[
              { label: "API", status: "✅ Online" },
              { label: "Base de datos", status: "🟡 Verificando..." },
              { label: "Redis / Queue", status: "🟡 Verificando..." },
              { label: "Fulfillment Worker", status: "🟡 Por configurar" },
              { label: "AI Worker", status: "🟡 Por configurar" },
              { label: "WhatsApp", status: "🔴 Sin configurar" },
              { label: "MercadoPago", status: "🔴 Sin configurar" },
              { label: "MercadoLibre", status: "🔴 Sin conectar" },
              { label: "Cloudflare R2", status: "🔴 Sin configurar" },
              { label: "Resend Email", status: "🔴 Sin configurar" },
            ].map((item) => (
              <div key={item.label} style={{ background: "#070810", border: "1px solid #1E2240", borderRadius: "8px", padding: "0.75rem" }}>
                <p style={{ color: "#4A5070", fontSize: "0.7rem", letterSpacing: "0.05em", textTransform: "uppercase", margin: "0 0 4px" }}>{item.label}</p>
                <p style={{ color: "#E8EDFF", fontSize: "0.8rem", margin: 0 }}>{item.status}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Fases del proyecto */}
        <div style={{
          background: "#0D0F1A",
          border: "1px solid #1E2240",
          borderRadius: "12px",
          padding: "1.5rem",
        }}>
          <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem", color: "#E8EDFF", margin: "0 0 1rem", letterSpacing: "0.05em" }}>
            FASES DE IMPLEMENTACIÓN
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {[
              { num: "00", label: "Arquitectura base", done: true },
              { num: "01", label: "Auth, Tenants, RBAC", done: true },
              { num: "02", label: "Productos y Catálogo", done: true },
              { num: "03", label: "Ecommerce & Checkout", done: true },
              { num: "04", label: "Fulfillment Digital", done: true },
              { num: "05", label: "IA — Generación de Contenido", done: true },
              { num: "06", label: "CRM — Leads y Conversaciones", done: true },
              { num: "07", label: "WhatsApp Business", done: true },
              { num: "08", label: "MercadoLibre", done: true },
              { num: "09", label: "Redes Sociales", done: true },
              { num: "10", label: "Blog & Email Marketing", done: false },
              { num: "11", label: "Catálogo 200 Productos", done: true },
              { num: "12", label: "Programa de Afiliadas", done: true },
              { num: "13", label: "Portal de Coaches", done: true },
              { num: "14", label: "Internacionalización", done: false },
              { num: "15", label: "Hardening y QA", done: false },
            ].map((phase) => (
              <div key={phase.num} style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                padding: "0.5rem 0.75rem",
                borderRadius: "6px",
                background: phase.done ? "rgba(0,255,135,0.05)" : "transparent",
              }}>
                <span style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontSize: "0.8rem",
                  color: phase.done ? "#00FF87" : "#4A5070",
                  fontWeight: 700,
                  minWidth: "32px",
                }}>
                  {phase.num}
                </span>
                <span style={{ flex: 1, fontSize: "0.875rem", color: phase.done ? "#E8EDFF" : "#4A5070" }}>
                  {phase.label}
                </span>
                <span style={{ fontSize: "0.75rem", color: phase.done ? "#00FF87" : "#4A5070" }}>
                  {phase.done ? "✅ Listo" : "⏳ Pendiente"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
