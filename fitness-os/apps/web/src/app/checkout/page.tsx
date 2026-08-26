"use client";
/**
 * Checkout — Fase 04.
 * Recopila email + nombre → init checkout → redirige a MercadoPago.
 */
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { initCheckout, validateCoupon, getProductBySlug, StoreProduct } from "@/lib/store-api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "#0A0C18",
  border: "1px solid #2A2F45",
  borderRadius: 8,
  color: "#E8EDFF",
  padding: "0.65rem 0.9rem",
  fontSize: "0.9rem",
  outline: "none",
  boxSizing: "border-box",
};

const API_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
const TENANT_SLUG = process.env["NEXT_PUBLIC_TENANT_SLUG"] ?? "";

function CheckoutForm() {
  const searchParams = useSearchParams();
  const productId = searchParams.get("productId") ?? "";
  const affiliateSlug = searchParams.get("ref") ?? undefined;

  const [product, setProduct] = useState<StoreProduct | null>(null);
  const [productLoading, setProductLoading] = useState(true);

  // Cliente
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");

  // Cupón
  const [coupon, setCoupon] = useState("");
  const [couponResult, setCouponResult] = useState<{ valid: boolean; discount?: number; discountPct?: number; message?: string } | null>(null);
  const [validatingCoupon, setValidatingCoupon] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cargar producto por id (desde la API directamente)
  useEffect(() => {
    if (!productId) return;
    fetch(`${API_URL}/api/v1/products/${productId}`, {
      headers: { "Content-Type": "application/json", ...(TENANT_SLUG ? { "X-Tenant-Slug": TENANT_SLUG } : {}) },
    })
      .then(r => r.json() as Promise<{ data?: StoreProduct } | StoreProduct>)
      .then(d => {
        const p = (d as { data?: StoreProduct }).data ?? d as StoreProduct;
        setProduct(p);
      })
      .catch(() => {})
      .finally(() => setProductLoading(false));
  }, [productId]);

  const price = product?.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product?.prices?.[0];
  const basePrice = price ? Number(price.basePrice) : null;
  const discount = couponResult?.valid ? (couponResult.discount ?? (basePrice && couponResult.discountPct ? basePrice * couponResult.discountPct / 100 : 0)) : 0;
  const total = basePrice !== null ? Math.max(0, (basePrice ?? 0) - (discount ?? 0)) : null;

  const handleValidateCoupon = async () => {
    if (!coupon) return;
    setValidatingCoupon(true);
    try {
      const res = await validateCoupon(coupon, [productId]);
      setCouponResult(res as { valid: boolean; discount?: number; discountPct?: number; message?: string });
    } catch {
      setCouponResult({ valid: false, message: "Cupón inválido o expirado" });
    } finally {
      setValidatingCoupon(false);
    }
  };

  const handleCheckout = async () => {
    if (!email || !name) { setError("Completá tu nombre y email"); return; }
    setLoading(true);
    setError(null);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const res = await initCheckout({
        items: [{ productId, quantity: 1 }],
        customer: { email: email.trim().toLowerCase(), name: name.trim(), phone: phone.trim() || undefined },
        couponCode: couponResult?.valid ? coupon : undefined,
        affiliateSlug,
        successUrl: `${origin}/checkout/success?productId=${productId}`,
        failureUrl: `${origin}/checkout/failure?productId=${productId}`,
      });
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

      <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2.25rem", fontWeight: 800, margin: "1.25rem 0 1.5rem", color: "#E8EDFF" }}>
        FINALIZAR COMPRA
      </h1>

      {/* Resumen del producto */}
      {!productLoading && product && (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
            <div>
              {product.category && (
                <p style={{ margin: "0 0 2px", color: CYAN, fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                  {product.category.name}
                </p>
              )}
              <p style={{ margin: 0, color: "#E8EDFF", fontWeight: 600, fontSize: "0.95rem", lineHeight: 1.3 }}>{product.name}</p>
              <p style={{ margin: "4px 0 0", color: "#4A5070", fontSize: "0.78rem" }}>
                ⚡ Descarga instantánea · PDF digital
                {product.durationWeeks ? ` · ${product.durationWeeks} semanas` : ""}
              </p>
            </div>
            {price && (
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <p style={{ margin: 0, color: NEON, fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "1.35rem" }}>
                  ${Number(price.basePrice).toLocaleString("es-AR")}
                </p>
                <p style={{ margin: "2px 0 0", color: "#4A5070", fontSize: "0.72rem" }}>{price.currency}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Datos del cliente */}
      <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem", marginBottom: "1.25rem" }}>
        <h3 style={{ margin: "0 0 1rem", color: "#6B7494", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Tus datos
        </h3>
        <div style={{ marginBottom: "0.75rem" }}>
          <label style={{ display: "block", color: "#4A5070", fontSize: "0.75rem", marginBottom: "5px" }}>NOMBRE *</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Tu nombre completo" style={inputStyle} />
        </div>
        <div style={{ marginBottom: "0.75rem" }}>
          <label style={{ display: "block", color: "#4A5070", fontSize: "0.75rem", marginBottom: "5px" }}>EMAIL *</label>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="tu@email.com" style={inputStyle} />
          <p style={{ margin: "4px 0 0", color: "#3A3F55", fontSize: "0.72rem" }}>Te enviaremos el acceso a tu descarga aquí</p>
        </div>
        <div>
          <label style={{ display: "block", color: "#4A5070", fontSize: "0.75rem", marginBottom: "5px" }}>TELÉFONO (opcional)</label>
          <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+54 9 11 1234-5678" style={inputStyle} />
        </div>
      </div>

      {/* Cupón */}
      <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem", marginBottom: "1.25rem" }}>
        <h3 style={{ margin: "0 0 0.75rem", color: "#6B7494", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>Cupón de descuento</h3>
        <div style={{ display: "flex", gap: "0.65rem" }}>
          <input
            value={coupon}
            onChange={e => { setCoupon(e.target.value.toUpperCase()); setCouponResult(null); }}
            placeholder="Código de descuento"
            style={{ ...inputStyle, flex: 1 }}
          />
          <button
            onClick={handleValidateCoupon}
            disabled={!coupon || validatingCoupon}
            style={{ padding: "0.6rem 1rem", background: "#1A1F35", border: "1px solid #2A2F45", borderRadius: 8, color: "#A0AAC8", fontSize: "0.85rem", cursor: "pointer", whiteSpace: "nowrap" }}
          >
            {validatingCoupon ? "…" : "Aplicar"}
          </button>
        </div>
        {couponResult && (
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: couponResult.valid ? NEON : PINK }}>
            {couponResult.valid
              ? `✓ Descuento de ${couponResult.discountPct}% aplicado`
              : (couponResult.message ?? "Cupón inválido")}
          </p>
        )}
      </div>

      {/* Resumen de precio */}
      {total !== null && (
        <div style={{ background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35", padding: "1.25rem", marginBottom: "1.25rem" }}>
          {discount > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
              <span style={{ color: "#6B7494", fontSize: "0.85rem" }}>Subtotal</span>
              <span style={{ color: "#4A5070", fontSize: "0.85rem", textDecoration: "line-through" }}>${basePrice?.toLocaleString("es-AR")}</span>
            </div>
          )}
          {discount > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
              <span style={{ color: NEON, fontSize: "0.85rem" }}>Descuento</span>
              <span style={{ color: NEON, fontSize: "0.85rem" }}>-${discount.toLocaleString("es-AR")}</span>
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "space-between", paddingTop: discount > 0 ? "0.75rem" : 0, borderTop: discount > 0 ? "1px solid #1A1F35" : "none" }}>
            <span style={{ color: "#E8EDFF", fontWeight: 700 }}>Total a pagar</span>
            <span style={{ color: NEON, fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.5rem" }}>
              ${total.toLocaleString("es-AR")} <span style={{ color: "#4A5070", fontSize: "0.75rem", fontWeight: 400 }}>ARS</span>
            </span>
          </div>
        </div>
      )}

      {error && (
        <div style={{ padding: "0.75rem 1rem", background: `${PINK}15`, border: `1px solid ${PINK}33`, borderRadius: 8, color: PINK, fontSize: "0.85rem", marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      <button
        onClick={handleCheckout}
        disabled={loading || !email || !name}
        style={{
          width: "100%", padding: "0.95rem 1rem",
          background: (loading || !email || !name) ? "#1A1F35" : `linear-gradient(135deg, ${NEON}, #00D4A0)`,
          border: "none", borderRadius: 12,
          color: (loading || !email || !name) ? "#4A5070" : "#06080F",
          fontWeight: 800, fontSize: "1.05rem",
          cursor: (loading || !email || !name) ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Redirigiendo a MercadoPago…" : "Pagar con MercadoPago →"}
      </button>

      <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "center", gap: "1.5rem", fontSize: "0.78rem", color: "#3A3F55" }}>
        <span>🔒 Pago seguro SSL</span>
        <span>⚡ Acceso inmediato</span>
        <span>💳 Todas las tarjetas</span>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#07080F", color: "#E8EDFF", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <nav style={{ background: "#0A0C18", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
      </nav>
      <Suspense fallback={<div style={{ padding: "4rem", textAlign: "center", color: "#4A5070" }}>Cargando checkout…</div>}>
        <CheckoutForm />
      </Suspense>
    </div>
  );
}
