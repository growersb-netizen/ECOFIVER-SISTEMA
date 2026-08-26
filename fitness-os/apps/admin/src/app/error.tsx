"use client";
/**
 * Fase 15 — Error boundary global para el admin.
 */
import { useEffect } from "react";

const PINK = "#FF2D9C";

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // En producción, loguear a Sentry (cuando esté configurado)
    console.error("[AdminError]", error);
  }, [error]);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#06080F",
      color: "#E8EDFF",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "'DM Sans', sans-serif",
      padding: "2rem",
    }}>
      <div style={{ maxWidth: 480, textAlign: "center" }}>
        <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>⚠️</div>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2rem", fontWeight: 700, color: PINK, margin: "0 0 0.75rem" }}>
          Algo salió mal
        </h1>
        <p style={{ color: "#6B7494", fontSize: "0.9rem", marginBottom: "1.5rem", lineHeight: 1.6 }}>
          {process.env.NODE_ENV === "development"
            ? error.message
            : "Ocurrió un error inesperado. El equipo fue notificado."}
        </p>
        {error.digest && (
          <p style={{ color: "#3A3F55", fontSize: "0.75rem", fontFamily: "monospace", marginBottom: "1.5rem" }}>
            Error ID: {error.digest}
          </p>
        )}
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
          <button
            onClick={reset}
            style={{ padding: "0.6rem 1.5rem", background: "#00FF87", border: "none", borderRadius: 8, color: "#06080F", fontWeight: 700, cursor: "pointer" }}
          >
            Intentar de nuevo
          </button>
          <a
            href="/dashboard"
            style={{ padding: "0.6rem 1.5rem", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 8, color: "#A0AAC8", textDecoration: "none" }}
          >
            Volver al dashboard
          </a>
        </div>
      </div>
    </div>
  );
}
