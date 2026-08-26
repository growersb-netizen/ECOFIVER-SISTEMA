"use client";
/**
 * /checkout/success — MercadoPago redirige aquí tras pago exitoso.
 * Muestra confirmación y enlace a /mis-compras.
 */
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const NEON   = "#00FF87";
const CEREZA = "#DE3163";
const BODY   = "#B8C4E0";
const MUTED  = "#7A87A8";
const DIM    = "#4A5570";

const STORE_NAME = process.env["NEXT_PUBLIC_STORE_NAME"] ?? "FITNESS BUSINESS OS";

function SuccessContent() {
  const searchParams = useSearchParams();
  const paymentId = searchParams.get("payment_id") ?? "";
  const status    = searchParams.get("status") ?? "";
  const [dots, setDots] = useState(".");

  useEffect(() => {
    const t = setInterval(() => setDots(d => d.length >= 3 ? "." : d + "."), 500);
    return () => clearInterval(t);
  }, []);

  const isPending = status === "pending" || status === "in_process";

  return (
    <div style={{ textAlign: "center", maxWidth: 520, margin: "0 auto", padding: "0 1.5rem" }}>
      {/* Ícono animado — Cereza para el checkmark */}
      <div style={{
        width: 90, height: 90, borderRadius: "50%",
        background: isPending ? `rgba(0,255,135,0.08)` : `rgba(222,49,99,0.12)`,
        border: `2px solid ${isPending ? NEON : CEREZA}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        margin: "0 auto 2rem", fontSize: "2.5rem",
        boxShadow: `0 0 40px ${isPending ? NEON : CEREZA}33`,
      }}>
        {isPending ? "⏳" : "✓"}
      </div>

      {/* Label de confirmación — CEREZA */}
      {!isPending && (
        <p style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontSize: "0.72rem", fontWeight: 700,
          letterSpacing: "0.2em", textTransform: "uppercase",
          color: CEREZA, marginBottom: "0.75rem",
          textShadow: `0 0 14px ${CEREZA}44`,
        }}>
          ✦ COMPRA CONFIRMADA ✦
        </p>
      )}

      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: "2.75rem", fontWeight: 800,
        color: isPending ? NEON : CEREZA,
        textShadow: `0 0 24px ${isPending ? NEON : CEREZA}55`,
        marginBottom: "0.85rem",
      }}>
        {isPending ? "PAGO EN PROCESO" : "¡PAGO CONFIRMADO!"}
      </h1>

      <p style={{ color: BODY, fontSize: "1.05rem", lineHeight: 1.7, marginBottom: "2rem" }}>
        {isPending
          ? `Tu pago está siendo procesado${dots} Te enviaremos un email cuando se confirme.`
          : "Tu compra fue procesada exitosamente. Revisá tu email — te enviamos el enlace de descarga."}
      </p>

      {paymentId && (
        <div style={{
          background: "#0D0F1A", border: "1px solid #1A1F35",
          borderRadius: 10, padding: "0.85rem 1.25rem",
          marginBottom: "2rem", display: "inline-block",
        }}>
          <span style={{ color: MUTED, fontSize: "0.72rem", letterSpacing: "0.1em" }}>ID DE PAGO </span>
          <span style={{ color: "#F0F4FF", fontSize: "0.9rem", fontFamily: "monospace" }}>{paymentId}</span>
        </div>
      )}

      {!isPending && (
        <div style={{
          background: `rgba(222,49,99,0.07)`,
          border: `1px solid ${CEREZA}30`,
          borderRadius: 12, padding: "1.25rem 1.5rem",
          marginBottom: "2rem", textAlign: "left",
        }}>
          <p style={{ color: CEREZA, fontWeight: 700, margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
            ⚡ Acceso inmediato
          </p>
          <p style={{ color: BODY, margin: 0, fontSize: "0.88rem", lineHeight: 1.6 }}>
            Ingresá a <strong style={{ color: "#F0F4FF" }}>Mis Compras</strong> o revisá tu email para descargar tu producto.
          </p>
        </div>
      )}

      <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
        <Link href="/mis-compras" style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          background: `linear-gradient(135deg, ${CEREZA}, #B82050)`,
          color: "#fff", fontWeight: 800, fontSize: "0.95rem",
          padding: "0.8rem 1.5rem", borderRadius: 10, textDecoration: "none",
          boxShadow: `0 4px 20px ${CEREZA}44`,
        }}>
          📥 Mis Compras →
        </Link>
        <Link href="/tienda" style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          background: "transparent", border: "1px solid #2A2F45",
          color: BODY, fontWeight: 600, fontSize: "0.95rem",
          padding: "0.8rem 1.5rem", borderRadius: 10, textDecoration: "none",
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
      minHeight: "100vh", background: "#07080F", color: "#F0F4FF",
      fontFamily: "'DM Sans', system-ui, sans-serif",
      display: "flex", flexDirection: "column",
    }}>
      <nav style={{
        background: "#0A0C18", borderBottom: `1px solid ${CEREZA}22`,
        padding: "0 1.5rem", height: 60,
        display: "flex", alignItems: "center",
      }}>
        <Link href="/" style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 800, fontSize: "1.1rem",
          letterSpacing: "0.08em", color: NEON, textDecoration: "none",
        }}>
          {STORE_NAME}
        </Link>
      </nav>

      <div style={{ flex: 1, display: "flex", alignItems: "center", padding: "4rem 1rem" }}>
        <Suspense fallback={<p style={{ color: CEREZA, textAlign: "center", width: "100%" }}>Procesando...</p>}>
          <SuccessContent />
        </Suspense>
      </div>

      <div style={{
        padding: "1.5rem", textAlign: "center",
        borderTop: "1px solid #1A1F35",
        color: DIM, fontSize: "0.78rem",
      }}>
        {STORE_NAME} · <span style={{ color: MUTED }}>soporte@fitnessbusiness.com</span>
      </div>
    </div>
  );
}
