"use client";
/**
 * Checkout — Fase 04.
 * Crea la preferencia de pago en MercadoPago y redirige al checkout externo.
 */
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { initCheckout, validateCoupon } from "@/lib/store-api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";

function CheckoutForm() {
  const searchParams = useSearchParams();
  const productId = searchParams.get("productId") ?? "";
  const affiliateSlug = searchParams.get("ref") ?? undefined;

  const [coupon, setCoupon] = useState("");
  const [couponResult, setCouponResult] = useState<{ valid: boolean; discountPct?: number; message?: string } | null>(null);
  const [validatingCoupon, setValidatingCoupon] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleValidateCoupon = async () => {
    if (!coupon) return;
    setValidatingCoupon(true);
    try {
      const res = await validateCoupon(coupon, [productId]);
      setCouponResult(res);
    } catch {
      setCouponResult({ valid: false, message: "Cupón inválido o expirado" });
    } finally {
      setValidatingCoupon(false);
    }
  };

  const handleCheckout = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await initCheckout({
        items: [{ productId, quantity: 1 }],
        couponCode: couponResult?.valid ? coupon : undefined,
        affiliateSlug,
        channel: "WEB",
      });
      // Redirigir a MercadoPago
      window.location.href = res.checkoutUrl;
    } catch (e: unknown) {
      setError((e as Error).message ?? "Error iniciando el pago. Intentá de nuevo.");
      setLoading(false);
    }
  };

  if (!productId) {
    return (
      <div style={{ textAlign: "center", padding: "3rem" }}>
        <p style={{ color: "#4A5070" }}>No se especificó un producto.</p>
        <Link href="/tienda" style={{ color: NEON }}>Volver a la tienda →</Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 480, margin: "3rem auto", padding: "0 1.5rem" }}>
      <Link href="/tienda" style={{ color: "#4A5070", textDecoration: "none", fontSize: "0.85rem" }}>← Volver a la tienda</Link>

      <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2.25rem", fontWeight: 800, margin: "1.25rem 0", color: "#E8EDFF" }}>
        Finalizar compra
      </h1>

      <div style={{ background: "#0D0F1A", borderRadius: 14, border: "1px solid #1A1F35", padding: "1.5rem", marginBottom: "1.25rem" }}>
        <h3 style={{ margin: "0 0 1rem", color: "#6B7494", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Cupón de descuento</h3>
        <div style={{ display: "flex", gap: "0.65rem" }}>
          <input
            value={coupon}
            onChange={e => { setCoupon(e.target.value.toUpperCase()); setCouponResult(null); }}
            placeholder="Ingresá tu código"
            style={{ flex: 1, background: "#0A0C18", border: `1px solid ${couponResult?.valid ? NEON : "#1A1F35"}`, borderRadius: 8, color: "#E8EDFF", padding: "0.6rem 0.85rem", fontSize: "0.9rem", outline: "none" }}
          />
          <button
            onClick={handleValidateCoupon}
            disabled={!coupon || validatingCoupon}
            style={{ padding: "0.6rem 1rem", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 8, color: "#A0AAC8", fontSize: "0.85rem", cursor: "pointer" }}
          >
            {validatingCoupon ? "…" : "Aplicar"}
          </button>
        </div>
        {couponResult && (
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: couponResult.valid ? NEON : PINK }}>
            {couponResult.valid ? `✓ Descuento de ${couponResult.discountPct}% aplicado` : couponResult.message ?? "Cupón inválido"}
          </p>
        )}
      </div>

      <div style={{ background: "#0D0F1A", borderRadius: 14, border: "1px solid #1A1F35", padding: "1.5rem", marginBottom: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "1rem", borderBottom: "1px solid #1A1F35", marginBottom: "1rem" }}>
          <span style={{ color: "#A0AAC8", fontSize: "0.9rem" }}>Producto digital</span>
          <span style={{ color: "#4A5070", fontSize: "0.8rem" }}>Descarga instantánea ⚡</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ color: "#6B7494", fontSize: "0.85rem" }}>Total</span>
          <span style={{ color: NEON, fontSize: "1.5rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700 }}>
            Se calcula en el siguiente paso
          </span>
        </div>
      </div>

      {error && (
        <div style={{ padding: "0.75rem 1rem", background: `${PINK}15`, border: `1px solid ${PINK}33`, borderRadius: 8, color: PINK, fontSize: "0.85rem", marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      <button
        onClick={handleCheckout}
        disabled={loading}
        style={{
          width: "100%", padding: "0.95rem 1rem",
          background: loading ? "#1A1F35" : `linear-gradient(135deg, ${NEON}, #00D4A0)`,
          border: "none", borderRadius: 12,
          color: loading ? "#4A5070" : "#06080F",
          fontWeight: 800, fontSize: "1.05rem", cursor: loading ? "not-allowed" : "pointer",
          transition: "background 0.2s",
        }}
      >
        {loading ? "Procesando…" : "Pagar con MercadoPago →"}
      </button>

      <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "center", gap: "1.5rem", fontSize: "0.78rem", color: "#3A3F55" }}>
        <span>🔒 Pago seguro</span>
        <span>⚡ Acceso inmediato</span>
        <span>💳 Todas las tarjetas</span>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <>
      <nav style={{ background: "#0A0C18", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
      </nav>
      <Suspense fallback={<div style={{ padding: "4rem", textAlign: "center", color: "#4A5070" }}>Cargando checkout…</div>}>
        <CheckoutForm />
      </Suspense>
    </>
  );
}
