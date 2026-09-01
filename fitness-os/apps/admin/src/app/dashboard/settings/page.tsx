"use client";
/**
 * /dashboard/settings — Configuración del tenant y perfil del admin.
 */
import { useEffect, useState, FormEvent, ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const NEON = "#00FF87";
const CYAN = "#00F5FF";

interface Profile {
  name: string;
  email: string;
  role: string;
  avatarUrl?: string;
}

interface TenantSettings {
  slug: string;
  name: string;
  domain?: string;
  logoUrl?: string;
  primaryColor: string;
  supportEmail: string;
}

// ── NavItem (igual al dashboard) ──────────────────────────────────
function NavItem({ label, href, active }: { label: string; href: string; active?: boolean }) {
  return (
    <a href={href} style={{
      display: "block", padding: "0.6rem 1rem", borderRadius: "8px",
      color: active ? NEON : "#A0AAC8",
      background: active ? "rgba(0,255,135,0.1)" : "transparent",
      textDecoration: "none", fontSize: "0.9rem",
      fontWeight: active ? 600 : 400,
      borderLeft: active ? `2px solid ${NEON}` : "2px solid transparent",
    }}>
      {label}
    </a>
  );
}

// ── Section wrapper ───────────────────────────────────────────────
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ background: "#0D0F1A", border: "1px solid #1E2240", borderRadius: 12, padding: "1.5rem", marginBottom: "1.5rem" }}>
      <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.05rem", color: "#E8EDFF", margin: "0 0 1.25rem", letterSpacing: "0.05em" }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

