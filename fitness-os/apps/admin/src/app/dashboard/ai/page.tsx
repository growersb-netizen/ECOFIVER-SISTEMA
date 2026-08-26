"use client";
/**
 * IA Generativa — Fase 05.
 * Genera contenido en DRAFT vía OpenRouter. La humana revisa y decide qué usar.
 * NUNCA publica directamente.
 */
import { useState } from "react";
import { AdminLayout } from "@/components/AdminLayout";
import { apiClient } from "@/lib/api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";
const YELLOW = "#FFE234";

type GenType = "product-description" | "social-caption" | "email-subject" | "whatsapp-response";

const GEN_TYPES: { id: GenType; label: string; icon: string; desc: string }[] = [
  { id: "product-description", label: "Descripción de producto", icon: "📦", desc: "Genera una descripción motivadora para un producto de fitness" },
  { id: "social-caption", label: "Caption para redes", icon: "📱", desc: "Caption optimizado para Instagram, TikTok o Facebook" },
  { id: "email-subject", label: "Asuntos de email", icon: "📧", desc: "Genera múltiples opciones de asunto para email marketing" },
  { id: "whatsapp-response", label: "Respuesta WhatsApp", icon: "💬", desc: "Sugerencia de respuesta para consulta de cliente" },
];

export default function AIPage() {
  const [genType, setGenType] = useState<GenType>("product-description");
  const [inputs, setInputs] = useState({ name: "", tone: "motivador", length: "medium", platform: "INSTAGRAM", customerMessage: "" });
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setResult(null);
    try {
      let res;
      if (genType === "product-description") {
        res = await apiClient.generateProductDescription({ productId: "temp", productName: inputs.name, tone: inputs.tone, length: inputs.length as "short" | "medium" | "long" });
        setResult(res.description ?? res.content ?? JSON.stringify(res));
      } else if (genType === "social-caption") {
        res = await apiClient.generateSocialCaption({ productId: "temp", productName: inputs.name, platform: inputs.platform as "INSTAGRAM" | "FACEBOOK" | "TIKTOK", tone: inputs.tone });
        setResult(res.caption ?? res.content ?? JSON.stringify(res));
      } else if (genType === "email-subject") {
        const r = await fetch("/api/v1/ai/generate/email-subject", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("access_token")}` },
          body: JSON.stringify({ campaignName: inputs.name, productName: inputs.name, tone: inputs.tone }),
        }).then(r => r.json());
        setResult(Array.isArray(r.subjects) ? r.subjects.join("\n") : JSON.stringify(r));
      } else {
        const r = await fetch("/api/v1/ai/generate/whatsapp-response", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("access_token")}` },
          body: JSON.stringify({ customerMessage: inputs.customerMessage, customerName: "Cliente" }),
        }).then(r => r.json());
        setResult(r.response ?? r.suggestion ?? JSON.stringify(r));
      }
    } catch (e: unknown) {
      setResult(`Error: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (result) {
      navigator.clipboard.writeText(result);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  const inputStyle = {
    background: "#0A0C18", border: "1px solid #1A1F35", borderRadius: "8px",
    color: "#E8EDFF", padding: "0.6rem 0.85rem", fontSize: "0.9rem",
    outline: "none", width: "100%", boxSizing: "border-box" as const,
  };

  const selected = GEN_TYPES.find(g => g.id === genType)!;

  return (
    <AdminLayout>
      <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, marginBottom: "0.25rem" }}>IA Generativa</h1>
      <p style={{ color: "#4A5070", fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Todo el contenido generado queda en <strong style={{ color: YELLOW }}>DRAFT</strong>. La IA no publica — vos decidís qué usar.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: "1.25rem", alignItems: "start" }}>
        {/* Type selector */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {GEN_TYPES.map(g => (
            <button key={g.id} onClick={() => { setGenType(g.id); setResult(null); }} style={{
              padding: "0.85rem 1rem", borderRadius: "10px", textAlign: "left",
              background: genType === g.id ? `${NEON}12` : "#0D0F1A",
              border: `1px solid ${genType === g.id ? `${NEON}44` : "#1A1F35"}`,
              color: genType === g.id ? NEON : "#A0AAC8",
              cursor: "pointer", transition: "all 0.15s",
            }}>
              <div style={{ fontSize: "1.1rem", marginBottom: "0.25rem" }}>{g.icon}</div>
              <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>{g.label}</div>
              <div style={{ fontSize: "0.75rem", color: genType === g.id ? `${NEON}88` : "#4A5070", marginTop: "0.25rem" }}>{g.desc}</div>
            </button>
          ))}
        </div>

        {/* Input + output */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem" }}>
            <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.15rem", margin: "0 0 1rem", color: "#E8EDFF" }}>
              {selected.icon} {selected.label}
            </h2>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {genType !== "whatsapp-response" && (
                <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                  <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                    {genType === "email-subject" ? "Nombre de campaña" : "Nombre del producto"}
                  </span>
                  <input style={inputStyle} value={inputs.name} onChange={e => setInputs(i => ({ ...i, name: e.target.value }))} placeholder={genType === "email-subject" ? "Promo Black Friday 2026" : "Plan Glúteos 30 Días"} />
                </label>
              )}

              {genType === "whatsapp-response" && (
                <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                  <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Mensaje de la cliente</span>
                  <textarea style={{ ...inputStyle, minHeight: 80, resize: "vertical" }} value={inputs.customerMessage} onChange={e => setInputs(i => ({ ...i, customerMessage: e.target.value }))} placeholder="Hola! cuánto cuesta el plan de nutrición?" />
                </label>
              )}

              <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                {genType !== "email-subject" && genType !== "whatsapp-response" && (
                  <label style={{ flex: 1, minWidth: 120, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                    <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Tono</span>
                    <select style={inputStyle} value={inputs.tone} onChange={e => setInputs(i => ({ ...i, tone: e.target.value }))}>
                      {["motivador", "profesional", "cercano", "urgente", "inspirador", "educativo"].map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </label>
                )}
                {genType === "product-description" && (
                  <label style={{ flex: 1, minWidth: 120, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                    <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Extensión</span>
                    <select style={inputStyle} value={inputs.length} onChange={e => setInputs(i => ({ ...i, length: e.target.value }))}>
                      {["short", "medium", "long"].map(l => <option key={l} value={l}>{l === "short" ? "Corto" : l === "medium" ? "Medio" : "Largo"}</option>)}
                    </select>
                  </label>
                )}
                {genType === "social-caption" && (
                  <label style={{ flex: 1, minWidth: 120, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                    <span style={{ color: "#6B7494", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>Plataforma</span>
                    <select style={inputStyle} value={inputs.platform} onChange={e => setInputs(i => ({ ...i, platform: e.target.value }))}>
                      {["INSTAGRAM", "FACEBOOK", "TIKTOK"].map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </label>
                )}
              </div>

              <button onClick={handleGenerate} disabled={loading} style={{
                padding: "0.7rem 1.5rem", background: loading ? "#1A1F35" : NEON,
                border: "none", borderRadius: "8px", color: "#06080F",
                fontWeight: 700, fontSize: "0.9rem", cursor: loading ? "not-allowed" : "pointer",
                alignSelf: "flex-start", transition: "background 0.15s",
              }}>
                {loading ? "Generando con IA…" : "✨ Generar borrador"}
              </button>
            </div>
          </div>

          {/* Result */}
          {result && (
            <div style={{ background: "#0D0F1A", borderRadius: 12, border: `1px solid ${NEON}33`, padding: "1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <span style={{ color: NEON, fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  ✓ BORRADOR GENERADO
                </span>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <span style={{ fontSize: "0.75rem", color: YELLOW, background: `${YELLOW}15`, padding: "2px 8px", borderRadius: 4, border: `1px solid ${YELLOW}33` }}>DRAFT — requiere revisión</span>
                  <button onClick={handleCopy} style={{
                    padding: "2px 10px", background: `${CYAN}15`, border: `1px solid ${CYAN}33`,
                    borderRadius: 4, color: CYAN, fontSize: "0.75rem", cursor: "pointer",
                  }}>
                    {copied ? "✓ Copiado" : "Copiar"}
                  </button>
                </div>
              </div>
              <p style={{ color: "#E8EDFF", fontSize: "0.9rem", lineHeight: 1.7, margin: 0, whiteSpace: "pre-wrap" }}>{result}</p>
            </div>
          )}
        </div>
      </div>
    </AdminLayout>
  );
}
