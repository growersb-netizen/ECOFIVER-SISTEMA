"use client";
/**
 * Gestión de productos — Fase 02.
 * Lista todos los productos, permite publicar, archivar, generar descripción con IA.
 * La IA genera DRAFT — nunca publica directamente.
 */

import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";
import { apiClient } from "@/lib/api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";
const YELLOW = "#FFE234";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#4A5070",
  AI_GENERATED: CYAN,
  EDITING: YELLOW,
  PROFESSIONAL_REVIEW: YELLOW,
  APPROVED: "#7C4DFF",
  PUBLISHED: NEON,
  PAUSED: "#FF9800",
  ARCHIVED: "#3A3F55",
};

interface Product {
  id: string;
  sku: string;
  name: string;
  status: string;
  productType: string;
  prices?: Array<{ basePrice: number; currency: string }>;
  category?: { name: string };
  createdAt: string;
}

function Badge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "#4A5070";
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 4,
      fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.05em",
      background: `${color}22`, color, border: `1px solid ${color}44`,
    }}>
      {status}
    </span>
  );
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [generating, setGenerating] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.getProducts({ search, status: filterStatus });
      setProducts(data.products ?? data);
    } catch {
      showToast("Error cargando productos", "err");
    } finally {
      setLoading(false);
    }
  }, [search, filterStatus]);

  useEffect(() => { load(); }, [load]);

  const handlePublish = async (id: string) => {
    if (!confirm("¿Publicar este producto? Una vez publicado será visible en la tienda.")) return;
    try {
      await apiClient.publishProduct(id);
      showToast("Producto publicado ✓");
      load();
    } catch (e: unknown) {
      showToast((e as Error).message ?? "Error al publicar", "err");
    }
  };

  const handleGenerateDescription = async (product: Product) => {
    setGenerating(product.id);
    try {
      const res = await apiClient.generateProductDescription({
        productId: product.id,
        productName: product.name,
        tone: "motivador",
        length: "medium",
      });
      showToast(`Descripción generada en DRAFT (${res.note ?? "requiere revisión"}) ✓`);
    } catch {
      showToast("Error generando descripción", "err");
    } finally {
      setGenerating(null);
    }
  };

  const inputStyle = {
    background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: "8px",
    color: "#E8EDFF", padding: "0.5rem 0.75rem", fontSize: "0.85rem",
    outline: "none",
  } as const;

  return (
    <AdminLayout>
      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: 70, right: 24, zIndex: 9999,
          padding: "0.75rem 1.25rem", borderRadius: 10,
          background: toast.type === "ok" ? `${NEON}22` : `${PINK}22`,
          border: `1px solid ${toast.type === "ok" ? NEON : PINK}`,
          color: toast.type === "ok" ? NEON : PINK,
          fontSize: "0.85rem",
        }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#E8EDFF" }}>
          Productos
        </h1>
        <a href="/dashboard/products/new" style={{
          padding: "0.5rem 1.25rem", background: NEON, color: "#06080F",
          borderRadius: "8px", textDecoration: "none", fontWeight: 700, fontSize: "0.85rem",
        }}>
          + Nuevo producto
        </a>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <input
          style={{ ...inputStyle, flex: 1, minWidth: 200 }}
          placeholder="Buscar por nombre o SKU…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select style={inputStyle} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="">Todos los estados</option>
          {Object.keys(STATUS_COLORS).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Table */}
      <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
        ) : products.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>
            No hay productos. <a href="/dashboard/products/new" style={{ color: NEON }}>Crear el primero →</a>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                  {["SKU", "Nombre", "Categoría", "Precio", "Estado", "Tipo", "Acciones"].map(h => (
                    <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {products.map(p => (
                  <tr key={p.id} style={{ borderBottom: "1px solid #0F111E" }}>
                    <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontFamily: "monospace", fontSize: "0.75rem" }}>{p.sku}</td>
                    <td style={{ padding: "0.75rem 1rem", color: "#E8EDFF", fontWeight: 500 }}>{p.name}</td>
                    <td style={{ padding: "0.75rem 1rem", color: "#6B7494" }}>{p.category?.name ?? "—"}</td>
                    <td style={{ padding: "0.75rem 1rem", color: CYAN, fontVariantNumeric: "tabular-nums" }}>
                      {p.prices?.[0] ? `$${Number(p.prices[0].basePrice).toLocaleString("es-AR")} ${p.prices[0].currency}` : "—"}
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}><Badge status={p.status} /></td>
                    <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>{p.productType}</td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <button
                          onClick={() => handleGenerateDescription(p)}
                          disabled={generating === p.id}
                          style={{ padding: "3px 8px", background: `${CYAN}15`, border: `1px solid ${CYAN}44`, borderRadius: 4, color: CYAN, fontSize: "0.7rem", cursor: "pointer" }}
                        >
                          {generating === p.id ? "…" : "✨ IA"}
                        </button>
                        {["APPROVED", "EDITING", "AI_GENERATED"].includes(p.status) && (
                          <button
                            onClick={() => handlePublish(p.id)}
                            style={{ padding: "3px 8px", background: `${NEON}15`, border: `1px solid ${NEON}44`, borderRadius: 4, color: NEON, fontSize: "0.7rem", cursor: "pointer" }}
                          >
                            Publicar
                          </button>
                        )}
                        <a href={`/dashboard/products/${p.id}`} style={{ padding: "3px 8px", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 4, color: "#A0AAC8", fontSize: "0.7rem", textDecoration: "none" }}>
                          Editar
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p style={{ marginTop: "0.75rem", color: "#4A5070", fontSize: "0.75rem" }}>
        {products.length} producto{products.length !== 1 ? "s" : ""} — La IA genera borradores (DRAFT) que requieren revisión humana antes de publicar.
      </p>
    </AdminLayout>
  );
}
