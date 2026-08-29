"use client";
/**
 * Blog & Email Marketing — Fase 11.
 * Posts del blog + campañas de email. Los endpoints son /api/v1/posts y /api/v1/campaigns.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const YELLOW = "#FFE234";
const PINK = "#FF2D9C";

const API = process.env["NEXT_PUBLIC_API_URL"] ?? "https://fitness-api-production-fff4.up.railway.app";

function getToken() {
  return localStorage.getItem("fitness_access_token") ?? "";
}

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#4A5070", PUBLISHED: NEON, ARCHIVED: "#3A3F55",
  SCHEDULED: CYAN, SENT: "#7C4DFF", PENDING: YELLOW,
};

interface Post {
  id: string;
  title: string;
  slug: string;
  status: string;
  publishedAt?: string;
  createdAt: string;
  excerpt?: string;
}

interface Campaign {
  id: string;
  subject: string;
  status: string;
  sentAt?: string;
  createdAt: string;
  recipientCount?: number;
}

export default function BlogPage() {
  const [tab, setTab] = useState<"posts" | "campaigns">("posts");
  const [posts, setPosts] = useState<Post[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${getToken()}` };
      const [postsRes, campaignsRes] = await Promise.all([
        fetch(`${API}/api/v1/posts`, { headers }),
        fetch(`${API}/api/v1/campaigns`, { headers }),
      ]);
      if (postsRes.ok) {
        const d = await postsRes.json();
        setPosts(d.data ?? d.posts ?? []);
      }
      if (campaignsRes.ok) {
        const d = await campaignsRes.json();
        setCampaigns(d.data ?? d.campaigns ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handlePublishPost = async (id: string) => {
    const res = await fetch(`${API}/api/v1/posts/${id}/publish`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (res.ok) { setMsg("Post publicado"); load(); }
    else setMsg("Error al publicar");
  };

  const handleSendCampaign = async (id: string) => {
    if (!confirm("¿Enviar esta campaña de email a todos los leads? Esta acción es real.")) return;
    const res = await fetch(`${API}/api/v1/campaigns/${id}/send`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (res.ok) { setMsg("Campaña enviada"); load(); }
    else setMsg("Error al enviar campaña");
  };

  return (
    <AdminLayout>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>
          Blog & Email Marketing
        </h1>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {(["posts", "campaigns"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: "0.4rem 1rem", background: tab === t ? `${NEON}20` : "transparent",
              border: `1px solid ${tab === t ? NEON : "#2A3050"}`, borderRadius: 6,
              color: tab === t ? NEON : "#6B7494", fontSize: "0.8rem", cursor: "pointer"
            }}>
              {t === "posts" ? "📝 Posts" : "📧 Email Campaigns"}
            </button>
          ))}
        </div>
      </div>

      {msg && (
        <div style={{ marginBottom: "1rem", padding: "0.75rem 1rem", background: `${NEON}15`, border: `1px solid ${NEON}33`, borderRadius: 8, color: NEON, fontSize: "0.85rem" }}>
          {msg} <button onClick={() => setMsg("")} style={{ background: "none", border: "none", color: NEON, cursor: "pointer", marginLeft: "0.5rem" }}>✕</button>
        </div>
      )}

      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
      ) : tab === "posts" ? (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
          {posts.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>📝</div>
              <p style={{ color: "#4A5070", margin: 0, fontSize: "0.9rem" }}>
                No hay posts todavía. Usá la IA para generar contenido de blog.
              </p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                    {["Título", "Slug", "Estado", "Publicado", "Acciones"].map(h => (
                      <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {posts.map(post => {
                    const color = STATUS_COLORS[post.status] ?? "#4A5070";
                    return (
                      <tr key={post.id} style={{ borderBottom: "1px solid #0F111E" }}>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <div style={{ color: "#E8EDFF", fontWeight: 500 }}>{post.title}</div>
                          {post.excerpt && <div style={{ color: "#4A5070", fontSize: "0.75rem", marginTop: "0.2rem" }}>{post.excerpt.slice(0, 60)}…</div>}
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>{post.slug}</td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${color}22`, color, border: `1px solid ${color}44` }}>
                            {post.status}
                          </span>
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>
                          {post.publishedAt ? new Date(post.publishedAt).toLocaleDateString("es-AR") : "—"}
                        </td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          {post.status === "DRAFT" && (
                            <button onClick={() => handlePublishPost(post.id)} style={{
                              padding: "3px 8px", background: `${NEON}15`, border: `1px solid ${NEON}44`,
                              borderRadius: 4, color: NEON, fontSize: "0.7rem", cursor: "pointer"
                            }}>
                              Publicar
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* Campañas de email */
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden" }}>
          {campaigns.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>📧</div>
              <p style={{ color: "#4A5070", margin: 0, fontSize: "0.9rem" }}>
                No hay campañas. Usá la sección IA para generar email subjects y crear campañas.
              </p>
              <div style={{ marginTop: "1rem", padding: "0.85rem", background: "#070810", borderRadius: 8, border: "1px solid #1A2040", fontSize: "0.8rem", color: "#6B7494", maxWidth: 400, margin: "1rem auto 0" }}>
                <strong style={{ color: YELLOW }}>⚠️ Requiere</strong> <code style={{ color: CYAN }}>RESEND_API_KEY</code> en Railway para envío real de emails.
              </div>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #1A1F35" }}>
                    {["Asunto", "Estado", "Destinatarios", "Enviado", "Acciones"].map(h => (
                      <th key={h} style={{ padding: "0.75rem 1rem", textAlign: "left", color: "#4A5070", fontWeight: 600, fontSize: "0.75rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map(camp => {
                    const color = STATUS_COLORS[camp.status] ?? "#4A5070";
                    return (
                      <tr key={camp.id} style={{ borderBottom: "1px solid #0F111E" }}>
                        <td style={{ padding: "0.75rem 1rem", color: "#E8EDFF", fontWeight: 500 }}>{camp.subject}</td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${color}22`, color, border: `1px solid ${color}44` }}>
                            {camp.status}
                          </span>
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: CYAN, fontVariantNumeric: "tabular-nums" }}>
                          {camp.recipientCount ?? "—"}
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "#6B7494", fontSize: "0.75rem" }}>
                          {camp.sentAt ? new Date(camp.sentAt).toLocaleDateString("es-AR") : "—"}
                        </td>
                        <td style={{ padding: "0.75rem 1rem" }}>
                          {camp.status === "DRAFT" && (
                            <button onClick={() => handleSendCampaign(camp.id)} style={{
                              padding: "3px 8px", background: `${PINK}15`, border: `1px solid ${PINK}44`,
                              borderRadius: 4, color: PINK, fontSize: "0.7rem", cursor: "pointer"
                            }}>
                              Enviar campaña
                            </button>
                          )}
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
    </AdminLayout>
  );
}
