"use client";
/**
 * MercadoLibre — Fase 08.
 * Panel de control para publicar los 205 productos en ML.
 * Flujo: Conectar ML → Generar 205 borradores → Revisar → Aprobar → Publicar
 * La IA genera DRAFT — la aprobación y publicación son siempre manuales.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const API_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";

const NEON   = "#00FF87";
const CYAN   = "#00F5FF";
const YELLOW = "#FFE234";
const PINK   = "#FF2D9C";
const PURPLE = "#7C4DFF";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#4A5070",
  READY: YELLOW,
  APPROVED: PURPLE,
  PUBLISHED: NEON,
  PAUSED: "#FF9800",
  ERROR: PINK,
  ARCHIVED: "#3A3F55",
};
const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Borrador",
  READY: "Listo",
  APPROVED: "Aprobado",
  PUBLISHED: "Publicado",
  PAUSED: "Pausado",
  ERROR: "Error",
  ARCHIVED: "Archivado",
};

interface MLStatus {
  connected: boolean;
  mlUserId?: string;
  totalProducts: number;
  withDraft: number;
  publishedListings: number;
  pending: number;
  byStatus: Record<string, number>;
}

interface MLListing {
  id: string;
  title: string;
  price: number;
  currency: string;
  status: string;
  externalId?: string;
  publishedAt?: string;
  product?: { name: string; sku: string; id: string };
}

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 4,
      fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.04em",
      background: `${color}22`, color, border: `1px solid ${color}44`,
    }}>
      {label}
    </span>
  );
}

function MetricCard({ label, value, color, sub }: { label: string; value: number | string; color: string; sub?: string }) {
  return (
    <div style={{
      background: "#0D0F1A", border: `1px solid ${color}33`, borderRadius: 12,
      padding: "1.1rem 1.25rem", minWidth: 130,
    }}>
      <div style={{ fontSize: "1.85rem", fontWeight: 700, color, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>
        {value}
      </div>
      <div style={{ fontSize: "0.72rem", color: "#6B7494", marginTop: "0.3rem" }}>{label}</div>
      {sub && <div style={{ fontSize: "0.65rem", color: "#4A5070", marginTop: "0.15rem" }}>{sub}</div>}
    </div>
  );
}

export default function MLPage() {
  const [status, setStatus] = useState<MLStatus | null>(null);
  const [listings, setListings] = useState<MLListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState("");
  const [bulkDraftLoading, setBulkDraftLoading] = useState(false);
  const [bulkPublishLoading, setBulkPublishLoading] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" | "warn" } | null>(null);
  const [bulkResult, setBulkResult] = useState<{ created?: number; published?: number; failed?: number; errors?: Array<{sku:string;reason:string}> } | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("fitness_access_token") : "";

  const showToast = (msg: string, type: "ok" | "err" | "warn" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 5000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sRes, lRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/ml/status`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_URL}/api/v1/ml/listings`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (sRes.ok) setStatus(await sRes.json() as MLStatus);
      if (lRes.ok) {
        const d = await lRes.json() as { data?: MLListing[] };
        setListings(d.data ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleConnectML = () => {
    window.open(`${API_URL}/api/v1/ml/auth`, "_blank");
  };

  const handleBulkDraft = async () => {
    if (!confirm(`¿Generar borradores para todos los productos sin publicación?\n\nEsto crea BORRADORES internos — no publica nada en MercadoLibre todavía.`)) return;
    setBulkDraftLoading(true);
    setBulkResult(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/ml/listings/bulk-draft`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json() as { created: number; skipped: number; errors?: Array<{sku:string;reason:string}> };
      setBulkResult({ created: data.created, errors: data.errors });
      showToast(`✅ ${data.created} borradores creados — ${data.skipped} sin precio (requieren precio antes de publicar)`);
      load();
    } catch {
      showToast("Error generando borradores", "err");
    } finally {
      setBulkDraftLoading(false);
    }
  };

  const handleBulkPublish = async () => {
    const approved = status?.byStatus?.["APPROVED"] ?? 0;
    if (approved === 0) {
      showToast("No hay listings aprobados. Aprobá borradores primero.", "warn");
      return;
    }
    if (!confirm(`¿Publicar ${approved} listings APROBADOS en MercadoLibre?\n\n⚠️ Esta acción es real y pública. Las publicaciones quedarán visibles en ML.`)) return;
    setBulkPublishLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/ml/listings/bulk-publish`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json() as { published: number; failed: number; errors?: Array<{sku:string;reason:string}> };
      setBulkResult({ published: data.published, failed: data.failed, errors: data.errors });
      showToast(`🎉 ${data.published} publicados en ML${data.failed > 0 ? ` — ${data.failed} con error` : ""}`, data.failed > 0 ? "warn" : "ok");
      load();
    } catch {
      showToast("Error en publicación masiva", "err");
    } finally {
      setBulkPublishLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    const res = await fetch(`${API_URL}/api/v1/ml/listings/${id}/approve`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { showToast("Listing aprobado ✓"); load(); }
    else showToast("Error al aprobar", "err");
  };

  const handlePublishOne = async (id: string) => {
    if (!confirm("¿Publicar este listing en MercadoLibre? Esta acción es real y pública.")) return;
    const res = await fetch(`${API_URL}/api/v1/ml/listings/${id}/publish`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { showToast("Publicado en ML ✓"); load(); }
    else showToast("Error al publicar", "err");
  };

  const toastColor = toast?.type === "ok" ? NEON : toast?.type === "warn" ? YELLOW : PINK;
  const totalDrafts = status?.withDraft ?? 0;
  const totalProducts = status?.totalProducts ?? 0;
  const pct = totalProducts > 0 ? Math.round((totalDrafts / totalProducts) * 100) : 0;
  const pctPublished = totalProducts > 0 ? Math.round(((status?.publishedListings ?? 0) / totalProducts) * 100) : 0;

  const filtered = filterStatus ? listings.filter(l => l.status === filterStatus) : listings;

  return (
    <AdminLayout>
      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: 70, right: 24, zIndex: 9999,
          padding: "0.75rem 1.25rem", borderRadius: 10,
          background: `${toastColor}22`, border: `1px solid ${toastColor}`,
          color: toastColor, fontSize: "0.85rem", maxWidth: 360,
        }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>
            MercadoLibre
          </h1>
          <p style={{ margin: "0.25rem 0 0", color: "#6B7494", fontSize: "0.8rem" }}>
            Publicá tus 205 productos digitales en ML — flujo: Borrador → Aprobación → Publicar
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.65rem", alignItems: "center" }}>
          {status?.connected ? (
            <span style={{ fontSize: "0.8rem", color: NEON, background: `${NEON}15`, padding: "0.4rem 0.85rem", borderRadius: 6, border: `1px solid ${NEON}33` }}>
              ✓ Cuenta conectada {status.mlUserId ? `(ID: ${status.mlUserId})` : ""}
            </span>
          ) : (
            <button
              onClick={handleConnectML}
              style={{ padding: "0.5rem 1.25rem", background: YELLOW, border: "none", borderRadius: "8px", color: "#06080F", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}
            >
              🔗 Conectar cuenta ML
            </button>
          )}
        </div>
      </div>

      {/* Métricas */}
      {status && (
        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
          <MetricCard label="Productos PUBLISHED" value={totalProducts} color={CYAN} sub="disponibles para ML" />
          <MetricCard label="Con borrador" value={totalDrafts} color={YELLOW} sub={`${pct}% del catálogo`} />
          <MetricCard
            label="Publicados en ML"
            value={status.publishedListings}
            color={NEON}
            sub={`${pctPublished}% del catálogo`}
          />
          <MetricCard label="Pendientes" value={status.pending} color={PURPLE} sub="con borrador, sin publicar" />
          {Object.entries(status.byStatus ?? {}).map(([s, n]) => (
            <MetricCard key={s} label={STATUS_LABELS[s] ?? s} value={n} color={STATUS_COLORS[s] ?? "#4A5070"} />
          ))}
        </div>
      )}

      {/* Barra de progreso */}
      {status && (
        <div style={{ background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 10, padding: "0.85rem 1.1rem", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem", fontSize: "0.78rem" }}>
            <span style={{ color: "#A0AAC8" }}>Progreso publicación</span>
            <span style={{ color: "#6B7494" }}>{status.publishedListings} / {totalProducts} productos</span>
          </div>
          <div style={{ background: "#1A1F35", borderRadius: 6, height: 8, overflow: "hidden" }}>
            <div style={{ width: `${pctPublished}%`, height: "100%", background: NEON, borderRadius: 6, transition: "width 0.4s" }} />
          </div>
          <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem", fontSize: "0.72rem", color: "#4A5070" }}>
            <span>▬ <span style={{ color: NEON }}>Publicado</span></span>
            <span>▬ <span style={{ color: PURPLE }}>Aprobado</span></span>
            <span>▬ <span style={{ color: YELLOW }}>Borrador</span></span>
          </div>
        </div>
      )}

      {/* Acciones masivas */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <button
          onClick={handleBulkDraft}
          disabled={bulkDraftLoading}
          style={{
            padding: "0.65rem 1.4rem", background: CYAN, border: "none", borderRadius: 10,
            color: "#06080F", fontWeight: 700, fontSize: "0.9rem",
            cursor: bulkDraftLoading ? "not-allowed" : "pointer", opacity: bulkDraftLoading ? 0.7 : 1,
          }}
        >
          {bulkDraftLoading ? "⏳ Generando…" : `📋 Generar ${totalProducts - totalDrafts > 0 ? `${totalProducts - totalDrafts} ` : ""}borradores`}
        </button>
        <button
          onClick={handleBulkPublish}
          disabled={bulkPublishLoading || !status?.connected || (status?.byStatus?.["APPROVED"] ?? 0) === 0}
          style={{
            padding: "0.65rem 1.4rem",
            background: status?.connected && (status?.byStatus?.["APPROVED"] ?? 0) > 0 ? NEON : "#2A2F45",
            border: "none", borderRadius: 10,
            color: status?.connected && (status?.byStatus?.["APPROVED"] ?? 0) > 0 ? "#06080F" : "#4A5070",
            fontWeight: 700, fontSize: "0.9rem",
            cursor: (bulkPublishLoading || !status?.connected || (status?.byStatus?.["APPROVED"] ?? 0) === 0) ? "not-allowed" : "pointer",
            opacity: bulkPublishLoading ? 0.7 : 1,
          }}
        >
          {bulkPublishLoading
            ? "⏳ Publicando…"
            : `🚀 Publicar ${status?.byStatus?.["APPROVED"] ?? 0} aprobados en ML`}
        </button>
        {!status?.connected && (
          <span style={{ alignSelf: "center", fontSize: "0.75rem", color: YELLOW }}>
            ⚠️ Conectá ML primero para poder publicar
          </span>
        )}
      </div>

      {/* Resultado de acción masiva */}
      {bulkResult && (
        <div style={{ marginBottom: "1.25rem", padding: "0.85rem 1.1rem", background: "#0D0F1A", border: `1px solid ${NEON}33`, borderRadius: 10, fontSize: "0.82rem" }}>
          {bulkResult.created !== undefined && <p style={{ margin: "0 0 0.3rem", color: NEON }}>✅ {bulkResult.created} borradores creados</p>}
          {bulkResult.published !== undefined && <p style={{ margin: "0 0 0.3rem", color: NEON }}>🎉 {bulkResult.published} publicados en ML</p>}
          {(bulkResult.failed ?? 0) > 0 && <p style={{ margin: "0 0 0.3rem", color: PINK }}>⚠️ {bulkResult.failed} con error</p>}
          {(bulkResult.errors?.length ?? 0) > 0 && (
            <details style={{ marginTop: "0.4rem" }}>
              <summary style={{ cursor: "pointer", color: "#6B7494" }}>Ver errores</summary>
              <ul style={{ margin: "0.4rem 0 0", padding: "0 0 0 1.2rem", color: YELLOW, fontSize: "0.75rem" }}>
                {bulkResult.errors!.map((e, i) => <li key={i}>{e.sku}: {e.reason}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Instrucciones si no está conectado */}
      {status && !status.connected && (
        <div style={{ marginBottom: "1.5rem", padding: "1rem 1.25rem", background: `${YELLOW}11`, border: `1px solid ${YELLOW}44`, borderRadius: 10, fontSize: "0.82rem", color: "#A0AAC8", lineHeight: 1.6 }}>
          <strong style={{ color: YELLOW }}>Pasos para conectar ML:</strong>
          <ol style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
            <li>Configurá las env vars en Railway: <code style={{ color: CYAN }}>MERCADOLIBRE_CLIENT_ID</code>, <code style={{ color: CYAN }}>MERCADOLIBRE_CLIENT_SECRET</code>, <code style={{ color: CYAN }}>API_URL</code>, <code style={{ color: CYAN }}>APP_ADMIN_URL</code></li>
            <li>Creá una app en <a href="https://developers.mercadolibre.com.ar" target="_blank" rel="noreferrer" style={{ color: CYAN }}>developers.mercadolibre.com.ar</a> con redirect URI: <code style={{ color: NEON }}>TU_API_URL/api/v1/ml/auth/callback</code></li>
            <li>Hacé clic en &ldquo;Conectar cuenta ML&rdquo; y autorizá el acceso</li>
            <li>Generá los borradores y aprobálos antes de publicar</li>
          </ol>
        </div>
      )}

      {/* Filtro + tabla */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
        <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem", fontWeight: 600, margin: 0, color: "#E8EDFF" }}>
          Listings ({filtered.length})
        </h2>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          style={{ background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#E8EDFF", padding: "0.4rem 0.7rem", fontSize: "0.8rem" }}
        >
          <option value="">Todos</option>
          {Object.entries(STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>
            {listings.length === 0
              ? "No hay listings todavía — hacé clic en \"Generar borradores\" para empezar"
              : `Sin resultados para filtro "${filterStatus}"`}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                  {["SKU / Producto", "Título ML", "Precio", "Estado", "ID en ML", "Acciones"].map(h => (
                    <th key={h} style={{ padding: "0.65rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.72rem", letterSpacing: "0.05em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(l => (
                  <tr key={l.id} style={{ borderBottom: "1px solid #0F111E" }}>
                    <td style={{ padding: "0.65rem 1rem" }}>
                      <div style={{ color: "#E8EDFF", fontWeight: 500, fontSize: "0.8rem" }}>
                        {l.product ? (
                          <a href={`/dashboard/products/${l.product.id}`} style={{ color: "#E8EDFF", textDecoration: "none" }}>
                            {l.product.name}
                          </a>
                        ) : "—"}
                      </div>
                      {l.product?.sku && <div style={{ color: "#4A5070", fontSize: "0.7rem", fontFamily: "monospace" }}>{l.product.sku}</div>}
                    </td>
                    <td style={{ padding: "0.65rem 1rem", color: "#A0AAC8", maxWidth: 220 }}>
                      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.title}>{l.title}</div>
                    </td>
                    <td style={{ padding: "0.65rem 1rem", color: CYAN, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                      ${Number(l.price).toLocaleString("es-AR")} {l.currency}
                    </td>
                    <td style={{ padding: "0.65rem 1rem" }}>
                      <Chip label={STATUS_LABELS[l.status] ?? l.status} color={STATUS_COLORS[l.status] ?? "#4A5070"} />
                    </td>
                    <td style={{ padding: "0.65rem 1rem" }}>
                      {l.externalId ? (
                        <span style={{ fontFamily: "monospace", fontSize: "0.72rem", color: NEON }}>{l.externalId}</span>
                      ) : <span style={{ color: "#3A3F55" }}>—</span>}
                    </td>
                    <td style={{ padding: "0.65rem 1rem" }}>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {l.status === "DRAFT" && (
                          <button
                            onClick={() => handleApprove(l.id)}
                            style={{ padding: "3px 8px", background: `${PURPLE}20`, border: `1px solid ${PURPLE}44`, borderRadius: 4, color: PURPLE, fontSize: "0.7rem", cursor: "pointer" }}
                          >
                            ✓ Aprobar
                          </button>
                        )}
                        {l.status === "APPROVED" && (
                          <button
                            onClick={() => handlePublishOne(l.id)}
                            style={{ padding: "3px 8px", background: `${NEON}15`, border: `1px solid ${NEON}44`, borderRadius: 4, color: NEON, fontSize: "0.7rem", cursor: "pointer" }}
                          >
                            🚀 Publicar
                          </button>
                        )}
                        {l.status === "PUBLISHED" && l.externalId && (
                          <a
                            href={`https://articulo.mercadolibre.com.ar/${l.externalId}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ padding: "3px 8px", background: `${CYAN}15`, border: `1px solid ${CYAN}44`, borderRadius: 4, color: CYAN, fontSize: "0.7rem", textDecoration: "none" }}
                          >
                            Ver en ML ↗
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p style={{ marginTop: "0.75rem", color: "#4A5070", fontSize: "0.72rem" }}>
        Flujo seguro: Borrador → Revisión manual → Aprobar → Publicar en ML. La IA nunca publica directamente.
      </p>
    </AdminLayout>
  );
}
