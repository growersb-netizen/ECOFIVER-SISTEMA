/**
 * Home de la tienda — Fase 03.
 * Muestra categorías y productos destacados.
 */
import Link from "next/link";
import { getPublishedProducts, getCategories, StoreProduct, StoreCategory } from "@/lib/store-api";
import HoverCard from "@/components/HoverCard";

const NEON    = "#00FF87";
const CYAN    = "#00F5FF";
const CEREZA  = "#DE3163";
// PINK se reserva solo para errores; CEREZA es el tercer color de marca

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
      <nav style={{ position: "sticky", top: 0, zIndex: 100, background: "rgba(6,8,15,0.96)", backdropFilter: "blur(12px)", borderBottom: `1px solid ${CEREZA}22`, padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center", gap: "1.5rem" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.15rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
        <div style={{ flex: 1 }} />
        <Link href="/tienda" style={{ color: "#A0AAC8", textDecoration: "none", fontSize: "0.9rem" }}>Tienda</Link>
        <Link href="/tienda" style={{ padding: "0.4rem 1.1rem", background: `linear-gradient(135deg, ${CEREZA}, #B82050)`, borderRadius: 8, color: "#fff", textDecoration: "none", fontWeight: 700, fontSize: "0.85rem" }}>
          Ver todo
        </Link>
      </nav>

      {/* Hero */}
      <section style={{ padding: "5rem 1.5rem 4rem", textAlign: "center", position: "relative", overflow: "hidden" }}>
        {/* Glow dual: neon top-left + cereza top-right */}
        <div style={{ position: "absolute", inset: 0, background: `radial-gradient(ellipse at 30% 0%, ${NEON}0D 0%, transparent 55%), radial-gradient(ellipse at 75% 0%, ${CEREZA}12 0%, transparent 55%)`, pointerEvents: "none" }} />
        {/* Eyebrow — cereza */}
        <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "0.82rem", fontWeight: 700, letterSpacing: "0.22em", textTransform: "uppercase", color: CEREZA, marginBottom: "1rem", position: "relative" }}>
          ✦ Contenido digital premium para alcanzar tus metas ✦
        </p>
        <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "clamp(3.5rem, 8vw, 6.5rem)", fontWeight: 800, lineHeight: 0.9, margin: "0 auto 1.5rem", maxWidth: 900, position: "relative" }}>
          <span style={{ color: NEON, textShadow: `0 0 20px ${NEON}66, 0 0 60px ${NEON}22` }}>PROGRAMAS</span>
          <br />
          <span style={{ color: "#E8EDFF" }}>Y GUÍAS DE</span>
          <br />
          {/* Cereza en "FITNESS" — la palabra más identitaria */}
          <span style={{ color: CEREZA, textShadow: `0 0 24px ${CEREZA}66, 0 0 60px ${CEREZA}22` }}>FITNESS</span>
        </h1>
        <p style={{ color: "#6B7494", fontSize: "1.05rem", maxWidth: 500, margin: "0 auto 2rem", lineHeight: 1.6, position: "relative" }}>
          Descargá al instante. Programas creados por especialistas en fitness. Para todos los niveles y objetivos.
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap", position: "relative" }}>
          <Link href="/tienda" style={{ padding: "0.75rem 2rem", background: `linear-gradient(135deg, ${CEREZA}, #B82050)`, borderRadius: 10, color: "#fff", textDecoration: "none", fontWeight: 700, fontSize: "1rem", boxShadow: `0 4px 24px ${CEREZA}44` }}>
            Ver programas →
          </Link>
          <Link href="/tienda" style={{ padding: "0.75rem 2rem", background: "transparent", border: `1px solid ${NEON}55`, borderRadius: 10, color: NEON, textDecoration: "none", fontWeight: 600, fontSize: "1rem" }}>
            Explorar catálogo
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
  const levelColors: Record<string, string> = { principiante: NEON, intermedio: CYAN, avanzado: CEREZA };
  const levelColor = product.level ? (levelColors[product.level] ?? CYAN) : CYAN;
  const isBundle = product.productType === "BUNDLE";

  return (
    <Link href={`/tienda/${product.slug}`} style={{ textDecoration: "none" }}>
      <HoverCard hoverBorderColor={`${CEREZA}44`}>
        {/* Cover */}
        <div style={{ height: 160, background: `linear-gradient(135deg, #0D0F1A 0%, ${CEREZA}0A 40%, ${NEON}08 100%)`, display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
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
          {isBundle && (
            <span style={{ position: "absolute", top: 10, left: 10, padding: "2px 8px", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, background: `${CEREZA}22`, color: CEREZA, border: `1px solid ${CEREZA}55` }}>
              PACK
            </span>
          )}
        </div>

        {/* Content */}
        <div style={{ padding: "1rem", flex: 1, display: "flex", flexDirection: "column" }}>
          {product.category && (
            <div style={{ fontSize: "0.7rem", color: CEREZA, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.35rem" }}>
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
