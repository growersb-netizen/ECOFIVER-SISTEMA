"use client";
/**
 * Afiliadas — Fase 11.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const YELLOW = "#FFE234";

interface Affiliate {
  id: string;
  name: string;
  email: string;
  commissionRate: number;
  active: boolean;
  status: string;
  _count?: { links: number; commissions: number };
}

interface Commission {
  id: string;
  amount: number;
  currency: string;
  status: string;
  affiliate?: { name: string };
  createdAt: string;
}

export default function AffiliatesPage() {
  const [affiliates, setAffiliates] = useState<Affiliate[]>([]);
  const [commissions, setCommissions] = useState<Commission[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"affiliates" | "commissions">("affiliates");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", commissionRate: "10" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` };
      const [affRes, commRes] = await Promise.all([
        fetch("/api/v1/affiliates", { headers }),
        fetch("/api/v1/affiliates/commissions", { headers }),
      ]);
      const affData = await affRes.json();
      const commData = await commRes.json();
      setAffiliates(affData.affiliates ?? affData.data ?? []);
      setCommissions(commData.commissions ?? commData.data ?? []);
    } catch { /* empty */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    await fetch("/api/v1/affiliates", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` },
      body: JSON.stringify({ name: form.name, email: form.email, commissionRate: parseFloat(form.commissionRate) }),
    });
    setCreating(false);
    setForm({ name: "", email: "", commissionRate: "10" });
    load();
  };

  const inputStyle = { background: "#0A0C18", border: "1px solid #1A1F35", borderRadius: "8px", color: "#E8EDFF", padding: "0.6rem 0.85rem", fontSize: "0.85rem", outline: "none", width: "100%", boxSizing: "border-box" as const };

  const pendingTotal = commissions.filter(c => c.status === "pending").reduce((sum, c) => sum + Number(c.amount), 0);

  return (
    <AdminLayout>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Afiliadas</h1>
        {tab === "affiliates" && (
          <button onClick={() => setCreating(!creating)} style={{ padding: "0.5rem 1.25rem", background: creating ? "#1A1F35" : NEON, border: "none", borderRadius: "8px", color: creating ? "#E8EDFF" : "#06080F", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}>
            {creating ? "Cancelar" : "+ Nueva afiliada"}
          </button>
        )}
      </div>

      {/* Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <div style={{ background: "#0D0F1A", borderRadius: 10, border: `1px solid ${NEON}22`, borderLeft: `3px solid ${NEON}`, padding: "1rem" }}>
          <div style={{ color: "#4A5070", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Afiliadas activas</div>
          <div style={{ color: NEON, fontSize: "2rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700 }}>{affiliates.filter(a => a.active).length}</div>
        </div>
        <div style={{ background: "#0D0F1A", borderRadius: 10, border: `1px solid ${YELLOW}22`, borderLeft: `3px solid ${YELLOW}`, padding: "1rem" }}>
          <div style={{ color: "#4A5070", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Comisiones pendientes</div>
          <div style={{ color: YELLOW, fontSize: "2rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700 }}>${pendingTotal.toLocaleString("es-AR")}</div>
        </div>
        <div style={{ background: "#0D0F1A", borderRadius: 10, border: `1px solid ${CYAN}22`, borderLeft: `3px solid ${CYAN}`, padding: "1rem" }}>
          <div style={{ color: "#4A5070", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Total comisiones</div>
          <div style={{ color: CYAN, fontSize: "2rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700 }}>{commissions.length}</div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", borderBottom: "1px solid #1A1F35", paddingBottom: "0.5rem" }}>
        {(["affiliates", "commissions"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ padding: "0.4rem 1rem", borderRadius: "8px 8px 0 0", background: tab === t ? `${NEON}15` : "transparent", border: `1px solid ${tab === t ? `${NEON}44` : "transparent"}`, color: tab === t ? NEON : "#6B7494", cursor: "pointer", fontSize: "0.85rem" }}>
            {t === "affiliates" ? "Afiliadas" : "Comisiones"}
          </button>
        ))}
      </div>

      {tab === "affiliates" && (
        <>
          {creating && (
            <div style={{ background: "#0D0F1A", borderRadius: 12, border: `1px solid ${NEON}33`, padding: "1.25rem", marginBottom: "1.25rem" }}>
              <h3 style={{ margin: "0 0 1rem", color: NEON, fontSize: "0.9rem", textTransform: "uppercase" }}>Nueva afiliada</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
                <input style={inputStyle} placeholder="Nombre" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                <input style={inputStyle} placeholder="Email" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
                <input style={inputStyle} placeholder="Comisión %" type="number" value={form.commissionRate} onChange={e => setForm(f => ({ ...f, commissionRate: e.target.value }))} />
              </div>
              <button onClick={handleCreate} style={{ padding: "0.5rem 1.25rem", background: NEON, border: "none", borderRadius: 8, color: "#06080F", fontWeight: 700, cursor: "pointer" }}>Crear</button>
            </div>
          )}
          <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
            {loading ? <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div> : affiliates.length === 0 ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>No hay afiliadas.</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead><tr style={{ borderBottom: "1px solid #1A1F35" }}>
                  {["Nombre", "Email", "Comisión", "Links", "Estado", ""].map(h => <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase" }}>{h}</th>)}
                </tr></thead>
                <tbody>{affiliates.map(a => (
                  <tr key={a.id} style={{ borderBottom: "1px solid #0F111E" }}>
                    <td style={{ padding: "0.75rem 1rem", color: "#E8EDFF", fontWeight: 500 }}>{a.name}</td>
                    <td style={{ padding: "0.75rem 1rem", color: "#6B7494" }}>{a.email}</td>
                    <td style={{ padding: "0.75rem 1rem", color: NEON, fontWeight: 700 }}>{a.commissionRate}%</td>
                    <td style={{ padding: "0.75rem 1rem", color: CYAN }}>{a._count?.links ?? 0} links</td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: a.active ? `${NEON}15` : "#1A1F35", color: a.active ? NEON : "#4A5070", border: `1px solid ${a.active ? `${NEON}33` : "#2A2F45"}` }}>
                        {a.active ? "Activa" : "Inactiva"}
                      </span>
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <a href={`/dashboard/affiliates/${a.id}`} style={{ fontSize: "0.75rem", color: "#6B7494", textDecoration: "none" }}>Ver →</a>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </>
      )}

      {tab === "commissions" && (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
          {commissions.length === 0 ? <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>No hay comisiones.</div> : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead><tr style={{ borderBottom: "1px solid #1A1F35" }}>
                {["Afiliada", "Monto", "Moneda", "Estado", "Fecha"].map(h => <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase" }}>{h}</th>)}
              </tr></thead>
              <tbody>{commissions.map(c => {
                const color = c.status === "paid" ? NEON : c.status === "pending" ? YELLOW : "#4A5070";
                return (
                  <tr key={c.id} style={{ borderBottom: "1px solid #0F111E" }}>
                    <td style={{ padding: "0.75rem 1rem", color: "#E8EDFF" }}>{c.affiliate?.name ?? "—"}</td>
                    <td style={{ padding: "0.75rem 1rem", color: CYAN, fontVariantNumeric: "tabular-nums" }}>${Number(c.amount).toLocaleString("es-AR")}</td>
                    <td style={{ padding: "0.75rem 1rem", color: "#6B7494" }}>{c.currency}</td>
                    <td style={{ padding: "0.75rem 1rem" }}><span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${color}22`, color, border: `1px solid ${color}44` }}>{c.status}</span></td>
                    <td style={{ padding: "0.75rem 1rem", color: "#4A5070", fontSize: "0.75rem" }}>{new Date(c.createdAt).toLocaleDateString("es-AR")}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
        </div>
      )}
    </AdminLayout>
  );
}
