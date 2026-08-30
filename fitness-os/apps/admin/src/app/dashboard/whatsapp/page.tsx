"use client";
/**
 * WhatsApp Business — Fase 07.
 * Panel de conversaciones y configuración de autopilot.
 */
import { useEffect, useState, useCallback } from "react";
import { AdminLayout } from "@/components/AdminLayout";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";
const YELLOW = "#FFE234";

const API = process.env["NEXT_PUBLIC_API_URL"] ?? "https://fitness-api-production-fff4.up.railway.app";

function getToken() {
  return localStorage.getItem("fitness_access_token") ?? "";
}

interface Conversation {
  id: string;
  channel: string;
  contactPhone?: string;
  contactName?: string;
  status: string;
  lastMessageAt?: string;
  unreadCount?: number;
  messages?: Message[];
}

interface Message {
  id: string;
  role: string;
  content: string;
  createdAt: string;
}

interface AutopilotConfig {
  mode: "MANUAL" | "COPILOT" | "AUTOPILOT";
  enabled: boolean;
}

export default function WhatsAppPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [autopilot, setAutopilot] = useState<AutopilotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [sendText, setSendText] = useState("");
  const [sending, setSending] = useState(false);
  const [tab, setTab] = useState<"conversations" | "config">("conversations");

  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      // Las conversaciones de WA están en CRM
      const res = await fetch(`${API}/api/v1/crm/conversations?channel=WHATSAPP`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) { setConfigured(false); return; }
      const data = await res.json();
      setConversations(data.data ?? data.conversations ?? []);
      setConfigured(true);
    } catch {
      setConfigured(false);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAutopilot = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/whatsapp/autopilot`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAutopilot(data.data);
      }
    } catch { /* no configurado */ }
  }, []);

  useEffect(() => {
    loadConversations();
    loadAutopilot();
  }, [loadConversations, loadAutopilot]);

  const handleSelectConv = async (conv: Conversation) => {
    setSelected(conv);
    // Cargar mensajes
    const res = await fetch(`${API}/api/v1/crm/conversations/${conv.id}/messages`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (res.ok) {
      const data = await res.json();
      setSelected({ ...conv, messages: data.data ?? data.messages ?? [] });
    }
  };

  const handleSend = async () => {
    if (!selected?.contactPhone || !sendText.trim()) return;
    setSending(true);
    try {
      const res = await fetch(`${API}/api/v1/whatsapp/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ to: selected.contactPhone, message: sendText.trim(), type: "text" }),
      });
      if (res.ok) {
        setSendText("");
        await handleSelectConv(selected);
      }
    } finally {
      setSending(false);
    }
  };

  const handleAutopilotChange = async (mode: "MANUAL" | "COPILOT" | "AUTOPILOT") => {
    const res = await fetch(`${API}/api/v1/whatsapp/autopilot`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ mode, enabled: mode !== "MANUAL" }),
    });
    if (res.ok) {
      const data = await res.json();
      setAutopilot(data.data);
    }
  };

  if (!configured) {
    return (
      <AdminLayout>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, marginBottom: "1.5rem" }}>
          WhatsApp Business
        </h1>
        <div style={{ padding: "3rem", textAlign: "center", background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>💬</div>
          <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", margin: "0 0 1rem" }}>
            WhatsApp no está configurado
          </h2>
          <p style={{ color: "#6B7494", maxWidth: 480, margin: "0 auto 1.5rem", lineHeight: 1.6 }}>
            Para activar WhatsApp Business necesitás configurar las siguientes variables de entorno en Railway:
          </p>
          <div style={{ textAlign: "left", maxWidth: 500, margin: "0 auto", background: "#070810", borderRadius: 8, padding: "1.25rem", fontFamily: "monospace", fontSize: "0.8rem", color: "#00F5FF", border: "1px solid #1A2040" }}>
            <div style={{ color: "#4A5070", marginBottom: "0.5rem" }}># En Railway → fitness-api → Variables</div>
            <div>WHATSAPP_PHONE_ID=<span style={{ color: "#FFE234" }}>tu_phone_id</span></div>
            <div>WHATSAPP_TOKEN=<span style={{ color: "#FFE234" }}>tu_token_permanente</span></div>
            <div>WHATSAPP_VERIFY_TOKEN=<span style={{ color: "#FFE234" }}>token_verificacion</span></div>
            <div style={{ color: "#4A5070", marginTop: "0.75rem", marginBottom: "0.5rem" }}># En Meta Business → Webhooks</div>
            <div style={{ fontSize: "0.72rem", color: "#A0AAC8", wordBreak: "break-all" }}>
              URL: https://fitness-api-production-fff4.up.railway.app/api/v1/webhooks/whatsapp
            </div>
          </div>
        </div>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>
          WhatsApp Business
        </h1>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {(["conversations", "config"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: "0.4rem 1rem", background: tab === t ? `${NEON}20` : "transparent",
              border: `1px solid ${tab === t ? NEON : "#2A3050"}`, borderRadius: 6,
              color: tab === t ? NEON : "#6B7494", fontSize: "0.8rem", cursor: "pointer"
            }}>
              {t === "conversations" ? "Conversaciones" : "Configuración"}
            </button>
          ))}
        </div>
      </div>

      {tab === "conversations" ? (
        <div style={{ display: "flex", gap: "1rem", height: "calc(100vh - 180px)", minHeight: 400 }}>
          {/* Lista de conversaciones */}
          <div style={{ width: 280, background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "0.85rem 1rem", borderBottom: "1px solid #1A1F35", fontSize: "0.75rem", color: "#4A5070", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Conversaciones ({conversations.length})
            </div>
            <div style={{ overflowY: "auto", flex: 1 }}>
              {loading ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
              ) : conversations.length === 0 ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "#4A5070", fontSize: "0.85rem" }}>
                  No hay conversaciones de WhatsApp todavía.
                </div>
              ) : (
                conversations.map(conv => (
                  <button key={conv.id} onClick={() => handleSelectConv(conv)} style={{
                    width: "100%", textAlign: "left", padding: "0.85rem 1rem",
                    background: selected?.id === conv.id ? "#141728" : "transparent",
                    border: "none", borderBottom: "1px solid #0F111E", cursor: "pointer",
                    display: "flex", flexDirection: "column", gap: "0.25rem"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ color: "#E8EDFF", fontSize: "0.85rem", fontWeight: 500 }}>
                        {conv.contactName ?? conv.contactPhone ?? "Desconocido"}
                      </span>
                      {(conv.unreadCount ?? 0) > 0 && (
                        <span style={{ background: NEON, color: "#07080F", borderRadius: "50%", width: 18, height: 18, fontSize: "0.65rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>
                          {conv.unreadCount}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.72rem", color: "#4A5070" }}>
                      {conv.contactPhone}
                    </div>
                    <span style={{ fontSize: "0.65rem", padding: "1px 6px", borderRadius: 3, background: conv.status === "OPEN" ? `${NEON}15` : "#1A1F35", color: conv.status === "OPEN" ? NEON : "#4A5070" }}>
                      {conv.status}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Ventana de chat */}
          <div style={{ flex: 1, background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {!selected ? (
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#4A5070", flexDirection: "column", gap: "0.75rem" }}>
                <div style={{ fontSize: "2rem" }}>💬</div>
                <div style={{ fontSize: "0.9rem" }}>Seleccioná una conversación</div>
              </div>
            ) : (
              <>
                <div style={{ padding: "1rem", borderBottom: "1px solid #1A1F35", display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <div style={{ width: 36, height: 36, borderRadius: "50%", background: `${CYAN}20`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1rem" }}>
                    👤
                  </div>
                  <div>
                    <div style={{ color: "#E8EDFF", fontSize: "0.9rem", fontWeight: 500 }}>{selected.contactName ?? "Contacto"}</div>
                    <div style={{ color: "#4A5070", fontSize: "0.75rem" }}>{selected.contactPhone}</div>
                  </div>
                </div>

                {/* Mensajes */}
                <div style={{ flex: 1, overflowY: "auto", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {(selected.messages ?? []).map(msg => (
                    <div key={msg.id} style={{ alignSelf: msg.role === "user" ? "flex-start" : "flex-end", maxWidth: "70%" }}>
                      <div style={{
                        padding: "0.5rem 0.85rem", borderRadius: 10,
                        background: msg.role === "user" ? "#141728" : `${NEON}15`,
                        color: msg.role === "user" ? "#E8EDFF" : NEON,
                        fontSize: "0.85rem", lineHeight: 1.5,
                        border: msg.role === "user" ? "1px solid #1A2040" : `1px solid ${NEON}33`,
                      }}>
                        {msg.content}
                      </div>
                      <div style={{ fontSize: "0.65rem", color: "#4A5070", marginTop: "0.2rem", textAlign: msg.role === "user" ? "left" : "right" }}>
                        {new Date(msg.createdAt).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Input de envío */}
                <div style={{ padding: "1rem", borderTop: "1px solid #1A1F35", display: "flex", gap: "0.5rem" }}>
                  <input
                    value={sendText}
                    onChange={e => setSendText(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                    placeholder="Escribí un mensaje…"
                    style={{
                      flex: 1, background: "#070810", border: "1px solid #2A3050", borderRadius: 8,
                      padding: "0.6rem 1rem", color: "#E8EDFF", fontSize: "0.85rem", outline: "none"
                    }}
                  />
                  <button
                    onClick={handleSend}
                    disabled={sending || !sendText.trim()}
                    style={{
                      padding: "0.6rem 1.25rem", background: sending ? "#1A1F35" : NEON, border: "none",
                      borderRadius: 8, color: "#07080F", fontWeight: 700, fontSize: "0.8rem", cursor: "pointer"
                    }}
                  >
                    {sending ? "…" : "Enviar"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : (
        /* Configuración de autopilot */
        <div style={{ maxWidth: 600 }}>
          <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.5rem" }}>
            <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.25rem", margin: "0 0 1rem" }}>
              🤖 Modo Autopilot
            </h2>
            <p style={{ color: "#6B7494", fontSize: "0.85rem", marginBottom: "1.25rem", lineHeight: 1.6 }}>
              Configurá cómo la IA responde los mensajes entrantes de WhatsApp.
            </p>

            {(["MANUAL", "COPILOT", "AUTOPILOT"] as const).map(mode => {
              const isActive = autopilot?.mode === mode;
              const labels: Record<string, { icon: string; title: string; desc: string }> = {
                MANUAL: { icon: "🖐", title: "Manual", desc: "Vos respondés todos los mensajes. La IA no interviene." },
                COPILOT: { icon: "🤝", title: "Copiloto", desc: "La IA sugiere respuestas pero vos las enviás." },
                AUTOPILOT: { icon: "🤖", title: "Autopilot", desc: "La IA responde automáticamente usando tu base de conocimiento." },
              };
              const l = labels[mode]!;
              return (
                <button key={mode} onClick={() => handleAutopilotChange(mode)} style={{
                  width: "100%", textAlign: "left", padding: "1rem", marginBottom: "0.75rem",
                  background: isActive ? `${NEON}10` : "#070810",
                  border: `1px solid ${isActive ? NEON : "#1A2040"}`, borderRadius: 8,
                  cursor: "pointer", display: "flex", alignItems: "center", gap: "1rem",
                }}>
                  <span style={{ fontSize: "1.5rem" }}>{l.icon}</span>
                  <div>
                    <div style={{ color: isActive ? NEON : "#E8EDFF", fontWeight: 600, fontSize: "0.9rem" }}>{l.title}</div>
                    <div style={{ color: "#6B7494", fontSize: "0.8rem", marginTop: "0.2rem" }}>{l.desc}</div>
                  </div>
                  {isActive && <div style={{ marginLeft: "auto", color: NEON, fontSize: "0.8rem", fontWeight: 700 }}>✓ Activo</div>}
                </button>
              );
            })}

            <div style={{ marginTop: "1rem", padding: "1rem", background: "#070810", borderRadius: 8, border: "1px solid #1A2040", fontSize: "0.8rem", color: "#6B7494" }}>
              <strong style={{ color: "#A0AAC8" }}>Webhook URL para Meta:</strong><br />
              <code style={{ color: CYAN, fontSize: "0.75rem", wordBreak: "break-all" }}>
                https://fitness-api-production-fff4.up.railway.app/api/v1/webhooks/whatsapp
              </code>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
