/**
 * Detalle de producto — SEO-optimizado, mobile-first.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getProductBySlug, StoreProduct } from "@/lib/store-api";

const NEON    = "#00FF87";
const CYAN    = "#00F5FF";
const CEREZA  = "#DE3163";
const CEREZA2 = "#B82050";
const TEXT    = "#F0F4FF";
const BODY    = "#B8C4E0";
const MUTED   = "#7A87A8";
const DIM     = "#4A5570";

const STORE_NAME = process.env["NEXT_PUBLIC_STORE_NAME"] ?? "NexFit";

export const revalidate = 300;

interface Props {
  params: { slug: string };
}

async function loadProduct(slug: string): Promise<StoreProduct | null> {
  try {
    const data = await getProductBySlug(slug);
    // API returns { data: product }
    if (data && typeof data === "object" && "data" in data && data.data) return data.data as StoreProduct;
    if (data && typeof data === "object" && "product" in data && data.product) return data.product as StoreProduct;
    return data as StoreProduct;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await loadProduct(params.slug);
  if (!product) return { title: "Producto no encontrado" };

  const title = `${product.name} | NexFit`;
  const description = product.description?.slice(0, 155) ?? "Programa digital de fitness. Descargá al instante.";
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];

  return {
    title,
    description,
    keywords: [product.name, product.category?.name ?? "", "fitness", "programa digital", "guía fitness"].filter(Boolean),
    openGraph: {
      title,
      description,
      type: "website",
      locale: "es_AR",
    },
    other: price ? {
      "product:price:amount": String(price.basePrice),
      "product:price:currency": price.currency,
    } : {},
  };
}

function categoryArt(slug?: string): { bg: string; accent: string; label: string; img?: string } {
  const s = slug ?? "";
  if (s.includes("abdomen") || s.includes("core")) return { bg: "linear-gradient(135deg,#0A0A04 0%,#1A1800 60%,#FFDD0020 100%)", accent: "#FFD700", label: "ABDOMEN & CORE" };
  if (s.includes("glut") || s.includes("pierna"))  return { bg: "linear-gradient(135deg,#0A0418 0%,#2A0830 60%,#DE316322 100%)", accent: "#FF6B9D", label: "GLÚTEOS & PIERNAS" };
  if (s.includes("nutri"))                          return { bg: "linear-gradient(135deg,#030E06 0%,#062010 60%,#00FF8720 100%)", accent: "#00FF87", label: "NUTRICIÓN" };
  if (s.includes("casa"))                           return { bg: "linear-gradient(135deg,#08080A 0%,#101018 60%,#8888FF22 100%)", accent: "#8888FF", label: "EN CASA" };
  if (s.includes("yoga") || s.includes("flex"))     return { bg: "linear-gradient(135deg,#040A14 0%,#071830 60%,#00F5FF18 100%)", accent: "#00F5FF", label: "YOGA & FLEX" };
  if (s.includes("transformacion"))                 return { bg: "linear-gradient(135deg,#06000E 0%,#100018 60%,#DE316328 100%)", accent: "#DE3163", label: "TRANSFORMACIÓN", img: "/images/cat-09.webp" };
  if (s.includes("postparto"))                      return { bg: "linear-gradient(135deg,#0A040E 0%,#1A0824 60%,#C97BFF22 100%)", accent: "#C97BFF", label: "POSTPARTO" };
  if (s.includes("mindset") || s.includes("habit")) return { bg: "linear-gradient(135deg,#04080E 0%,#081420 60%,#00BFFF20 100%)", accent: "#00BFFF", label: "MINDSET", img: "/images/cat-11.webp" };
  if (s.includes("receta"))                         return { bg: "linear-gradient(135deg,#030E06 0%,#062010 60%,#00FF8720 100%)", accent: "#00FF87", label: "RECETAS", img: "/images/cat-12.webp" };
  if (s.includes("desafio"))                        return { bg: "linear-gradient(135deg,#0E0400 0%,#200800 60%,#FF450020 100%)", accent: "#FF4500", label: "DESAFÍOS", img: "/images/cat-13.webp" };
  if (s.includes("vip") || s.includes("bundle") || s.includes("pack")) return { bg: "linear-gradient(135deg,#0A0800 0%,#1A1200 60%,#FFD70025 100%)", accent: "#FFD700", label: "VIP / PACK", img: "/images/cat-14.webp" };
  if (s.includes("hombre"))                         return { bg: "linear-gradient(135deg,#040A0E 0%,#081420 60%,#00C8FF22 100%)", accent: "#00C8FF", label: "PARA HOMBRES", img: "/images/cat-15.webp" };
  if (s.includes("fuerza") || s.includes("musc"))   return { bg: "linear-gradient(135deg,#060008 0%,#120020 60%,#AA00FF22 100%)", accent: "#AA00FF", label: "FUERZA", img: "/images/cat-16.webp" };
  if (s.includes("rendimiento") || s.includes("deport")) return { bg: "linear-gradient(135deg,#000A08 0%,#001A12 60%,#00FF8728 100%)", accent: "#00FF87", label: "RENDIMIENTO", img: "/images/cat-17.webp" };
  return { bg: "linear-gradient(135deg,#06080F 0%,#0D1020 60%,#DE316318 100%)", accent: "#DE3163", label: "FITNESS" };
}

export default async function ProductPage({ params }: Props) {
  const product = await loadProduct(params.slug);
  if (!product) notFound();

  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const art = categoryArt(product.category?.slug);

  // JSON-LD structured data for Google
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.description,
    category: product.category?.name,
    ...(price && {
      offers: {
        "@type": "Offer",
        price: String(price.basePrice),
        priceCurrency: price.currency,
        availability: "https://schema.org/InStock",
      },
    }),
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      {/* Nav */}
      <nav style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "rgba(6,8,15,0.97)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid #1A1F35",
        padding: "0 1rem", height: 56,
        display: "flex", alignItems: "center", gap: "1rem",
      }}>
        <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <img src="/images/logo-1.webp" alt={STORE_NAME} style={{ height: 32, width: 32, objectFit: "contain", borderRadius: 4 }} />
          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1rem", letterSpacing: "0.08em", color: NEON, whiteSpace: "nowrap" }}>{STORE_NAME}</span>
        </Link>
        <div style={{ flex: 1 }} />
        <Link href="/tienda" style={{ color: "#A0AAC8", textDecoration: "none", fontSize: "0.82rem", whiteSpace: "nowrap" }}>← Tienda</Link>
      </nav>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "1.5rem 1rem 3rem" }}>

        {/* Breadcrumb */}
        <div style={{ display: "flex", gap: "0.35rem", alignItems: "center", marginBottom: "1.25rem", fontSize: "0.75rem", color: MUTED, flexWrap: "wrap" }}>
          <Link href="/tienda" style={{ color: MUTED, textDecoration: "none" }}>Tienda</Link>
          {product.category && <><span>›</span><Link href={`/tienda?categoria=${product.category.slug}`} style={{ color: CEREZA, textDecoration: "none" }}>{product.category.name}</Link></>}
          <span>›</span>
          <span style={{ color: BODY, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "40vw" }}>{product.name}</span>
        </div>

        {/* Hero cover — mobile visible */}
        <div style={{
          height: 200, borderRadius: 14,
          background: art.bg,
          display: "flex", alignItems: "center", justifyContent: "center",
          marginBottom: "1.5rem",
          border: `1px solid ${art.accent}33`,
          position: "relative", overflow: "hidden",
        }}>
          {art.img && (
            <img
              src={art.img}
              alt={art.label}
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.7, borderRadius: 14 }}
            />
          )}
          {art.img && (
            <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.6) 100%)", borderRadius: 14, pointerEvents: "none" }} />
          )}
          {!art.img && <div style={{ position: "absolute", bottom: -30, right: -30, width: 160, height: 160, borderRadius: "50%", border: `2px solid ${art.accent}25`, pointerEvents: "none" }} />}
          {!art.img && <div style={{ position: "absolute", top: -20, left: -20, width: 100, height: 100, borderRadius: "50%", border: `1px solid ${art.accent}18`, pointerEvents: "none" }} />}
          <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg, ${art.accent}88 0%, transparent 100%)` }} />
          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1rem", fontWeight: 800, letterSpacing: "0.2em", color: art.img ? "#fff" : art.accent, opacity: art.img ? 0.9 : 0.7, textTransform: "uppercase", position: "relative" }}>
            {art.label}
          </span>
        </div>

        {/* Category & Title */}
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
          {product.category && (
            <span style={{ padding: "3px 10px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${CEREZA}18`, color: CEREZA, border: `1px solid ${CEREZA}44`, textTransform: "uppercase", letterSpacing: "0.08em" }}>
              {product.category.name}
            </span>
          )}
        </div>
        <h1 style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontSize: "clamp(1.75rem, 6vw, 3rem)", fontWeight: 800, lineHeight: 1.05,
          margin: "0 0 1rem", color: TEXT,
        }}>
          {product.name}
        </h1>

        {/* Two-column layout: stacks to 1 col on mobile */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: "1.5rem",
        }}
          className="product-detail-grid"
        >
          {/* BUY BOX — primero en mobile */}
          <div>
            <div style={{
              background: "#0D0F1A", borderRadius: 16,
              border: `1px solid ${CEREZA}44`, padding: "1.5rem",
              position: "sticky", top: 68,
              boxShadow: `0 0 40px ${CEREZA}10`,
            }}>
              {price && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <div style={{ color: "#4A5070", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "0.35rem" }}>Precio</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                    <span style={{ color: NEON, fontSize: "2.25rem", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
                      ${Number(price.basePrice).toLocaleString("es-AR")}
                    </span>
                    <span style={{ color: "#4A5070", fontSize: "0.82rem" }}>{price.currency}</span>
                  </div>
                  <div style={{ color: "#4A5070", fontSize: "0.75rem", marginTop: "0.2rem" }}>Pago único · Acceso de por vida</div>
                </div>
              )}

              <a
                href={`/checkout?productId=${product.id}`}
                style={{
                  display: "block", width: "100%", padding: "0.9rem 1rem",
                  background: `linear-gradient(135deg, ${CEREZA}, #B82050)`,
                  borderRadius: 10, color: "#fff", textAlign: "center",
                  fontWeight: 800, fontSize: "1.05rem", textDecoration: "none",
                  letterSpacing: "0.02em", boxSizing: "border-box",
                  boxShadow: `0 4px 20px ${CEREZA}44`,
                }}
              >
                Comprar ahora →
              </a>

              <div style={{ marginTop: "1.1rem", paddingTop: "1.1rem", borderTop: "1px solid #1A1F35" }}>
                {[
                  ["⚡", "Descarga inmediata después del pago"],
                  ["🔒", "Pago seguro con MercadoPago"],
                  ["📱", "Compatible con cualquier dispositivo"],
                  ["♾️", "Acceso de por vida"],
                ].map(([icon, text]) => (
                  <div key={text} style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.5rem", fontSize: "0.78rem", color: BODY }}>
                    <span>{icon}</span><span>{text}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* DESCRIPTION */}
          <div>
            {product.description && (
              <div style={{ lineHeight: 1.75, color: BODY, fontSize: "0.95rem", marginBottom: "1.75rem" }}>
                {product.description.split("\n").map((line, i) => (
                  <p key={i} style={{ margin: "0 0 0.75rem" }}>{line}</p>
                ))}
              </div>
            )}

            {/* What's included */}
            <div style={{ background: "#0D0F1A", borderRadius: 14, border: "1px solid #1A1F35", padding: "1.25rem", marginBottom: "1.5rem" }}>
              <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.15rem", fontWeight: 700, color: "#E8EDFF", margin: "0 0 0.85rem" }}>
                ¿Qué incluye?
              </h2>
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
                {[
                  "Contenido en formato PDF descargable",
                  "Guía detallada con instrucciones paso a paso",
                  "Plan estructurado semana a semana",
                  product.category?.name ? `Enfoque: ${product.category.name}` : "Material de alta calidad",
                  "Acceso de por vida, sin vencimiento",
                  "Compatible con cualquier dispositivo",
                ].map((item, i) => (
                  <li key={i} style={{ display: "flex", gap: "0.55rem", alignItems: "flex-start", fontSize: "0.88rem", color: BODY }}>
                    <span style={{ color: NEON, flexShrink: 0, marginTop: "0.1rem" }}>✓</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* SEO-rich FAQ block */}
            <div style={{ background: "#0D0F1A", borderRadius: 14, border: "1px solid #1A1F35", padding: "1.25rem" }}>
              <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.15rem", fontWeight: 700, color: "#E8EDFF", margin: "0 0 0.85rem" }}>
                Preguntas frecuentes
              </h2>
              {[
                ["¿Cómo accedo al contenido?", "Una vez confirmado el pago recibís el enlace de descarga por email de forma inmediata."],
                ["¿Necesito experiencia previa?", "Cada programa indica el nivel requerido. Si no está especificado, está diseñado para cualquier nivel."],
                ["¿Puedo usarlo desde el celular?", "Sí, todos los materiales son compatibles con smartphones, tablets y computadoras."],
                ["¿Tiene fecha de vencimiento?", "No. El acceso es de por vida. Descargás el material y es tuyo para siempre."],
              ].map(([q, a]) => (
                <details key={q as string} style={{ borderBottom: "1px solid #1A1F35", paddingBottom: "0.75rem", marginBottom: "0.75rem" }}>
                  <summary style={{ cursor: "pointer", color: "#E8EDFF", fontSize: "0.88rem", fontWeight: 600, listStyle: "none", userSelect: "none", paddingTop: "0.1rem" }}>
                    {q}
                  </summary>
                  <p style={{ color: BODY, fontSize: "0.85rem", lineHeight: 1.6, margin: "0.5rem 0 0" }}>{a}</p>
                </details>
              ))}
            </div>
          </div>
        </div>

        {/* Related CTA */}
        <div style={{ marginTop: "2.5rem", textAlign: "center" }}>
          <Link href="/tienda" style={{ color: "#6B7494", textDecoration: "none", fontSize: "0.85rem" }}>
            ← Ver todos los programas
          </Link>
        </div>
      </div>

      {/* Responsive grid CSS */}
      <style>{`
        @media (min-width: 768px) {
          .product-detail-grid {
            grid-template-columns: 360px minmax(0, 1fr) !important;
          }
          .product-detail-grid > div:first-child {
            order: 2;
          }
          .product-detail-grid > div:last-child {
            order: 1;
          }
        }
        details summary::-webkit-details-marker { display: none; }
        details summary::before { content: "+ "; color: ${CEREZA}; }
        details[open] summary::before { content: "− "; color: ${CEREZA}; }
      `}</style>
    </>
  );
}
