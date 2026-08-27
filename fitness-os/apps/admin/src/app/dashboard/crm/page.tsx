"use client";
/**
 * CRM — Leads, clientes y conversaciones — Fase 07.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";
import { apiClient } from "@/lib/api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";
const YELLOW = "#FFE234";

const LEAD_COLORS: Record<string, string> = {
  NEW: CYAN, CONTACTED: YELLOW, QUALIFIED: "#7C4DFF",
  PROPOSAL: "#FF9800", PURCHASED: NEON, CUSTOMER: NEON,
  REPEAT_CUSTOMER: NEON, INACTIVE: "#3A3F55",
};

interface Lead {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  source?: string;
  status: string;
  productInterest?: string;
  assignedTo?: { name: string };
  createdAt: string;
}

type Tab = "leads" | "customers";

export default function CRMPage() {
  const [tab, setTab] = useState<Tab>("leads");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.getLeads({ search, status: filterStatus });
      setLeads((data.leads ?? data) as Lead[]);
    } catch { /* empty */ }
    finally { setLoading(false); }
  }, [search, filterStatus]);

  useEffect(() => { if (tab === "leads") load(); }, [tab, load]);

  const inputStyle = {
    background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: "8px",
    color: "#E8EDFF", padding: "0.5rem 0.75rem", fontSize: "0.85rem", outline: "none",
  } as const;

  return (
    <AdminLayout>
      <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, marginBottom: "1.25rem" }}>CRM</h1>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", borderBottom: "1px solid #1A1F35", paddingBottom: "0.5rem" }}>
        {(["leads", "customers"] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "0.4rem 1rem", borderRadius: "8px 8px 0 0",
            background: tab === t ? `${NEON}15` : "transparent",
            border: `1px solid ${tab === t ? `${NEON}44` : "transparent"}`,
            color: tab === t ? NEON : "#6B7494", cursor: "pointer", fontSize: "0.85rem",
          }}>
            {t === "leads" ? "Leads" : "Clientes"}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <input style={{ ...inputStyle, flex: 1, minWidth: 200 }} placeholder="Buscar…" value={search} onChange={e => setSearch(e.target.value)} />
        {tab === "leads" && (
          <select style={inputStyle} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            <option value="">Todos los estados</option>
            {Object.keys(LEAD_COLORS).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </div>

      {/* Leads table */}
      {tab === "leads" && (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
          {loading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
          ) : leads.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>No hay leads.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                    {["Nombre", "Email / Tel", "Fuente", "Interés", "Asignada", "Estado", "Fecha"].map(h => (
                      <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {leads.map(lead => {
                    const color = LEAD_COLORS[lead.status] ?? "#4A5070";
                    return (
                      <tr key={lead.id} style={{ borderBottom: "1px solid #0F111E" }}>
                        <td style={{ padding: "0.75rem 1rem", color: "#E8EDFF", fontWeight: 500 }}>{lead.name}</td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <div style={{ color: "#A0AAC8" }}>{lead.email ?? "—"}</div>
                          {lead.phone && <div style={{ color: "#6B7494", fontSize: "0.75rem" }}>{lead.phone}</div>}
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>{lead.source ?? "—"}</td>
                        <td style={{ padding: "0.75rem 1rem", color: CYAN, fontSize: "0.8rem" }}>{lead.productInterest ?? "—"}</td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.8rem" }}>{lead.assignedTo?.name ?? "Sin asignar"}</td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${color}22`, color, border: `1px solid ${color}44` }}>
                            {lead.status}
                          </span>
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "#4A5070", fontSize: "0.75rem" }}>
                          {new Date(lead.createdAt).toLocaleDateString("es-AR")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "customers" && (
        <CustomersTab />
      )}
    </AdminLayout>
  );
}

function CustomersTab() {
  const [customers, setCustomers] = useState<Array<{ id: string; name?: string; email: string; source?: string; tags: string[]; createdAt: string }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.getCustomers?.()
      .then(d => setCustomers(d.customers ?? d))
      .catch(() => { })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
      ) : customers.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Aún no hay clientes registrados.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                {["Nombre", "Email", "Fuente", "Tags", "Registro"].map(h => (
                  <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {customers.map(c => (
                <tr key={c.id} style={{ borderBottom: "1px solid #0F111E" }}>
                  <td style={{ padding: "0.75rem 1rem", color: "#E8EDFF" }}>{c.name ?? "—"}</td>
                  <td style={{ padding: "0.75rem 1rem", color: "#A0AAC8" }}>{c.email}</td>
                  <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>{c.source ?? "—"}</td>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    {c.tags.map(t => <span key={t} style={{ marginRight: 4, padding: "1px 6px", borderRadius: 4, background: "#1A1F35", color: "#6B7494", fontSize: "0.7rem" }}>{t}</span>)}
                  </td>
                  <td style={{ padding: "0.75rem 1rem", color: "#4A5070", fontSize: "0.75rem" }}>{new Date(c.createdAt).toLocaleDateString("es-AR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
