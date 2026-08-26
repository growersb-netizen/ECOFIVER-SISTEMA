/**
 * Dashboard placeholder — Fase 00.
 * La UI completa se construye en Fases 01-05.
 */
export default function AdminHome() {
  const modules = [
    { phase: "01", name: "Auth · Tenants · RBAC", status: "pending" },
    { phase: "02", name: "Productos & Catálogo", status: "pending" },
    { phase: "03", name: "Ecommerce — Tienda", status: "pending" },
    { phase: "04", name: "Fulfillment Engine", status: "pending" },
    { phase: "05", name: "IA — OpenRouter & AI Studio", status: "pending" },
    { phase: "06", name: "CRM & Omnichannel Inbox", status: "pending" },
    { phase: "07", name: "WhatsApp + Autopilot", status: "pending" },
    { phase: "08", name: "Mercado Libre", status: "pending" },
    { phase: "09", name: "Redes Sociales", status: "pending" },
    { phase: "10", name: "Blog + Email", status: "pending" },
    { phase: "11", name: "Catálogo ~200 Productos", status: "pending" },
    { phase: "12", name: "Afiliados", status: "pending" },
    { phase: "13", name: "Coaches", status: "pending" },
    { phase: "14", name: "Internacionalización", status: "pending" },
    { phase: "15", name: "Hardening & Lanzamiento", status: "pending" },
  ] as const;

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#07080F",
        color: "#E8EDFF",
        fontFamily: "'DM Sans', system-ui, sans-serif",
        padding: "3rem 2rem",
      }}
    >
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "3rem" }}>
          <p
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: "0.72rem",
              fontWeight: 700,
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "#00F5FF",
              textShadow: "0 0 12px rgba(0,245,255,0.6)",
              marginBottom: "0.75rem",
            }}
          >
            FITNESS BUSINESS OS — ADMIN
          </p>
          <h1
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: "clamp(2.5rem, 6vw, 4rem)",
              fontWeight: 800,
              lineHeight: 0.95,
              letterSpacing: "-0.01em",
              color: "#00FF87",
              textShadow:
                "0 0 12px rgba(0,255,135,0.8), 0 0 32px rgba(0,255,135,0.3)",
              marginBottom: "0.5rem",
            }}
          >
            FASE 00
          </h1>
          <p style={{ color: "#8A94C0", fontSize: "0.9rem" }}>
            Arquitectura instalada · DB schema listo · API corriendo en :3001
          </p>
        </div>

        {/* Status badge */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.4rem 1rem",
            borderRadius: 4,
            background: "rgba(0,255,135,0.07)",
            border: "1px solid rgba(0,255,135,0.25)",
            marginBottom: "2rem",
            fontSize: "0.78rem",
            fontWeight: 600,
            fontFamily: "'Barlow Condensed', sans-serif",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "#00FF87",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#00FF87",
              boxShadow: "0 0 6px #00FF87",
            }}
          />
          MONOREPO ACTIVO
        </div>

        {/* Phases grid */}
        <div
          style={{
            display: "grid",
            gap: "0.75rem",
          }}
        >
          {modules.map((m) => (
            <div
              key={m.phase}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "1.25rem",
                padding: "0.85rem 1.25rem",
                background: "#0D0F1C",
                border: "1px solid #1E2240",
                borderLeft: "3px solid #1E2240",
                borderRadius: 4,
              }}
            >
              <span
                style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontSize: "1.4rem",
                  fontWeight: 800,
                  color: "#3D4468",
                  minWidth: "2.5ch",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {m.phase}
              </span>
              <span
                style={{
                  fontSize: "0.85rem",
                  color: "#4A5070",
                  fontWeight: 500,
                }}
              >
                {m.name}
              </span>
              <span
                style={{
                  marginLeft: "auto",
                  fontSize: "0.68rem",
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "#3D4468",
                  border: "1px solid #1E2240",
                  padding: "0.15rem 0.5rem",
                  borderRadius: 3,
                }}
              >
                PENDIENTE
              </span>
            </div>
          ))}
        </div>

        {/* Footer */}
        <p
          style={{
            marginTop: "3rem",
            fontSize: "0.75rem",
            color: "#3D4468",
            fontFamily: "monospace",
          }}
        >
          API: {process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001"}{" "}
          · DB schema: v1.0 · {new Date().toLocaleDateString("es-AR")}
        </p>
      </div>
    </main>
  );
}
