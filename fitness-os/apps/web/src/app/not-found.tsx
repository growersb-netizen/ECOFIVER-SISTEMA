/**
 * Página 404 para la tienda.
 */
import Link from "next/link";

const NEON = "#00FF87";
const CYAN = "#00F5FF";

export default function NotFound() {
  return (
    <div style={{ minHeight: "100vh", background: "#06080F", color: "#E8EDFF", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'DM Sans', sans-serif", padding: "2rem" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "clamp(6rem, 20vw, 10rem)", fontWeight: 900, color: "#1A1F35", lineHeight: 1, marginBottom: "1rem" }}>
          404
        </div>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2rem", fontWeight: 700, color: NEON, margin: "0 0 0.75rem" }}>
          Página no encontrada
        </h1>
        <p style={{ color: "#6B7494", fontSize: "0.95rem", marginBottom: "2rem" }}>
          No encontramos lo que buscabas. Puede que el producto haya sido removido o el link esté mal.
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/tienda" style={{ padding: "0.7rem 1.75rem", background: NEON, borderRadius: 10, color: "#06080F", textDecoration: "none", fontWeight: 700 }}>
            Ir a la tienda
          </Link>
          <Link href="/" style={{ padding: "0.7rem 1.75rem", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 10, color: "#A0AAC8", textDecoration: "none" }}>
            Inicio
          </Link>
        </div>
      </div>
    </div>
  );
}
