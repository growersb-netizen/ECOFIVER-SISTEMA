"use client";
/**
 * Fase 15 — Error boundary global para la tienda.
 */
import Link from "next/link";

const NEON = "#00FF87";
const PINK = "#FF2D9C";

export default function WebError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div style={{ minHeight: "100vh", background: "#06080F", color: "#E8EDFF", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'DM Sans', sans-serif", padding: "2rem" }}>
      <div style={{ maxWidth: 480, textAlign: "center" }}>
        <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🏋️</div>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2.5rem", fontWeight: 800, color: "#E8EDFF", margin: "0 0 0.75rem" }}>
          Ups, algo falló
        </h1>
        <p style={{ color: "#6B7494", fontSize: "0.95rem", marginBottom: "2rem", lineHeight: 1.6 }}>
          Ocurrió un error inesperado. Podés intentar de nuevo o volver a la tienda.
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <button onClick={reset} style={{ padding: "0.7rem 1.75rem", background: NEON, border: "none", borderRadius: 10, color: "#06080F", fontWeight: 700, fontSize: "0.95rem", cursor: "pointer" }}>
            Intentar de nuevo
          </button>
          <Link href="/tienda" style={{ padding: "0.7rem 1.75rem", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 10, color: "#A0AAC8", textDecoration: "none", fontSize: "0.95rem" }}>
            Volver a la tienda
          </Link>
        </div>
      </div>
    </div>
  );
}
