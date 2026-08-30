"use client";
/**
 * Publicaciones en redes sociales — Fase 09.
 * DRAFT → SCHEDULED → PUBLISHED. La IA solo genera borradores.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";
const YELLOW = "#FFE234";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#4A5070", READY: YELLOW, APPROVED: "#7C4DFF",
  SCHEDULED: CYAN, PUBLISHED: NEON, PAUSED: "#FF9800",
  ERROR: PINK, ARCHIVED: "#3A3F55",
};

const PLATFORM_ICONS: Record<string, string> = {
  INSTAGRAM: "📸", FACEBOOK: "👍", TIKTOK: "🎵", YOUTUBE: "▶️",
};

interface Publication {
  id: string;
  platform: string;
  type: string;
  status: string;
  title?: string;
  caption?: string;
  scheduledAt?: string;
  publishedAt?: string;
  aiGenerated: boolean;
  createdAt: string;
}

export default function SocialPage() {
  const [pubs, setPubs] = useState<Publication[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newPub, setNewPub] = useState({ platform: "INSTAGRAM", type: "POST", caption: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/social/publications", {
        headers: { Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` },
      });
      const data = await res.json();
      setPubs(data.publications ?? data.data ?? []);
    } catch { /* empty */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      await fetch("/api/v1/social/publications", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` },
        body: JSON.stringify(newPub),
      });
      setCreating(false);
      setNewPub({ platform: "INSTAGRAM", type: "POST", caption: "" });
      load();
    } catch { /* empty */ }
  };

  const handlePublish = async (id: string) => {
    if (!confirm("¿Publicar en la plataforma? Esta acción es externa.")) return;
    await fetch(`/api/v1/social/publications/${id}/publish`, {
      method: "POST",
      headers: { Authorization: `Bearer ${localStorage.getItem("fitness_access_token")}` },
    });
    load();
  };

  const inputStyle = { background: "#0A0C18", border: "1px solid #1A1F35", borderRadius: "8px", color: "#E8EDFF", padding: "0.6rem 0.85rem", fontSize: "0.85rem", outline: "none", width: "100%", boxSizing: "border-box" as const };

  return (
    <AdminLayout>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Redes Sociales</h1>
        <button onClick={() => setCreating(!creating)} style={{ padding: "0.5rem 1.25rem", background: creating ? "#1A1F35" : NEON, border: "none", borderRadius: "8px", color: creating ? "#E8EDFF" : "#06080F", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}>
          {creating ? "Cancelar" : "+ Nueva publicación"}
        </button>
      </div>

      {/* Create form */}
      {creating && (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: `1px solid ${NEON}33`, padding: "1.25rem", marginBottom: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", color: NEON, fontSize: "0.9rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Nueva publicación (DRAFT)</h3>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
            <select style={{ ...inputStyle, flex: 1, minWidth: 140 }} value={newPub.platform} onChange={e => setNewPub(p => ({ ...p, platform: e.target.value }))}>
              {Object.keys(PLATFORM_ICONS).map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <select style={{ ...inputStyle, flex: 1, minWidth: 140 }} value={newPub.type} onChange={e => setNewPub(p => ({ ...p, type: e.target.value }))}>
              {["POST", "STORY", "REEL", "VIDEO", "CAROUSEL"].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <textarea style={{ ...inputStyle, minHeight: 100, resize: "vertical", marginBottom: "0.75rem" }} placeholder="Caption de la publicación…" value={newPub.caption} onChange={e => setNewPub(p => ({ ...p, caption: e.target.value }))} />
          <button onClick={handleCreate} style={{ padding: "0.5rem 1.25rem", background: NEON, border: "none", borderRadius: "8px", color: "#06080F", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}>
            Guardar como DRAFT
          </button>
        </div>
      )}

      {/* Grid of publications */}
      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
      ) : pubs.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>No hay publicaciones.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
          {pubs.map(pub => {
            const color = STATUS_COLORS[pub.status] ?? "#4A5070";
            return (
              <div key={pub.id} style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {/* Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    <span style={{ fontSize: "1.25rem" }}>{PLATFORM_ICONS[pub.platform] ?? "📄"}</span>
                    <div>
                      <div style={{ fontSize: "0.8rem", fontWeight: 700, color: "#E8EDFF" }}>{pub.platform}</div>
                      <div style={{ fontSize: "0.7rem", color: "#4A5070" }}>{pub.type}</div>
                    </div>
                  </div>
                  <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${color}22`, color, border: `1px solid ${color}44` }}>
                    {pub.status}
                  </span>
                </div>

                {/* Caption preview */}
                {pub.caption && (
                  <p style={{ color: "#A0AAC8", fontSize: "0.82rem", lineHeight: 1.5, margin: 0, display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {pub.caption}
                  </p>
                )}

                {pub.aiGenerated && (
                  <span style={{ fontSize: "0.7rem", color: CYAN, background: `${CYAN}15`, padding: "2px 8px", borderRadius: 4, border: `1px solid ${CYAN}33`, alignSelf: "flex-start" }}>✨ IA</span>
                )}

                {/* Actions */}
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "auto" }}>
                  {pub.status === "APPROVED" && (
                    <button onClick={() => handlePublish(pub.id)} style={{ padding: "4px 10px", background: `${NEON}15`, border: `1px solid ${NEON}44`, borderRadius: 4, color: NEON, fontSize: "0.75rem", cursor: "pointer" }}>
                      Publicar
                    </button>
                  )}
                  {["DRAFT", "READY"].includes(pub.status) && (
                    <span style={{ fontSize: "0.7rem", color: YELLOW }}>Pendiente revisión</span>
                  )}
                  <span style={{ flex: 1 }} />
                  <span style={{ fontSize: "0.7rem", color: "#4A5070" }}>{new Date(pub.createdAt).toLocaleDateString("es-AR")}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </AdminLayout>
  );
}
