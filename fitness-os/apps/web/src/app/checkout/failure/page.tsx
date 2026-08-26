"use client";
/**
 * /checkout/failure — MercadoPago redirige aquí si el pago falla o se cancela.
 */
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const NEON = "#00FF87";
const PINK = "#FF2D9C";

const REASONS: Record<string, string> = {
  cc_rejected_bad_filled_security_code: "El código de seguridad de la tarjeta es incorrecto.",
  cc_rejected_bad_filled_date: "La fecha de vencimiento de la tarjeta es incorrecta.",
  cc_rejected_high_risk: "El pago fue rechazado por razones de seguridad.",
  cc_rejected_insufficient_amount: "La tarjeta no tiene fondos suficientes.",
  cc_rejected_other_reason: "El pago fue rechazado por tu banco. Intentá con otra tarjeta.",
  pending_contingency: "El pago está siendo procesado. Te notificaremos por email.",
  cancelled: "Cancelaste el proceso de pago.",
};

function FailureContent() {
  const searchParams = useSearchParams();
  const status = searchParams.get("status") ?? "";
  const reason = searchParams.get("status_detail") ?? searchParams.get("reason") ?? "";
  const productId = searchParams.get("productId") ?? "";

  const isCancelled = status === "null" || reason === "cancelled" || status === "cancelled";
  const reasonMsg = REASONS[reason] ?? (isCancelled ? "Cancelaste el proceso de pago." : "Ocurrió un problema con el pago. Podés intentar de nuevo.");

  return (
    <div style={{ textAlign: "center", maxWidth: 520, margin: "0 auto", padding: "0 1.5rem" }}>
      {/* Ícono */}
      <div style={{
        width: 90, height: 90, borderRadius: "50%",
        background: `radial-gradient(circle, ${PINK}22, transparent)`,
        border: `2px solid ${PINK}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        margin: "0 auto 2rem", fontSize: "2.5rem",
        boxShadow: `0 0 40px ${PINK}44`,
      }}>
        {isCancelled ? "↩" : "✕"}
      </div>

      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif",
        fontSize: "2.5rem", fontWeight: 800,
        color: PINK,
        textShadow: `0 0 20px ${PINK}66`,
        marginBottom: "0.75rem",
      }}>
        {isCancelled ? "Pago cancelado" : "El pago no pudo procesarse"}
      </h1>

      <p style={{ color: "#A0AAC8", fontSize: "1.05rem", lineHeight: 1.6, marginBottom: "2rem" }}>
        {reasonMsg}
      </p>

      {/* Tips */}
      {!isCancelled && (
        <div style={{
          background: "#0D0F1A", border: "1px solid #1A1F35",
          borderRadius: 12, padding: "1.25rem 1.5rem",
          marginBottom: "2rem", textAlign: "left",
        }}>
          <p style={{ color: "#E8EDFF", fontWeight: 700, margin: "0 0 0.75rem", fontSize: "0.9rem" }}>
            💡 ¿Qué podés hacer?
          </p>
          {[
            "Verificá que los datos de la tarjeta sean correctos",
            "Probá con otra tarjeta o método de pago",
            "Contactá a tu banco si el problema persiste",
            "Intentá en unos minutos si fue un error temporal",
          ].map((tip, i) => (
            <div key={i} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <span style={{ color: NEON, flexShrink: 0 }}>→</span>
              <span style={{ color: "#A0AAC8", fontSize: "0.88rem" }}>{tip}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
        {productId && (
          <Link href={`/checkout?productId=${productId}`} style={{
            display: "inline-flex", alignItems: "center", gap: "0.5rem",
            background: `linear-gradient(135deg, ${NEON}, #00D4A0)`,
            color: "#06080F", fontWeight: 800, fontSize: "0.95rem",
            padding: "0.75rem 1.5rem", borderRadius: 10, textDecoration: "none",
            boxShadow: `0 0 20px ${NEON}44`,
          }}>
            🔄 Intentar de nuevo
          </Link>
        )}
        <Link href="/tienda" style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          background: "transparent", border: "1px solid #2A2F45",
          color: "#A0AAC8", fontWeight: 600, fontSize: "0.95rem",
          padding: "0.75rem 1.5rem", borderRadius: 10, textDecoration: "none",
        }}>
          ← Volver a la tienda
        </Link>
      </div>

      <p style={{ color: "#3A3F55", fontSize: "0.8rem", marginTop: "2.5rem" }}>
        ¿Necesitás ayuda? Escribinos a{" "}
        <a href="mailto:soporte@fitnessbusiness.com" style={{ color: "#4A5070" }}>
          soporte@fitnessbusiness.com
        </a>
      </p>
    </div>
  );
}

export default function CheckoutFailurePage() {
  return (
    <div style={{
      minHeight: "100vh",
      background: "#07080F",
      color: "#E8EDFF",
      fontFamily: "'DM Sans', system-ui, sans-serif",
      display: "flex",
      flexDirection: "column",
    }}>
      <nav style={{ background: "#0A0C18", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
      </nav>
      <div style={{ flex: 1, display: "flex", alignItems: "center", padding: "4rem 1rem" }}>
        <Suspense fallback={<p style={{ color: PINK, textAlign: "center", width: "100%" }}>Cargando...</p>}>
          <FailureContent />
        </Suspense>
      </div>
      <div style={{ padding: "1.5rem", textAlign: "center", borderTop: "1px solid #1A1F35", color: "#3A3F55", fontSize: "0.78rem" }}>
        Fitness Business OS · Soporte: soporte@fitnessbusiness.com
      </div>
    </div>
  );
}
