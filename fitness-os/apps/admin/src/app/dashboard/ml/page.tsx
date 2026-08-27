"use client";
/**
 * MercadoLibre — Fase 10.
 * Gestión de publicaciones en ML. Siempre DRAFT → revisión humana → publicar.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const YELLOW = "#FFE234";
const PINK = "#FF2D9C";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#4A5070", READY: YELLOW, APPROVED: "#7C4DFF",
  PUBLISHED: NEON, PAUSED: "#FF9800", ERROR: PINK, ARCHIVED: "#3A3F55",
};

interface MLListing {
  id: string;
  title: string;
  price: number;
  currency: string;
  status: string;
  externalId?: string;
  externalUrl?: string;
  mlCategoryId?: string;
  publishedAt?: string;
  product?: { name: string; sku: string };
}

export default function MLPage() {
  const [listings, setListings] = useState<MLListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [oauthStatus, setOauthStatus] = useState<"unknown" | "connected" | "disconnected">("unknown");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/ml/listings", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (res.status === 401) { setOauthStatus("disconnected"); return; }
      const data = await res.json();
      setListings(data.listings ?? data.data ?? []);
      setOauthStatus("connected");
    } catch { setOauthStatus("disconnected"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handlePublish = async (id: string) => {
    if (!confirm("¿Publicar este listing en MercadoLibre? Esta acción es real y pública.")) return;
    const res = await fetch(`/api/v1/ml/listings/${id}/publish`, {
      method: "POST",
      headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
    });
    if (res.ok) load();
  };

  const handleConnectML = () => {
    window.open("/api/v1/ml/auth", "_blank");
  };

  return (
    <AdminLayout>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>MercadoLibre</h1>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          {oauthStatus === "disconnected" && (
            <button onClick={handleConnectML} style={{ padding: "0.5rem 1.25rem", background: YELLOW, border: "none", borderRadius: "8px", color: "#06080F", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}>
              🔗 Conectar cuenta ML
            </button>
          )}
          {oauthStatus === "connected" && (
            <span style={{ fontSize: "0.8rem", color: NEON, background: `${NEON}15`, padding: "0.4rem 0.85rem", borderRadius: 6, border: `1px solid ${NEON}33` }}>
              ✓ Cuenta conectada
            </span>
          )}
        </div>
      </div>

      {oauthStatus === "disconnected" ? (
        <div style={{ padding: "3rem", textAlign: "center", background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35" }}>
          <div style={{ fontSize: "2rem", marginBottom: "1rem" }}>🛍️</div>
          <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", margin: "0 0 0.75rem" }}>Conectá tu cuenta de MercadoLibre</h2>
          <p style={{ color: "#6B7494", marginBottom: "1.5rem", maxWidth: 400, margin: "0 auto 1.5rem" }}>
            Para gestionar publicaciones en ML necesitás autorizar el acceso. Hacé clic en &ldquo;Conectar cuenta ML&rdquo; para empezar.
          </p>
          <button onClick={handleConnectML} style={{ padding: "0.65rem 1.5rem", background: YELLOW, border: "none", borderRadius: 8, color: "#06080F", fontWeight: 700, cursor: "pointer" }}>
            Conectar con MercadoLibre
          </button>
        </div>
      ) : loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando listings…</div>
      ) : listings.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>
          No hay listings. Los productos con precio pueden publicarse como DRAFT en ML desde la sección Productos.
        </div>
      ) : (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                  {["Título", "Precio", "Categoría ML", "Estado", "ID externo", "Publicado", "Acciones"].map(h => (
                    <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {listings.map(l => {
                  const color = STATUS_COLORS[l.status] ?? "#4A5070";
                  return (
                    <tr key={l.id} style={{ borderBottom: "1px solid #0F111E" }}>
                      <td style={{ padding: "0.75rem 1rem" }}>
                        <div style={{ color: "#E8EDFF", fontWeight: 500 }}>{l.title}</div>
                        {l.product && <div style={{ color: "#4A5070", fontSize: "0.75rem" }}>SKU: {l.product.sku}</div>}
                      </td>
                      <td style={{ padding: "0.75rem 1rem", color: CYAN, fontVariantNumeric: "tabular-nums" }}>
                        ${Number(l.price).toLocaleString("es-AR")} {l.currency}
                      </td>
                      <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>{l.mlCategoryId ?? "—"}</td>
                      <td style={{ padding: "0.75rem 1rem" }}>
                        <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${color}22`, color, border: `1px solid ${color}44` }}>
                          {l.status}
                        </span>
                      </td>
                      <td style={{ padding: "0.75rem 1rem" }}>
                        {l.externalId ? (
                          <a href={l.externalUrl ?? "#"} target="_blank" rel="noreferrer" style={{ color: CYAN, fontSize: "0.75rem" }}>
                            {l.externalId}
                          </a>
                        ) : "—"}
                      </td>
                      <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>
                        {l.publishedAt ? new Date(l.publishedAt).toLocaleDateString("es-AR") : "—"}
                      </td>
                      <td style={{ padding: "0.75rem 1rem" }}>
                        {l.status === "APPROVED" && (
                          <button onClick={() => handlePublish(l.id)} style={{ padding: "3px 8px", background: `${NEON}15`, border: `1px solid ${NEON}44`, borderRadius: 4, color: NEON, fontSize: "0.7rem", cursor: "pointer" }}>
                            Publicar en ML
                          </button>
                        )}
                        {l.status === "DRAFT" && (
                          <span style={{ fontSize: "0.7rem", color: YELLOW }}>Pendiente aprobación</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
