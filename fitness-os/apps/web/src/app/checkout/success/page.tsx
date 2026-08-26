"use client";
/**
 * /checkout/success — MercadoPago redirige aquí tras pago exitoso.
 * Muestra confirmación y enlace a /mis-compras.
 */
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const NEON = "#00FF87";
const CYAN = "#00F5FF";

function SuccessContent() {
  const searchParams = useSearchParams();
  const paymentId = searchParams.get("payment_id") ?? "";
  const status = searchParams.get("status") ?? "";
  const [dots, setDots] = useState(".");

  // Animación de puntos mientras procesa
  useEffect(() => {
    const t = setInterval(() => setDots(d => d.length >= 3 ? "." : d + "."), 500);
    return () => clearInterval(t);
  }, []);

  const isPending = status === "pending" || status === "in_process";

  return (
    <div style={{ textAlign: "center", maxWidth: 520, margin: "0 auto", padding: "0 1.5rem" }}>
      {/* Ícono animado */}
      <div style={{
        width: 90, height: 90, borderRadius: "50%",
        background: `radial-gradient(circle, ${NEON}22, transparent)`,
        border: `2px solid ${NEON}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        margin: "0 auto 2rem",
        fontSize: "2.5rem",
        boxShadow: `0 0 40px ${NEON}44`,
      }}>
        {isPending ? "⏳" : "✓"}
      </div>

      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: "2.5rem", fontWeight: 800,
        color: NEON,
        textShadow: `0 0 20px ${NEON}66`,
        marginBottom: "0.75rem",
      }}>
        {isPending ? "Pago en proceso" : "¡Pago confirmado!"}
      </h1>

      <p style={{ color: "#A0AAC8", fontSize: "1.05rem", lineHeight: 1.6, marginBottom: "2rem" }}>
        {isPending
          ? `Tu pago está siendo procesado${dots} Te enviaremos un email cuando se confirme.`
          : "Tu compra fue procesada exitosamente. Tu producto ya está disponible en tu biblioteca."}
      </p>

      {paymentId && (
        <div style={{
          background: "#0D0F1A", border: "1px solid #1A1F35",
          borderRadius: 10, padding: "0.85rem 1.25rem",
          marginBottom: "2rem", display: "inline-block",
        }}>
          <span style={{ color: "#4A5070", fontSize: "0.78rem", letterSpacing: "0.08em" }}>ID DE PAGO </span>
          <span style={{ color: "#E8EDFF", fontSize: "0.9rem", fontFamily: "monospace" }}>{paymentId}</span>
        </div>
      )}

      {!isPending && (
        <div style={{
          background: `${NEON}0D`, border: `1px solid ${NEON}33`,
          borderRadius: 12, padding: "1.25rem 1.5rem",
          marginBottom: "2rem", textAlign: "left",
        }}>
          <p style={{ color: NEON, fontWeight: 700, margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
            ⚡ Acceso inmediato
          </p>
          <p style={{ color: "#A0AAC8", margin: 0, fontSize: "0.88rem", lineHeight: 1.5 }}>
            Ingresá a <strong style={{ color: "#E8EDFF" }}>Mis Compras</strong> para descargar tu producto.
            También te enviamos el enlace de descarga por email.
          </p>
        </div>
      )}

      <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
        <Link href="/mis-compras" style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          background: `linear-gradient(135deg, ${NEON}, #00D4A0)`,
          color: "#06080F", fontWeight: 800, fontSize: "0.95rem",
          padding: "0.75rem 1.5rem", borderRadius: 10, textDecoration: "none",
          boxShadow: `0 0 20px ${NEON}44`,
        }}>
          📥 Mis Compras →
        </Link>
        <Link href="/tienda" style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          background: "transparent", border: "1px solid #2A2F45",
          color: "#A0AAC8", fontWeight: 600, fontSize: "0.95rem",
          padding: "0.75rem 1.5rem", borderRadius: 10, textDecoration: "none",
        }}>
          Seguir comprando
        </Link>
      </div>
    </div>
  );
}

export default function CheckoutSuccessPage() {
  return (
    <div style={{
      minHeight: "100vh",
      background: "#07080F",
      color: "#E8EDFF",
      fontFamily: "'DM Sans', system-ui, sans-serif",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Nav */}
      <nav style={{ background: "#0A0C18", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
      </nav>

      {/* Content */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", padding: "4rem 1rem" }}>
        <Suspense fallback={<p style={{ color: CYAN, textAlign: "center", width: "100%" }}>Procesando...</p>}>
          <SuccessContent />
        </Suspense>
      </div>

      {/* Footer simple */}
      <div style={{ padding: "1.5rem", textAlign: "center", borderTop: "1px solid #1A1F35", color: "#3A3F55", fontSize: "0.78rem" }}>
        Fitness Business OS · Soporte: soporte@fitnessbusiness.com
      </div>
    </div>
  );
}