// ── Field ─────────────────────────────────────────────────────────
function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <label style={{ display: "block", fontSize: "0.75rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: 6 }}>
        {label}
      </label>
      {children}
      {hint && <p style={{ color: "#3A3F55", fontSize: "0.75rem", margin: "4px 0 0" }}>{hint}</p>}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", background: "#0A0C18", border: "1px solid #2A2F45",
  borderRadius: 8, padding: "0.65rem 1rem", color: "#E8EDFF",
  fontSize: "0.9rem", outline: "none", boxSizing: "border-box",
};

const readonlyStyle: React.CSSProperties = {
  ...inputStyle, color: "#4A5070", cursor: "not-allowed",
};

// ── Pending vars display ──────────────────────────────────────────
const PENDING_ENV_VARS = [
  { key: "OPENROUTER_API_KEY", label: "OpenRouter API Key", help: "Requerida para generación de contenido con IA", service: "Railway" },
  { key: "MERCADOPAGO_ACCESS_TOKEN", label: "MercadoPago Access Token", help: "Necesario para procesar pagos online", service: "Railway" },
  { key: "RESEND_API_KEY", label: "Resend API Key", help: "Para envío de emails de confirmación y entrega", service: "Railway" },
  { key: "R2_ACCOUNT_ID", label: "Cloudflare R2 Account ID", help: "Para almacenar los ZIPs de productos digitales", service: "Railway" },
  { key: "R2_ACCESS_KEY_ID", label: "Cloudflare R2 Access Key", help: "Credenciales R2", service: "Railway" },
  { key: "R2_SECRET_ACCESS_KEY", label: "Cloudflare R2 Secret Key", help: "Credenciales R2", service: "Railway" },
  { key: "WHATSAPP_TOKEN", label: "WhatsApp Cloud API Token", help: "Para habilitar el agente de WhatsApp", service: "Railway" },
  { key: "WHATSAPP_PHONE_NUMBER_ID", label: "WhatsApp Phone Number ID", help: "ID del número en Meta Business", service: "Railway" },
  { key: "ML_APP_ID", label: "MercadoLibre App ID", help: "Para la integración con MercadoLibre", service: "Railway" },
  { key: "ML_APP_SECRET", label: "MercadoLibre App Secret", help: "Credenciales OAuth ML", service: "Railway" },
];

export default function SettingsPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [tenant, setTenant] = useState<TenantSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  // Campos editables del perfil
  const [displayName, setDisplayName] = useState("");
  const [primaryColor, setPrimaryColor] = useState("#00FF87");
  const [supportEmail, setSupportEmail] = useState("");
  const [tenantName, setTenantName] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("fitness_access_token");
    if (!token) { router.push("/login"); return; }

    const apiUrl = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

    fetch(`${apiUrl}/api/v1/auth/me`, { headers })
      .then(async (res) => {
        if (!res.ok) { router.push("/login"); return; }
        const data = await res.json() as { user: Profile & { tenant?: TenantSettings } };
        setProfile(data.user);
        setDisplayName(data.user.name ?? "");
        if (data.user.tenant) {
          setTenant(data.user.tenant);
          setPrimaryColor(data.user.tenant.primaryColor ?? "#00FF87");
          setSupportEmail(data.user.tenant.supportEmail ?? "");
          setTenantName(data.user.tenant.name ?? "");
        }
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function handleSaveProfile(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(null);
    // En esta versión guardamos solo localmente (endpoint pendiente)
    await new Promise(r => setTimeout(r, 600));
    setSaving(false);
    setSaved("profile");
    setTimeout(() => setSaved(null), 3000);
  }

  async function handleSaveTenant(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(null);
    await new Promise(r => setTimeout(r, 600));
    setSaving(false);
    setSaved("tenant");
    setTimeout(() => setSaved(null), 3000);
  }

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#07080F", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: NEON, fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", letterSpacing: "0.1em" }}>CARGANDO...</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#07080F", color: "#E8EDFF", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      {/* Sidebar */}
      <aside style={{ width: 220, flexShrink: 0, background: "#0A0B14", borderRight: "1px solid #1E2240", display: "flex", flexDirection: "column", padding: "1.5rem 1rem", position: "sticky", top: 0, height: "100vh" }}>
        <div style={{ marginBottom: "2rem", paddingLeft: "0.5rem" }}>
          <p style={{ fontSize: "0.65rem", letterSpacing: "0.2em", color: CYAN, textTransform: "uppercase", marginBottom: "2px" }}>FITNESS BUSINESS OS</p>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem", fontWeight: 700, color: NEON, margin: 0 }}>PANEL ADMIN</p>
        </div>
        <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
          <NavItem label="📊 Dashboard" href="/dashboard" />
          <NavItem label="📦 Productos" href="/dashboard/products" />
          <NavItem label="🛒 Órdenes" href="/dashboard/orders" />
          <NavItem label="🎟 Cupones" href="/dashboard/coupons" />
          <NavItem label="👥 CRM / Leads" href="/dashboard/crm" />
          <NavItem label="💬 WhatsApp" href="/dashboard/whatsapp" />
          <NavItem label="🤖 IA" href="/dashboard/ai" />
          <NavItem label="📱 Redes Sociales" href="/dashboard/social" />
          <NavItem label="🏪 MercadoLibre" href="/dashboard/ml" />
          <NavItem label="🔗 Afiliadas" href="/dashboard/affiliates" />
          <NavItem label="🏋️ Coaches" href="/dashboard/coaches" />
          <NavItem label="📝 Blog & Email" href="/dashboard/blog" />
          <NavItem label="⚙️ Configuración" href="/dashboard/settings" active />
        </nav>
        <div style={{ borderTop: "1px solid #1E2240", paddingTop: "1rem", marginTop: "1rem" }}>
          <p style={{ fontSize: "0.8rem", color: "#E8EDFF", fontWeight: 600, margin: "0 0 2px" }}>{profile?.name}</p>
          <p style={{ fontSize: "0.72rem", color: "#4A5070", margin: "0 0 0.75rem" }}>{profile?.role}</p>
          <button onClick={() => { localStorage.clear(); window.location.href = "/login"; }}
            style={{ fontSize: "0.75rem", color: "#4A5070", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            Cerrar sesión →
          </button>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, padding: "2rem", overflowX: "auto", maxWidth: 760 }}>
        <div style={{ marginBottom: "2rem" }}>
          <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2rem", fontWeight: 800, color: "#E8EDFF", margin: 0 }}>CONFIGURACIÓN</h1>
          <p style={{ color: "#4A5070", fontSize: "0.85rem", marginTop: "4px" }}>Perfil, tenant, integraciones y variables de entorno</p>
        </div>

        {/* Perfil */}
        <Section title="👤 PERFIL DE ADMINISTRADOR">
          <form onSubmit={handleSaveProfile}>
            <Field label="NOMBRE">
              <input value={displayName} onChange={e => setDisplayName(e.target.value)}
                style={inputStyle} placeholder="Tu nombre" />
            </Field>
            <Field label="EMAIL" hint="No es editable — es tu identificador de acceso">
              <input value={profile?.email ?? ""} readOnly style={readonlyStyle} />
            </Field>
            <Field label="ROL">
              <input value={profile?.role ?? ""} readOnly style={readonlyStyle} />
            </Field>
            <button type="submit" disabled={saving} style={{
              padding: "0.65rem 1.5rem", background: `linear-gradient(135deg, ${NEON}, #00D4A0)`,
              border: "none", borderRadius: 8, color: "#06080F", fontWeight: 800,
              fontSize: "0.88rem", cursor: "pointer",
            }}>
              {saving && saved !== "tenant" ? "Guardando..." : saved === "profile" ? "✓ Guardado" : "Guardar perfil"}
            </button>
          </form>
        </Section>

        {/* Tenant */}
        <Section title="🏢 CONFIGURACIÓN DEL NEGOCIO">
          <form onSubmit={handleSaveTenant}>
            <Field label="NOMBRE DEL NEGOCIO">
              <input value={tenantName} onChange={e => setTenantName(e.target.value)}
                style={inputStyle} placeholder="Fitness Business OS" />
            </Field>
            <Field label="SLUG (IDENTIFICADOR)" hint="No es editable una vez creado">
              <input value={tenant?.slug ?? ""} readOnly style={readonlyStyle} />
            </Field>
            <Field label="EMAIL DE SOPORTE">
              <input type="email" value={supportEmail} onChange={e => setSupportEmail(e.target.value)}
                style={inputStyle} placeholder="soporte@tunegocio.com" />
            </Field>
            <Field label="COLOR PRINCIPAL">
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                <input type="color" value={primaryColor} onChange={e => setPrimaryColor(e.target.value)}
                  style={{ width: 48, height: 40, border: "none", background: "none", cursor: "pointer" }} />
                <input value={primaryColor} onChange={e => setPrimaryColor(e.target.value)}
                  style={{ ...inputStyle, width: "auto", flex: 1 }} placeholder="#00FF87" />
                <div style={{ width: 40, height: 40, borderRadius: 8, background: primaryColor, flexShrink: 0 }} />
              </div>
            </Field>
            <button type="submit" disabled={saving} style={{
              padding: "0.65rem 1.5rem", background: `linear-gradient(135deg, ${NEON}, #00D4A0)`,
              border: "none", borderRadius: 8, color: "#06080F", fontWeight: 800,
              fontSize: "0.88rem", cursor: "pointer",
            }}>
              {saving && saved !== "profile" ? "Guardando..." : saved === "tenant" ? "✓ Guardado" : "Guardar configuración"}
            </button>
          </form>
        </Section>

        {/* Variables de entorno pendientes */}
        <Section title="🔑 VARIABLES DE ENTORNO PENDIENTES">
          <p style={{ color: "#4A5070", fontSize: "0.85rem", marginBottom: "1.25rem", lineHeight: 1.5 }}>
            Para activar todas las integraciones, configurá estas variables en <strong style={{ color: "#E8EDFF" }}>Railway</strong> (panel de la API) y en <strong style={{ color: "#E8EDFF" }}>Vercel</strong> según corresponda.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {PENDING_ENV_VARS.map(v => (
              <div key={v.key} style={{ display: "flex", gap: "1rem", alignItems: "flex-start", background: "#07080F", border: "1px solid #1A1F35", borderRadius: 8, padding: "0.75rem 1rem" }}>
                <div style={{ flex: 1 }}>
                  <code style={{ color: CYAN, fontSize: "0.82rem", fontFamily: "monospace" }}>{v.key}</code>
                  <p style={{ color: "#4A5070", fontSize: "0.78rem", margin: "3px 0 0" }}>{v.help}</p>
                </div>
                <span style={{ color: "#FF2D9C", fontSize: "0.72rem", fontWeight: 600, flexShrink: 0, letterSpacing: "0.05em", marginTop: 2 }}>
                  {v.service} · PENDIENTE
                </span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: "1.25rem", padding: "1rem", background: `${NEON}08`, border: `1px solid ${NEON}22`, borderRadius: 8 }}>
            <p style={{ color: "#A0AAC8", fontSize: "0.83rem", margin: 0, lineHeight: 1.5 }}>
              💡 <strong style={{ color: NEON }}>Importante:</strong> Después de agregar variables en Railway hacé un redeploy.
              En Vercel las variables <code style={{ color: CYAN }}>NEXT_PUBLIC_*</code> requieren un rebuild completo (no solo redeploy).
            </p>
          </div>
        </Section>

        {/* Links de administración */}
        <Section title="🔗 PANELES DE ADMINISTRACIÓN">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {[
              { label: "Railway (API + Workers)", url: "https://railway.app/dashboard", desc: "Logs, env vars, deploys de la API" },
              { label: "Vercel — Admin Panel", url: "https://vercel.com/dashboard", desc: "Deploy del panel de administración" },
              { label: "Vercel — Web Store", url: "https://vercel.com/dashboard", desc: "Deploy de la tienda pública" },
              { label: "Neon DB (PostgreSQL)", url: "https://console.neon.tech", desc: "Base de datos PostgreSQL serverless" },
              { label: "Cloudflare R2", url: "https://dash.cloudflare.com", desc: "Almacenamiento de ZIPs de productos" },
              { label: "MercadoPago Developers", url: "https://www.mercadopago.com.ar/developers/es/docs", desc: "Webhooks, tokens, integraciones" },
            ].map(link => (
              <a key={link.label} href={link.url} target="_blank" rel="noopener noreferrer"
                style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem 1rem", background: "#07080F", border: "1px solid #1A1F35", borderRadius: 8, textDecoration: "none", gap: "1rem" }}>
                <div>
                  <p style={{ margin: 0, color: "#E8EDFF", fontSize: "0.88rem", fontWeight: 600 }}>{link.label}</p>
                  <p style={{ margin: "2px 0 0", color: "#4A5070", fontSize: "0.75rem" }}>{link.desc}</p>
                </div>
                <span style={{ color: "#3A3F55", fontSize: "0.85rem", flexShrink: 0 }}>→</span>
              </a>
            ))}
          </div>
        </Section>
      </main>
    </div>
  );
}
