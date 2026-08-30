"use client";
/**
 * Coaches — Fase 12.
 * Gestión de coaches, sus clientes asignados y programas personalizados.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const NEON = "#00FF87";
const CYAN = "#00F5FF";

interface Coach {
  id: string;
  name: string;
  email: string;
  specialties: string[];
  active: boolean;
  instagram?: string;
  _count?: { coachCustomers: number; programs: number };
}

export default function CoachesPage() {
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", specialties: "", instagram: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/coaches", {
        headers: { Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` },
      });
      const data = await res.json();
      setCoaches(data.coaches ?? data.data ?? []);
    } catch { /* empty */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    await fetch("/api/v1/coaches", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` },
      body: JSON.stringify({
        name: form.name, email: form.email,
        specialties: form.specialties.split(",").map(s => s.trim()).filter(Boolean),
        instagram: form.instagram || undefined,
      }),
    });
    setCreating(false);
    setForm({ name: "", email: "", specialties: "", instagram: "" });
    load();
  };

  const inputStyle = { background: "#0A0C18", border: "1px solid #1A1F35", borderRadius: "8px", color: "#E8EDFF", padding: "0.6rem 0.85rem", fontSize: "0.85rem", outline: "none", width: "100%", boxSizing: "border-box" as const };

  return (
    <AdminLayout>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Coaches</h1>
        <button onClick={() => setCreating(!creating)} style={{ padding: "0.5rem 1.25rem", background: creating ? "#1A1F35" : NEON, border: "none", borderRadius: "8px", color: creating ? "#E8EDFF" : "#06080F", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}>
          {creating ? "Cancelar" : "+ Agregar coach"}
        </button>
      </div>

      {creating && (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: `1px solid ${NEON}33`, padding: "1.25rem", marginBottom: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", color: NEON, fontSize: "0.9rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Nueva coach</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Nombre *</span>
              <input style={inputStyle} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="María González" />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Email *</span>
              <input style={inputStyle} type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="coach@fitness.com" />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Especialidades (separadas por coma)</span>
              <input style={inputStyle} value={form.specialties} onChange={e => setForm(f => ({ ...f, specialties: e.target.value }))} placeholder="glúteos, pérdida de grasa, yoga" />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Instagram</span>
              <input style={inputStyle} value={form.instagram} onChange={e => setForm(f => ({ ...f, instagram: e.target.value }))} placeholder="@coach_maria" />
            </label>
          </div>
          <button onClick={handleCreate} disabled={!form.name || !form.email} style={{ padding: "0.5rem 1.25rem", background: NEON, border: "none", borderRadius: "8px", color: "#06080F", fontWeight: 700, cursor: "pointer", opacity: (!form.name || !form.email) ? 0.5 : 1 }}>
            Crear coach
          </button>
        </div>
      )}

      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
      ) : coaches.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>No hay coaches registradas.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
          {coaches.map(coach => (
            <div key={coach.id} style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600, color: "#E8EDFF" }}>{coach.name}</h3>
                  <div style={{ color: "#4A5070", fontSize: "0.8rem" }}>{coach.email}</div>
                </div>
                <span style={{ fontSize: "0.7rem", padding: "2px 8px", borderRadius: 4, background: coach.active ? `${NEON}15` : "#1A1F35", color: coach.active ? NEON : "#4A5070", border: `1px solid ${coach.active ? `${NEON}44` : "#2A2F45"}` }}>
                  {coach.active ? "Activa" : "Inactiva"}
                </span>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "0.75rem" }}>
                {coach.specialties.map(s => (
                  <span key={s} style={{ padding: "2px 8px", borderRadius: 4, background: `${CYAN}15`, color: CYAN, border: `1px solid ${CYAN}22`, fontSize: "0.7rem" }}>{s}</span>
                ))}
              </div>

              <div style={{ display: "flex", gap: "1.25rem", fontSize: "0.8rem", color: "#6B7494" }}>
                <span>👥 {coach._count?.coachCustomers ?? 0} clientes</span>
                <span>📋 {coach._count?.programs ?? 0} programas</span>
                {coach.instagram && <span>📸 {coach.instagram}</span>}
              </div>

              <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid #1A1F35", display: "flex", gap: "0.5rem" }}>
                <a href={`/dashboard/coaches/${coach.id}`} style={{ padding: "4px 10px", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 4, color: "#A0AAC8", fontSize: "0.75rem", textDecoration: "none" }}>
                  Ver perfil
                </a>
                <a href={`/dashboard/coaches/${coach.id}/programs`} style={{ padding: "4px 10px", background: `${NEON}15`, border: `1px solid ${NEON}33`, borderRadius: 4, color: NEON, fontSize: "0.75rem", textDecoration: "none" }}>
                  Programas
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </AdminLayout>
  );
}
