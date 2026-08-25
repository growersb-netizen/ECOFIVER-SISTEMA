"use client";
/**
 * Gestión de órdenes — Fase 04 (Ecommerce).
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";
import { apiClient } from "@/lib/api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";

const STATUS_COLORS: Record<string, string> = {
  PENDING_PAYMENT: "#FFE234",
  PAID: CYAN,
  AWAITING_CUSTOMER_DATA: "#FF9800",
  READY_FOR_FULFILLMENT: "#7C4DFF",
  FULFILLMENT_PROCESSING: CYAN,
  DELIVERED: NEON,
  COMPLETED: NEON,
  DELIVERY_FAILED: PINK,
  CANCELLED: "#3A3F55",
  REFUNDED: "#3A3F55",
};

interface Order {
  id: string;
  status: string;
  total: number;
  currency: string;
  customerEmail?: string;
  customerName?: string;
  channel?: string;
  items?: Array<{ product: { name: string }; quantity: number; unitPrice: number }>;
  createdAt: string;
}

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "#4A5070";
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 4,
      fontSize: "0.7rem", fontWeight: 700, background: `${color}22`,
      color, border: `1px solid ${color}44`, whiteSpace: "nowrap",
    }}>{status.replace(/_/g, " ")}</span>
  );
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Order | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.getOrders();
      setOrders(data.orders ?? data);
    } catch {
      /* empty */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <AdminLayout>
      <div style={{ display: "flex", gap: "1.5rem", height: "100%" }}>
        {/* List */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
            <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Órdenes</h1>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {(["PAID", "PENDING_PAYMENT", "DELIVERED"] as const).map(s => (
                <span key={s} style={{ fontSize: "0.7rem", padding: "2px 8px", borderRadius: 4, background: `${STATUS_COLORS[s]}22`, color: STATUS_COLORS[s], border: `1px solid ${STATUS_COLORS[s]}44` }}>
                  {s === "PAID" ? "Pagadas" : s === "PENDING_PAYMENT" ? "Pendientes" : "Entregadas"}
                </span>
              ))}
            </div>
          </div>

          <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
            {loading ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
            ) : orders.length === 0 ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Aún no hay órdenes.</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                      {["ID", "Cliente", "Canal", "Total", "Estado", "Fecha", ""].map(h => (
                        <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map(o => (
                      <tr key={o.id} style={{ borderBottom: "1px solid #0F111E", cursor: "pointer", background: selected?.id === o.id ? "#1A1F35" : "transparent" }}
                        onClick={() => setSelected(selected?.id === o.id ? null : o)}>
                        <td style={{ padding: "0.75rem 1rem", fontFamily: "monospace", fontSize: "0.75rem", color: "#6B7494" }}>{o.id.slice(-8)}</td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <div style={{ color: "#E8EDFF" }}>{o.customerName ?? "—"}</div>
                          <div style={{ color: "#4A5070", fontSize: "0.75rem" }}>{o.customerEmail}</div>
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>{o.channel ?? "WEB"}</td>
                        <td style={{ padding: "0.75rem 1rem", color: CYAN, fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                          ${Number(o.total).toLocaleString("es-AR")} {o.currency}
                        </td>
                        <td style={{ padding: "0.75rem 1rem" }}><StatusBadge status={o.status} /></td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>
                          {new Date(o.createdAt).toLocaleDateString("es-AR")}
                        </td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <span style={{ color: "#4A5070", fontSize: "1rem" }}>{selected?.id === o.id ? "▲" : "▼"}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Detail panel */}
        {selected && (
          <div style={{ width: 300, background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 12, padding: "1.25rem", flexShrink: 0, overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ margin: 0, fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem" }}>Orden #{selected.id.slice(-8)}</h3>
              <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", color: "#4A5070", cursor: "pointer", fontSize: "1.25rem" }}>×</button>
            </div>
            <StatusBadge status={selected.status} />
            <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Row label="Cliente" value={selected.customerName ?? "—"} />
              <Row label="Email" value={selected.customerEmail ?? "—"} />
              <Row label="Canal" value={selected.channel ?? "WEB"} />
              <Row label="Total" value={`$${Number(selected.total).toLocaleString("es-AR")} ${selected.currency}`} highlight />
              <Row label="Fecha" value={new Date(selected.createdAt).toLocaleString("es-AR")} />
            </div>
            {selected.items && selected.items.length > 0 && (
              <>
                <p style={{ color: "#4A5070", fontSize: "0.75rem", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", margin: "1rem 0 0.5rem" }}>Productos</p>
                {selected.items.map((item, i) => (
                  <div key={i} style={{ padding: "0.5rem 0", borderBottom: "1px solid #1A1F35", fontSize: "0.8rem" }}>
                    <div style={{ color: "#E8EDFF" }}>{item.product?.name}</div>
                    <div style={{ color: "#4A5070" }}>x{item.quantity} · ${Number(item.unitPrice).toLocaleString("es-AR")}</div>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </AdminLayout>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
      <span style={{ color: "#4A5070" }}>{label}</span>
      <span style={{ color: highlight ? CYAN : "#E8EDFF", fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
}
