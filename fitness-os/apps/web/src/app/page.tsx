/**
 * Home de la tienda — Fase 03.
 * Muestra categorías y productos destacados.
 */
import Link from "next/link";
import { getPublishedProducts, getCategories, StoreProduct, StoreCategory } from "@/lib/store-api";
import HoverCard from "@/components/HoverCard";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";

async function getFeaturedProducts(): Promise<StoreProduct[]> {
  try {
    const data = await getPublishedProducts({ pageSize: 8 });
    return data.products ?? data.data ?? [];
  } catch {
    return [];
  }
}

async function getCats(): Promise<StoreCategory[]> {
  try {
    const data = await getCategories();
    return data.categories ?? data.data ?? [];
  } catch {
    return [];
  }
}

function formatPrice(product: StoreProduct) {
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  if (!price) return "";
  return `$${Number(price.basePrice).toLocaleString("es-AR")} ${price.currency}`;
}

export default async function HomePage() {
  const [products, categories] = await Promise.all([getFeaturedProducts(), getCats()]);

  return (
    <>
      {/* Nav */}
      <nav style={{ position: "sticky", top: 0, zIndex: 100, background: "rgba(6,8,15,0.95)", backdropFilter: "blur(12px)", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center", gap: "1.5rem" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.15rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
        <div style={{ flex: 1 }} />
        <Link href="/tienda" style={{ color: "#A0AAC8", textDecoration: "none", fontSize: "0.9rem" }}>Tienda</Link>
        <Link href="/tienda" style={{ padding: "0.4rem 1.1rem", background: NEON, borderRadius: 8, color: "#06080F", textDecoration: "none", fontWeight: 700, fontSize: "0.85rem" }}>
          Ver todo
        </Link>
      </nav>

      {/* Hero */}
      <section style={{ padding: "5rem 1.5rem 4rem", textAlign: "center", position: "relative", overflow: "hidden" }}>
        {/* Glow BG */}
        <div style={{ position: "absolute", inset: 0, background: `radial-gradient(ellipse at 50% 0%, ${NEON}0A 0%, transparent 60%)`, pointerEvents: "none" }} />
        <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "0.8rem", fontWeight: 700, letterSpacing: "0.2em", textTransform: "uppercase", color: CYAN, marginBottom: "1rem" }}>
          Transformá tu cuerpo con contenido digital premium
        </p>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "clamp(3.5rem, 8vw, 6.5rem)", fontWeight: 800, lineHeight: 0.9, margin: "0 auto 1.5rem", maxWidth: 900 }}>
          <span style={{ color: NEON, textShadow: `0 0 20px ${NEON}66, 0 0 60px ${NEON}22` }}>PROGRAMAS</span>
          <br />
          <span style={{ color: "#E8EDFF" }}>Y GUÍAS DE</span>
          <br />
          <span style={{ color: CYAN, textShadow: `0 0 20px ${CYAN}66` }}>FITNESS</span>
        </h1>
        <p style={{ color: "#6B7494", fontSize: "1.05rem", maxWidth: 500, margin: "0 auto 2rem", lineHeight: 1.6 }}>
          Descargá al instante. Programas diseñados por coaches especializadas. Resultados reales.
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/tienda" style={{ padding: "0.75rem 2rem", background: NEON, borderRadius: 10, color: "#06080F", textDecoration: "none", fontWeight: 700, fontSize: "1rem" }}>
            Ver programas →
          </Link>
          <Link href="/tienda?categoria=programas-transformacion" style={{ padding: "0.75rem 2rem", background: "transparent", border: `1px solid ${CYAN}55`, borderRadius: 10, color: CYAN, textDecoration: "none", fontWeight: 600, fontSize: "1rem" }}>
            Transformación total
          </Link>
        </div>
      </section>

      {/* Categories */}
      {categories.length > 0 && (
        <section style={{ padding: "2rem 1.5rem", maxWidth: 1200, margin: "0 auto" }}>
          <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: "0 0 1.25rem", color: "#E8EDFF" }}>Categorías</h2>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            {categories.slice(0, 10).map(cat => (
              <Link key={cat.id} href={`/tienda?categoria=${cat.slug}`} style={{
                padding: "0.45rem 1.1rem", background: "#0D0F1A", border: "1px solid #1A1F35",
                borderRadius: 50, color: "#A0AAC8", textDecoration: "none", fontSize: "0.85rem",
                transition: "all 0.15s",
              }}>
                {cat.name}
                {cat._count && <span style={{ color: "#4A5070", marginLeft: "0.35rem", fontSize: "0.75rem" }}>({cat._count.products})</span>}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Products grid */}
      <section style={{ padding: "1rem 1.5rem 4rem", maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
          <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Productos destacados</h2>
          <Link href="/tienda" style={{ color: NEON, textDecoration: "none", fontSize: "0.85rem" }}>Ver todos →</Link>
        </div>

        {products.length === 0 ? (
          <div style={{ padding: "4rem", textAlign: "center", color: "#4A5070", background: "#0D0F1A", borderRadius: 16, border: "1px solid #1A1F35" }}>
            <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>🏋️</div>
            <p>Próximamente tendremos productos disponibles.</p>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1.25rem" }}>
            {products.map(p => <ProductCard key={p.id} product={p} />)}
          </div>
        )}
      </section>

      {/* Footer */}
      <footer style={{ borderTop: "1px solid #1A1F35", padding: "2rem 1.5rem", textAlign: "center" }}>
        <p style={{ color: "#3A3F55", fontSize: "0.8rem" }}>
          © {new Date().getFullYear()} Fitness Business OS · Todos los derechos reservados
        </p>
      </footer>
    </>
  );
}

function ProductCard({ product }: { product: StoreProduct }) {
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const levelColors: Record<string, string> = { principiante: NEON, intermedio: CYAN, avanzado: PINK };
  const levelColor = product.level ? (levelColors[product.level] ?? CYAN) : CYAN;

  return (
    <Link href={`/tienda/${product.slug}`} style={{ textDecoration: "none" }}>
      <HoverCard hoverBorderColor={`${NEON}55`}>
        {/* Cover */}
        <div style={{ height: 160, background: `linear-gradient(135deg, #0D0F1A 0%, ${NEON}10 50%, ${CYAN}08 100%)`, display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
          <span style={{ fontSize: "2.5rem" }}>
            {product.category?.slug?.includes("glut") ? "🍑" :
             product.category?.slug?.includes("yoga") ? "🧘" :
             product.category?.slug?.includes("nutri") ? "🥗" :
             product.category?.slug?.includes("abdomen") ? "⚡" :
             product.category?.slug?.includes("postparto") ? "💪" : "🏋️"}
          </span>
          {product.level && (
            <span style={{ position: "absolute", top: 10, right: 10, padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${levelColor}22`, color: levelColor, border: `1px solid ${levelColor}44` }}>
              {product.level}
            </span>
          )}
        </div>

        {/* Content */}
        <div style={{ padding: "1rem", flex: 1, display: "flex", flexDirection: "column" }}>
          {product.category && (
            <div style={{ fontSize: "0.7rem", color: CYAN, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.35rem" }}>
              {product.category.name}
            </div>
          )}
          <h3 style={{ color: "#E8EDFF", fontSize: "0.95rem", fontWeight: 600, margin: "0 0 0.5rem", lineHeight: 1.3, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {product.name}
          </h3>
          {product.description && (
            <p style={{ color: "#6B7494", fontSize: "0.8rem", lineHeight: 1.5, margin: "0 0 auto", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
              {product.description}
            </p>
          )}
          <div style={{ marginTop: "0.85rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            {price ? (
              <div>
                <div style={{ color: NEON, fontWeight: 700, fontSize: "1.15rem", fontVariantNumeric: "tabular-nums" }}>
                  ${Number(price.basePrice).toLocaleString("es-AR")}
                </div>
                <div style={{ color: "#4A5070", fontSize: "0.7rem" }}>{price.currency}</div>
              </div>
            ) : <div />}
            {product.durationWeeks && (
              <div style={{ fontSize: "0.75rem", color: "#4A5070" }}>⏱ {product.durationWeeks} sem.</div>
            )}
          </div>
        </div>
      </HoverCard>
    </Link>
  );
}
