"use client";
/**
 * Página de Login del Panel de Administración.
 * Neon dark — Barlow Condensed + DM Sans.
 */

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantSlug, setTenantSlug] = useState(process.env["NEXT_PUBLIC_TENANT_SLUG"] ?? "");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(email, password, tenantSlug || undefined);
      router.push("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Credenciales inválidas");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{
      minHeight: "100vh",
      background: "#07080F",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "1rem",
      fontFamily: "'DM Sans', system-ui, sans-serif",
    }}>
      <div style={{ width: "100%", maxWidth: "400px" }}>
        {/* Logo / marca */}
        <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
          <p style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontSize: "0.7rem",
            letterSpacing: "0.25em",
            textTransform: "uppercase",
            color: "#00F5FF",
            textShadow: "0 0 10px rgba(0,245,255,0.6)",
            marginBottom: "0.5rem",
          }}>
            FITNESS BUSINESS OS
          </p>
          <h1 style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontSize: "2.5rem",
            fontWeight: 800,
            color: "#00FF87",
            textShadow: "0 0 16px rgba(0,255,135,0.5)",
            margin: 0,
          }}>
            PANEL ADMIN
          </h1>
        </div>

        {/* Card */}
        <div style={{
          background: "#0D0F1A",
          border: "1px solid #1E2240",
          borderRadius: "16px",
          padding: "2rem",
        }}>
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: "1.25rem" }}>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#A0AAC8", marginBottom: "6px", letterSpacing: "0.05em" }}>
                EMAIL
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                style={{
                  width: "100%",
                  background: "#070810",
                  border: "1px solid #2A3050",
                  borderRadius: "8px",
                  padding: "0.75rem 1rem",
                  color: "#E8EDFF",
                  fontSize: "0.95rem",
                  outline: "none",
                  boxSizing: "border-box",
                  transition: "border-color 0.2s",
                }}
                onFocus={(e) => e.target.style.borderColor = "#00FF87"}
                onBlur={(e) => e.target.style.borderColor = "#2A3050"}
                placeholder="admin@tutienda.com"
              />
            </div>

            <div style={{ marginBottom: "1.25rem" }}>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#A0AAC8", marginBottom: "6px", letterSpacing: "0.05em" }}>
                CONTRASEÑA
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={{
                  width: "100%",
                  background: "#070810",
                  border: "1px solid #2A3050",
                  borderRadius: "8px",
                  padding: "0.75rem 1rem",
                  color: "#E8EDFF",
                  fontSize: "0.95rem",
                  outline: "none",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => e.target.style.borderColor = "#00FF87"}
                onBlur={(e) => e.target.style.borderColor = "#2A3050"}
              />
            </div>

            {/* Ocultar campo tenant si ya viene pre-llenado desde env var */}
            {!process.env["NEXT_PUBLIC_TENANT_SLUG"] && (
            <div style={{ marginBottom: "2rem" }}>
              <label style={{ display: "block", fontSize: "0.8rem", color: "#A0AAC8", marginBottom: "6px", letterSpacing: "0.05em" }}>
                TENANT <span style={{ color: "#4A5070" }}>(opcional si solo hay uno)</span>
              </label>
              <input
                type="text"
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
                style={{
                  width: "100%",
                  background: "#070810",
                  border: "1px solid #2A3050",
                  borderRadius: "8px",
                  padding: "0.75rem 1rem",
                  color: "#E8EDFF",
                  fontSize: "0.95rem",
                  outline: "none",
                  boxSizing: "border-box",
                }}
                placeholder="mi-fitness-store"
              />
            </div>
            )}
            </div>

            {error && (
              <p style={{
                background: "rgba(255,45,156,0.1)",
                border: "1px solid rgba(255,45,156,0.3)",
                borderRadius: "8px",
                padding: "0.75rem",
                color: "#FF2D9C",
                fontSize: "0.85rem",
                marginBottom: "1.25rem",
              }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                padding: "0.9rem",
                background: loading ? "#1E2240" : "#00FF87",
                border: "none",
                borderRadius: "8px",
                color: loading ? "#4A5070" : "#07080F",
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 700,
                fontSize: "1rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                cursor: loading ? "not-allowed" : "pointer",
                transition: "all 0.2s",
                boxShadow: loading ? "none" : "0 0 20px rgba(0,255,135,0.3)",
              }}
            >
              {loading ? "INGRESANDO..." : "INGRESAR →"}
            </button>
          </form>
        </div>

        <p style={{ textAlign: "center", color: "#4A5070", fontSize: "0.75rem", marginTop: "1.5rem" }}>
          Fitness Business OS · Panel de Administración
        </p>
      </div>
    </main>
  );
}
