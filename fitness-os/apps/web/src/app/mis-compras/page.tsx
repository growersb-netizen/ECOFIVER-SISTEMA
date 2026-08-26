"use client";
/**
 * /mis-compras — Portal del cliente.
 * Muestra las compras realizadas con enlace de descarga de cada producto.
 * Auth: email + order ID (sin registro obligatorio).
 */
import { useState, FormEvent } from "react";
import Link from "next/link";

const API_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
const TENANT_SLUG = process.env["NEXT_PUBLIC_TENANT_SLUG"] ?? "";
const NEON = "#00FF87";
const CYAN = "#00F5FF";

interface Purchase {
  id: string;
  status: string;
  totalAmount: number;
  currency: string;
  createdAt: string;
  items: Array<{
    productName: string;
    productSku: string;
    downloadUrl?: string;
  }>;
}

async function fetchPurchases(email: string, orderId?: string): Promise<Purchase[]> {
  const qs = new URLSearchParams({ email });
  if (orderId) qs.set("orderId", orderId);
  const res = await fetch(`${API_URL}/api/v1/orders/my-purchases?${qs}`, {
    headers: {
      "Content-Type": "application/json",
      ...(TENANT_SLUG ? { "X-Tenant-Slug": TENANT_SLUG } : {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { error?: string };
    throw new Error(err.error ?? "No se encontraron compras para ese email.");
  }
  const data = await res.json() as { data: Purchase[] };
  return data.data ?? [];
}

export default function MisComprasPage() {
  const [email, setEmail] = useState("");
  const [orderId, setOrderId] = useState("");
  const [purchases, setPurchases] = useState<Purchase[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const data = await fetchPurchases(email.trim().toLowerCase(), orderId.trim() || undefined);
      setPurchases(data);
    } catch (err) {
      setError((err as Error).message);
      setPurchases([]);
    } finally {
      setLoading(false);
    }
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("es-AR", { day: "2-digit", month: "long", year: "numeric" });

  const formatPrice = (amount: number, currency: string) =>
    new Intl.NumberFormat("es-AR", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);

  const statusLabel = (s: string) => {
    const map: Record<string, { label: string; color: string }> = {
      PAID: { label: "✓ Pagado", color: NEON },
      DELIVERED: { label: "⚡ Entregado", color: NEON },
      PENDING: { label: "⏳ Pendiente", color: "#FFE234" },
      FAILED: { label: "✕ Fallido", color: "#FF2D9C" },
      CANCELLED: { label: "↩ Cancelado", color: "#4A5070" },
    };
    return map[s] ?? { label: s, color: "#A0AAC8" };
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#07080F",
      color: "#E8EDFF",
      fontFamily: "'DM Sans', system-ui, sans-serif",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Nav */}
      <nav style={{ background: "#0A0C18", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center", gap: "1.5rem" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
        <Link href="/tienda" style={{ color: "#4A5070", fontSize: "0.85rem", textDecoration: "none" }}>Tienda</Link>
      </nav>

      <main style={{ flex: 1, maxWidth: 680, width: "100%", margin: "0 auto", padding: "3rem 1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2.25rem", fontWeight: 800, margin: "0 0 0.5rem" }}>
          MIS COMPRAS
        </h1>
        <p style={{ color: "#4A5070", fontSize: "0.9rem", margin: "0 0 2.5rem" }}>
          Ingresá tu email para ver y descargar tus productos.
        </p>

        {/* Form */}
        <form onSubmit={handleSearch} style={{
          background: "#0D0F1A", border: "1px solid #1A1F35",
          borderRadius: 14, padding: "1.5rem",
          marginBottom: "2rem",
        }}>
          <div style={{ marginBottom: "1rem" }}>
            <label style={{ display: "block", fontSize: "0.78rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: "6px" }}>
              EMAIL CON EL QUE COMPRASTE *
            </label>
            <input
              type="email" required value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="tu@email.com"
              style={{
                width: "100%", background: "#0A0C18",
                border: "1px solid #2A2F45", borderRadius: 8,
                padding: "0.7rem 1rem", color: "#E8EDFF",
                fontSize: "0.95rem", outline: "none", boxSizing: "border-box",
              }}
              onFocus={e => (e.target.style.borderColor = NEON)}
              onBlur={e => (e.target.style.borderColor = "#2A2F45")}
            />
          </div>
          <div style={{ marginBottom: "1.25rem" }}>
            <label style={{ display: "block", fontSize: "0.78rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: "6px" }}>
              ID DE ORDEN <span style={{ color: "#3A3F55" }}>(opcional)</span>
            </label>
            <input
              type="text" value={orderId}
              onChange={e => setOrderId(e.target.value)}
              placeholder="Si tenés el ID de tu orden"
              style={{
                width: "100%", background: "#0A0C18",
                border: "1px solid #2A2F45", borderRadius: 8,
                padding: "0.7rem 1rem", color: "#E8EDFF",
                fontSize: "0.95rem", outline: "none", boxSizing: "border-box",
              }}
            />
          </div>
          <button type="submit" disabled={loading || !email} style={{
            width: "100%", padding: "0.85rem",
            background: loading ? "#1A1F35" : `linear-gradient(135deg, ${NEON}, #00D4A0)`,
            border: "none", borderRadius: 10,
            color: loading ? "#4A5070" : "#06080F",
            fontWeight: 800, fontSize: "0.95rem",
            cursor: loading ? "not-allowed" : "pointer",
          }}>
            {loading ? "Buscando..." : "Ver mis compras →"}
          </button>
        </form>

        {/* Results */}
        {error && (
          <div style={{ padding: "1rem 1.25rem", background: "#FF2D9C15", border: "1px solid #FF2D9C33", borderRadius: 10, color: "#FF2D9C", marginBottom: "1.5rem" }}>
            {error}
          </div>
        )}

        {searched && !loading && purchases !== null && purchases.length === 0 && !error && (
          <div style={{ padding: "2.5rem", textAlign: "center", background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 14 }}>
            <p style={{ color: "#4A5070", marginBottom: "1rem" }}>No encontramos compras para ese email.</p>
            <p style={{ color: "#3A3F55", fontSize: "0.85rem" }}>
              ¿Compraste con otro email? Intentá con el email que usaste en el pago.
              <br />Si el problema persiste, contactanos:{" "}
              <a href="mailto:soporte@fitnessbusiness.com" style={{ color: CYAN }}>soporte@fitnessbusiness.com</a>
            </p>
          </div>
        )}

        {purchases && purchases.length > 0 && (
          <div>
            <p style={{ color: "#4A5070", fontSize: "0.85rem", marginBottom: "1rem" }}>
              {purchases.length} compra{purchases.length !== 1 ? "s" : ""} encontrada{purchases.length !== 1 ? "s" : ""}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {purchases.map(purchase => {
                const { label, color } = statusLabel(purchase.status);
                const canDownload = purchase.status === "PAID" || purchase.status === "DELIVERED";
                return (
                  <div key={purchase.id} style={{
                    background: "#0D0F1A", border: "1px solid #1A1F35",
                    borderRadius: 14, overflow: "hidden",
                  }}>
                    {/* Header orden */}
                    <div style={{ padding: "1rem 1.25rem", borderBottom: "1px solid #1A1F35", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div>
                        <span style={{ color: "#4A5070", fontSize: "0.75rem", letterSpacing: "0.08em" }}>ORDEN </span>
                        <span style={{ color: "#E8EDFF", fontFamily: "monospace", fontSize: "0.85rem" }}>#{purchase.id.slice(-8).toUpperCase()}</span>
                      </div>
                      <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                        <span style={{ color, fontSize: "0.82rem", fontWeight: 600 }}>{label}</span>
                        <span style={{ color: "#4A5070", fontSize: "0.78rem" }}>{formatDate(purchase.createdAt)}</span>
                        <span style={{ color: NEON, fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "1.05rem" }}>
                          {formatPrice(purchase.totalAmount, purchase.currency)}
                        </span>
                      </div>
                    </div>

                    {/* Items */}
                    <div style={{ padding: "1rem 1.25rem" }}>
                      {purchase.items.map((item, idx) => (
                        <div key={idx} style={{
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                          padding: "0.75rem 0",
                          borderBottom: idx < purchase.items.length - 1 ? "1px solid #1A1F35" : "none",
                          gap: "1rem",
                        }}>
                          <div>
                            <p style={{ margin: 0, color: "#E8EDFF", fontWeight: 600, fontSize: "0.95rem" }}>{item.productName}</p>
                            <p style={{ margin: "2px 0 0", color: "#4A5070", fontSize: "0.75rem", fontFamily: "monospace" }}>{item.productSku}</p>
                          </div>
                          {canDownload ? (
                            item.downloadUrl ? (
                              <a
                                href={item.downloadUrl}
                                target="_blank" rel="noopener noreferrer"
                                style={{
                                  display: "inline-flex", alignItems: "center", gap: "0.4rem",
                                  background: `${NEON}15`, border: `1px solid ${NEON}44`,
                                  color: NEON, padding: "0.45rem 0.85rem",
                                  borderRadius: 8, fontSize: "0.82rem", fontWeight: 700,
                                  textDecoration: "none", whiteSpace: "nowrap",
                                  flexShrink: 0,
                                }}
                              >
                                ⬇ Descargar
                              </a>
                            ) : (
                              <span style={{ color: "#4A5070", fontSize: "0.8rem", flexShrink: 0 }}>
                                Procesando...
                              </span>
                            )
                          ) : (
                            <span style={{ color: "#3A3F55", fontSize: "0.78rem", flexShrink: 0 }}>
                              No disponible
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            <p style={{ color: "#3A3F55", fontSize: "0.78rem", marginTop: "2rem", textAlign: "center" }}>
              Los links de descarga son válidos por 72 horas. ¿Problemas?{" "}
              <a href="mailto:soporte@fitnessbusiness.com" style={{ color: "#4A5070" }}>Contactanos</a>
            </p>
          </div>
        )}
      </main>

      <div style={{ padding: "1.5rem", textAlign: "center", borderTop: "1px solid #1A1F35", color: "#3A3F55", fontSize: "0.78rem" }}>
        Fitness Business OS · soporte@fitnessbusiness.com
      </div>
    </div>
  );
}
