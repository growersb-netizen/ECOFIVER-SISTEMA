/**
 * Detalle de producto — Fase 03.
 * Muestra toda la info del producto + botón de compra.
 */
import Link from "next/link";
import { notFound } from "next/navigation";
import { getProductBySlug, StoreProduct, initCheckout } from "@/lib/store-api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";

export const revalidate = 120;

interface Props {
  params: { slug: string };
}

async function loadProduct(slug: string): Promise<StoreProduct | null> {
  try {
    const data = await getProductBySlug(slug);
    if ("product" in data && data.product) return data.product;
    return data as StoreProduct;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: Props) {
  const product = await loadProduct(params.slug);
  if (!product) return { title: "Producto no encontrado" };
  return {
    title: product.name,
    description: product.description?.slice(0, 160),
  };
}

export default async function ProductPage({ params }: Props) {
  const product = await loadProduct(params.slug);
  if (!product) notFound();

  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const levelColors: Record<string, string> = { principiante: NEON, intermedio: CYAN, avanzado: PINK };
  const levelColor = product.level ? (levelColors[product.level] ?? CYAN) : CYAN;

  return (
    <>
      {/* Nav */}
      <nav style={{ position: "sticky", top: 0, zIndex: 100, background: "rgba(6,8,15,0.95)", backdropFilter: "blur(12px)", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center", gap: "1.5rem" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
        <div style={{ flex: 1 }} />
        <Link href="/tienda" style={{ color: "#A0AAC8", textDecoration: "none", fontSize: "0.85rem" }}>← Tienda</Link>
      </nav>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "2.5rem 1.5rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: "3rem", alignItems: "start" }}>
          {/* Left — details */}
          <div>
            {/* Breadcrumb */}
            <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", marginBottom: "1.25rem", fontSize: "0.8rem", color: "#4A5070" }}>
              <Link href="/tienda" style={{ color: "#4A5070", textDecoration: "none" }}>Tienda</Link>
              <span>›</span>
              {product.category && <Link href={`/tienda?categoria=${product.category.slug}`} style={{ color: "#4A5070", textDecoration: "none" }}>{product.category.name}</Link>}
              {product.category && <span>›</span>}
              <span style={{ color: "#6B7494" }}>{product.name}</span>
            </div>

            {/* Title */}
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.75rem" }}>
              {product.category && (
                <span style={{ padding: "3px 10px", borderRadius: 4, fontSize: "0.72rem", fontWeight: 700, background: `${CYAN}15`, color: CYAN, border: `1px solid ${CYAN}33`, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  {product.category.name}
                </span>
              )}
              {product.level && (
                <span style={{ padding: "3px 10px", borderRadius: 4, fontSize: "0.72rem", fontWeight: 700, background: `${levelColor}15`, color: levelColor, border: `1px solid ${levelColor}33` }}>
                  {product.level}
                </span>
              )}
            </div>
            <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "clamp(2rem, 5vw, 3.25rem)", fontWeight: 800, lineHeight: 1, margin: "0 0 1.25rem", color: "#E8EDFF" }}>
              {product.name}
            </h1>

            {/* Meta tags */}
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
              {product.durationWeeks && <Chip icon="⏱" text={`${product.durationWeeks} semanas`} />}
              {product.objective && <Chip icon="🎯" text={product.objective} />}
              {product.place && <Chip icon="📍" text={product.place} />}
              {product.equipment && <Chip icon="🏋️" text={product.equipment} />}
              {product.productType === "DIGITAL" && <Chip icon="⚡" text="Descarga instantánea" color={NEON} />}
            </div>

            {/* Description */}
            {product.description && (
              <div style={{ lineHeight: 1.75, color: "#A0AAC8", fontSize: "0.95rem", marginBottom: "2rem" }}>
                {product.description.split("\n").map((line, i) => <p key={i} style={{ margin: "0 0 0.75rem" }}>{line}</p>)}
              </div>
            )}

            {/* What's included */}
            <div style={{ background: "#0D0F1A", borderRadius: 14, border: "1px solid #1A1F35", padding: "1.5rem", marginBottom: "2rem" }}>
              <h3 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.15rem", fontWeight: 700, color: "#E8EDFF", margin: "0 0 1rem" }}>¿Qué incluye?</h3>
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {[
                  "PDF descargable con el programa completo",
                  "Guía de ejercicios con instrucciones detalladas",
                  "Plan semanal estructurado",
                  product.objective ? `Enfocado en: ${product.objective}` : "Contenido de alta calidad",
                  "Acceso de por vida",
                ].map((item, i) => (
                  <li key={i} style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", fontSize: "0.9rem", color: "#A0AAC8" }}>
                    <span style={{ color: NEON, flexShrink: 0, marginTop: "0.1rem" }}>✓</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Right — buy box */}
          <div style={{ position: "sticky", top: 80 }}>
            <div style={{ background: "#0D0F1A", borderRadius: 16, border: "1px solid #1A1F35", padding: "1.75rem" }}>
              {price && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <div style={{ color: "#4A5070", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "0.35rem" }}>Precio</div>
                  <div style={{ color: NEON, fontSize: "2.5rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
                    ${Number(price.basePrice).toLocaleString("es-AR")}
                  </div>
                  <div style={{ color: "#4A5070", fontSize: "0.82rem", marginTop: "0.25rem" }}>{price.currency} · Pago único</div>
                </div>
              )}

              <BuyButton productId={product.id} />

              <div style={{ marginTop: "1.25rem", paddingTop: "1.25rem", borderTop: "1px solid #1A1F35" }}>
                {[
                  ["⚡", "Acceso inmediato después del pago"],
                  ["🔒", "Pago seguro con MercadoPago"],
                  ["📱", "Compatible con todos los dispositivos"],
                ].map(([icon, text]) => (
                  <div key={text} style={{ display: "flex", gap: "0.6rem", alignItems: "center", marginBottom: "0.6rem", fontSize: "0.8rem", color: "#6B7494" }}>
                    <span>{icon}</span><span>{text}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Chip({ icon, text, color = "#6B7494" }: { icon: string; text: string; color?: string }) {
  return (
    <span style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center", padding: "0.3rem 0.7rem", background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 50, fontSize: "0.8rem", color }}>
      <span>{icon}</span><span>{text}</span>
    </span>
  );
}

function BuyButton({ productId }: { productId: string }) {
  // This is a Server Component — the form action triggers a server action
  return (
    <form action={async () => {
      "use server";
      const { checkoutUrl } = await initCheckout({
        items: [{ productId, quantity: 1 }],
        channel: "WEB",
      });
      // redirect handled client-side via the form submit response
      console.log("Checkout URL:", checkoutUrl);
    }}>
      <input type="hidden" name="productId" value={productId} />
      <a
        href={`/checkout?productId=${productId}`}
        style={{
          display: "block", width: "100%", padding: "0.85rem 1rem",
          background: `linear-gradient(135deg, ${NEON}, #00D4A0)`,
          borderRadius: 10, color: "#06080F", textAlign: "center",
          fontWeight: 800, fontSize: "1.05rem", textDecoration: "none",
          letterSpacing: "0.02em", boxSizing: "border-box",
        }}
      >
        Comprar ahora →
      </a>
    </form>
  );
}
