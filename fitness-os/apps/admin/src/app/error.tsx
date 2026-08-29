"use client";
/**
 * Error boundary global del admin.
 * Detecta ChunkLoadError (cache stale tras deploy) y fuerza recarga automática.
 */
import { useEffect } from "react";

const PINK = "#FF2D9C";
const NEON = "#00FF87";

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[AdminError]", error.name, error.message);

    // ChunkLoadError = el navegador tiene JS viejos cacheados tras un nuevo deploy.
    // Solución: forzar hard-reload para que descargue los chunks nuevos.
    const isChunkError =
      error.name === "ChunkLoadError" ||
      error.message?.includes("ChunkLoadError") ||
      error.message?.includes("Loading chunk") ||
      error.message?.includes("Failed to fetch dynamically imported module") ||
      error.message?.includes("Importing a module script failed");

    if (isChunkError) {
      // Marcar en sessionStorage para no entrar en loop infinito
      const key = "chunk_reload_attempted";
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        window.location.reload();
      } else {
        // Ya intentamos recargar — limpiar y mostrar error normal
        sessionStorage.removeItem(key);
      }
    }
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
        <h1 style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontSize: "2rem",
          fontWeight: 700,
          color: PINK,
          margin: "0 0 0.75rem",
        }}>
          Algo salió mal
        </h1>
        <p style={{ color: "#6B7494", fontSize: "0.9rem", marginBottom: "1.5rem", lineHeight: 1.6 }}>
          {process.env.NODE_ENV === "development"
            ? error.message
            : "Ocurrió un error inesperado. Intentá recargar la página."}
        </p>
        {error.digest && (
          <p style={{ color: "#3A3F55", fontSize: "0.75rem", fontFamily: "monospace", marginBottom: "1.5rem" }}>
            Error ID: {error.digest}
          </p>
        )}
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: "0.6rem 1.5rem",
              background: NEON,
              border: "none",
              borderRadius: 8,
              color: "#06080F",
              fontWeight: 700,
              cursor: "pointer",
              fontSize: "0.9rem",
            }}
          >
            Recargar página
          </button>
          <button
            onClick={reset}
            style={{
              padding: "0.6rem 1.5rem",
              background: "transparent",
              border: `1px solid #2A2F45`,
              borderRadius: 8,
              color: "#A0AAC8",
              cursor: "pointer",
              fontSize: "0.9rem",
            }}
          >
            Intentar de nuevo
          </button>
          <a
            href="/login"
            style={{
              padding: "0.6rem 1.5rem",
              background: "#1A1F35",
              border: "1px solid #2A2F45",
              borderRadius: 8,
              color: "#A0AAC8",
              textDecoration: "none",
              fontSize: "0.9rem",
            }}
          >
            Ir al login
          </a>
        </div>
      </div>
    </div>
  );
}
