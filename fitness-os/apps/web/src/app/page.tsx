/**
 * Home — Tienda Fitness Business OS
 * Diseño profesional: un color dominante (Cereza), tipografía con intención,
 * sin efectos futuristas genéricos.
 */
import Link from "next/link";
import { getPublishedProducts, getCategories, StoreProduct, StoreCategory } from "@/lib/store-api";
import HoverCard from "@/components/HoverCard";

// ── Paleta ──────────────────────────────────────────────────────────
const NEON    = "#00FF87";   // precios / datos
const CYAN    = "#00F5FF";   // info / hombres
const CEREZA  = "#DE3163";   // marca / CTAs
const CEREZA2 = "#B82050";

// Jerarquía tipográfica — suficientemente clara, nada apagado
const TEXT  = "#F0F4FF";
const BODY  = "#B8C4E0";
const MUTED = "#7A87A8";
const DIM   = "#4A5570";

const STORE_NAME = process.env["NEXT_PUBLIC_STORE_NAME"] ?? "FITNESS BUSINESS OS";

async function getFeaturedProducts(): Promise<StoreProduct[]> {
  try {
    const data = await getPublishedProducts({ pageSize: 8 });
    return data.products ?? data.data ?? [];
  } catch { return []; }
}

async function getCats(): Promise<StoreCategory[]> {
  try {
    const data = await getCategories();
    return data.categories ?? data.data ?? [];
  } catch { return []; }
}

export default async function HomePage() {
  const [products, categories] = await Promise.all([getFeaturedProducts(), getCats()]);

  return (
    <>
      {/* ── Navbar ────────────────────────────────────────────────── */}
      <nav style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "#06080F",
        borderBottom: "1px solid #1A1F35",
        padding: "0 2rem", height: 58,
        display: "flex", alignItems: "center", gap: "2rem",
      }}>
        <Link href="/" style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 800, fontSize: "1.1rem",
          letterSpacing: "0.06em", color: TEXT,
          textDecoration: "none",
        }}>
          {STORE_NAME}
        </Link>
        <div style={{ flex: 1 }} />
        <Link href="/tienda" style={{ color: MUTED, textDecoration: "none", fontSize: "0.85rem", fontWeight: 500 }}>
          Catálogo
        </Link>
        <Link href="/mis-compras" style={{ color: MUTED, textDecoration: "none", fontSize: "0.85rem", fontWeight: 500 }}>
          Mis compras
        </Link>
        <Link href="/tienda" style={{
          padding: "0.45rem 1.25rem",
          background: CEREZA,
          borderRadius: 6, color: "#fff",
          textDecoration: "none", fontWeight: 700, fontSize: "0.85rem",
          letterSpacing: "0.01em",
        }}>
          Comprar
        </Link>
      </nav>

      {/* ── Hero ──────────────────────────────────────────────────── */}
      <section style={{
        padding: "5rem 2rem 5rem",
        maxWidth: 1200, margin: "0 auto",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "4rem",
        alignItems: "center",
      }}
        className="hero-section"
      >
        {/* Texto */}
        <div>
          {/* Raya de color + subtítulo — reemplaza los ✦ genéricos */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
            <div style={{ width: 32, height: 3, background: CEREZA, borderRadius: 2 }} />
            <span style={{ color: CEREZA, fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase" }}>
              Contenido digital para fitness
            </span>
          </div>

          <h1 style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontSize: "clamp(3rem, 6vw, 5.5rem)",
            fontWeight: 800,
            lineHeight: 0.95,
            margin: "0 0 1.75rem",
            color: TEXT,
            letterSpacing: "-0.01em",
          }}>
            PROGRAMAS<br />
            QUE DAN<br />
            <span style={{ color: CEREZA }}>RESULTADOS</span>
          </h1>

          <p style={{
            color: BODY, fontSize: "1rem",
            lineHeight: 1.7, maxWidth: 420,
            margin: "0 0 2.5rem",
          }}>
            Guías y programas de fitness en formato digital. Descargá al instante,
            trabajá a tu ritmo. Creados por especialistas.
          </p>

          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <Link href="/tienda" style={{
              padding: "0.8rem 2rem",
              background: CEREZA,
              borderRadius: 6, color: "#fff",
              textDecoration: "none", fontWeight: 700, fontSize: "0.95rem",
            }}>
              Ver catálogo completo
            </Link>
            <Link href="/mis-compras" style={{
              padding: "0.8rem 1.75rem",
              background: "transparent",
              border: "1px solid #2A3050",
              borderRadius: 6, color: BODY,
              textDecoration: "none", fontWeight: 600, fontSize: "0.95rem",
            }}>
              Mis compras
            </Link>
          </div>

          {/* Stats — reemplaza los trust badges con emojis */}
          <div style={{
            display: "flex", gap: "2.5rem",
            marginTop: "2.5rem",
            paddingTop: "2.5rem",
            borderTop: "1px solid #1A1F35",
          }}>
            {[
              { value: "200+", label: "Programas" },
              { value: "72h", label: "Acceso al link" },
              { value: "100%", label: "Digital, sin envío" },
            ].map(s => (
              <div key={s.label}>
                <p style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontSize: "1.75rem", fontWeight: 800,
                  color: NEON, margin: "0 0 2px",
                  fontVariantNumeric: "tabular-nums",
                }}>
                  {s.value}
                </p>
                <p style={{ color: MUTED, fontSize: "0.78rem", margin: 0 }}>{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Panel visual derecho — categorías como grid limpio */}
        <div style={{
          background: "#0D0F1A",
          border: "1px solid #1A1F35",
          borderRadius: 16,
          padding: "2rem",
        }}>
          <p style={{
            color: MUTED, fontSize: "0.72rem",
            fontWeight: 700, letterSpacing: "0.14em",
            textTransform: "uppercase", margin: "0 0 1.25rem",
          }}>
            Categorías disponibles
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {(categories.slice(0, 8)).map((cat, i) => (
              <Link key={cat.id} href={`/tienda?categoria=${cat.slug}`} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "0.65rem 0.85rem",
                background: "#07080F",
                border: "1px solid #1A1F35",
                borderRadius: 8,
                textDecoration: "none",
                transition: "border-color 0.15s",
              }}
                className="cat-link"
              >
                <span style={{ color: TEXT, fontSize: "0.88rem", fontWeight: 500 }}>
                  {cat.name}
                </span>
                {cat._count && (
                  <span style={{
                    color: MUTED, fontSize: "0.75rem",
                    background: "#1A1F35",
                    padding: "1px 7px", borderRadius: 4,
                  }}>
                    {cat._count.products}
                  </span>
                )}
              </Link>
            ))}
          </div>
          {categories.length > 8 && (
            <Link href="/tienda" style={{
              display: "block", marginTop: "1rem",
              color: CEREZA, fontSize: "0.82rem",
              fontWeight: 600, textDecoration: "none",
              textAlign: "center",
            }}>
              Ver todas las categorías →
            </Link>
          )}
        </div>
      </section>

      {/* ── Productos destacados ──────────────────────────────────── */}
      <section style={{
        padding: "3rem 2rem 5rem",
        maxWidth: 1200, margin: "0 auto",
        borderTop: "1px solid #1A1F35",
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between",
          alignItems: "flex-end", marginBottom: "2rem",
        }}>
          <div>
            <p style={{
              color: CEREZA, fontSize: "0.72rem",
              fontWeight: 700, letterSpacing: "0.14em",
              textTransform: "uppercase", margin: "0 0 0.4rem",
            }}>
              Destacados
            </p>
            <h2 style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: "2rem", fontWeight: 800,
              color: TEXT, margin: 0,
            }}>
              Más populares
            </h2>
          </div>
          <Link href="/tienda" style={{
            color: CEREZA, textDecoration: "none",
            fontSize: "0.88rem", fontWeight: 600,
          }}>
            Ver todos →
          </Link>
        </div>

        {products.length === 0 ? (
          <div style={{
            padding: "4rem", textAlign: "center",
            color: MUTED, background: "#0D0F1A",
            borderRadius: 12, border: "1px solid #1A1F35",
          }}>
            <p style={{ margin: 0, color: BODY }}>Próximamente tendremos productos disponibles.</p>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "1.25rem",
          }}>
            {products.map(p => <ProductCard key={p.id} product={p} />)}
          </div>
        )}
      </section>

      {/* ── Footer ────────────────────────────────────────────────── */}
      <footer style={{
        borderTop: "1px solid #1A1F35",
        padding: "2.5rem 2rem",
      }}>
        <div style={{
          maxWidth: 1200, margin: "0 auto",
          display: "flex", justifyContent: "space-between",
          alignItems: "center", flexWrap: "wrap", gap: "1rem",
        }}>
          <div>
            <p style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 800, fontSize: "1rem",
              letterSpacing: "0.06em", color: TEXT, margin: "0 0 3px",
            }}>
              {STORE_NAME}
            </p>
            <p style={{ color: DIM, fontSize: "0.78rem", margin: 0 }}>
              © {new Date().getFullYear()} · Todos los derechos reservados
            </p>
          </div>
          <nav style={{ display: "flex", gap: "1.5rem" }}>
            <Link href="/tienda" style={{ color: MUTED, textDecoration: "none", fontSize: "0.82rem" }}>Catálogo</Link>
            <Link href="/mis-compras" style={{ color: MUTED, textDecoration: "none", fontSize: "0.82rem" }}>Mis compras</Link>
          </nav>
        </div>
      </footer>

      <style>{`
        /* Hero: dos columnas en desktop, una en mobile */
        .hero-section {
          grid-template-columns: 1fr !important;
        }
        @media (min-width: 900px) {
          .hero-section {
            grid-template-columns: 1fr 1fr !important;
          }
        }
        /* Hover cat links */
        .cat-link:hover {
          border-color: ${CEREZA}55 !important;
        }
      `}</style>
    </>
  );
}

// ── ProductCard — diseño de e-commerce real ─────────────────────────
function ProductCard({ product }: { product: StoreProduct }) {
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const levelColors: Record<string, string> = { principiante: NEON, intermedio: CYAN, avanzado: CEREZA };
  const levelColor = product.level ? (levelColors[product.level] ?? CYAN) : CYAN;
  const isBundle = product.productType === "BUNDLE";

  // Emoji por categoría (placeholder hasta tener imágenes reales)
  const emoji = (() => {
    const slug = product.category?.slug ?? "";
    if (slug.includes("glut") || slug.includes("pierna")) return "🍑";
    if (slug.includes("yoga") || slug.includes("flex"))    return "🧘";
    if (slug.includes("nutri") || slug.includes("receta")) return "🥗";
    if (slug.includes("abdomen") || slug.includes("core")) return "⚡";
    if (slug.includes("postparto"))  return "💪";
    if (slug.includes("mindset"))    return "🧠";
    if (slug.includes("desafio"))    return "🔥";
    if (slug.includes("hombre"))     return "🏋️";
    if (slug.includes("pack") || slug.includes("bundle")) return "⭐";
    return "🏋️";
  })();

  return (
    <Link href={`/tienda/${product.slug}`} style={{ textDecoration: "none", display: "block" }}>
      <article style={{
        background: "#0D0F1A",
        border: "1px solid #1A1F35",
        borderRadius: 12,
        overflow: "hidden",
        display: "flex", flexDirection: "column",
        height: "100%",
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
        className="product-card"
      >
        {/* Cover — limpio, sin gradiente doble */}
        <div style={{
          height: 160,
          background: "#0A0C18",
          display: "flex", alignItems: "center", justifyContent: "center",
          position: "relative",
          borderBottom: "1px solid #1A1F35",
        }}>
          <span style={{ fontSize: "2.5rem", opacity: 0.9 }}>{emoji}</span>

          {/* Badges — top-left y top-right, nunca los dos a la vez en conflicto */}
          <div style={{
            position: "absolute", top: 10, left: 10,
            display: "flex", gap: "0.4rem",
          }}>
            {isBundle && (
              <span style={{
                padding: "2px 8px", borderRadius: 4,
                fontSize: "0.65rem", fontWeight: 700,
                background: `${CEREZA}20`, color: CEREZA,
                border: `1px solid ${CEREZA}44`,
                letterSpacing: "0.06em",
              }}>
                PACK
              </span>
            )}
          </div>
          {product.level && (
            <span style={{
              position: "absolute", top: 10, right: 10,
              padding: "2px 7px", borderRadius: 4,
              fontSize: "0.65rem", fontWeight: 700,
              background: `${levelColor}18`, color: levelColor,
              border: `1px solid ${levelColor}35`,
            }}>
              {product.level}
            </span>
          )}
        </div>

        {/* Content */}
        <div style={{ padding: "1rem 1rem 1.1rem", flex: 1, display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          {/* Categoría — CEREZA, label pequeño */}
          {product.category && (
            <p style={{
              margin: 0,
              fontSize: "0.68rem", color: CEREZA,
              fontWeight: 700, letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}>
              {product.category.name}
            </p>
          )}

          {/* Nombre */}
          <h3 style={{
            margin: 0,
            color: TEXT, fontSize: "0.92rem", fontWeight: 700,
            lineHeight: 1.3,
            display: "-webkit-box", WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>
            {product.name}
          </h3>

          {/* Descripción corta — BODY, claramente legible */}
          {product.description && (
            <p style={{
              margin: "0.1rem 0 0",
              color: BODY, fontSize: "0.78rem", lineHeight: 1.5,
              display: "-webkit-box", WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical", overflow: "hidden",
              flex: 1,
            }}>
              {product.description}
            </p>
          )}

          {/* Footer de card: precio + duración */}
          <div style={{
            display: "flex", alignItems: "center",
            justifyContent: "space-between",
            marginTop: "0.85rem",
            paddingTop: "0.75rem",
            borderTop: "1px solid #1A1F35",
          }}>
            {price ? (
              <div>
                <span style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  color: NEON, fontWeight: 800,
                  fontSize: "1.2rem",
                  fontVariantNumeric: "tabular-nums",
                }}>
                  ${Number(price.basePrice).toLocaleString("es-AR")}
                </span>
                <span style={{ color: MUTED, fontSize: "0.68rem", marginLeft: "0.3rem" }}>{price.currency}</span>
              </div>
            ) : <div />}
            {product.durationWeeks && (
              <span style={{ color: MUTED, fontSize: "0.73rem" }}>
                {product.durationWeeks} sem.
              </span>
            )}
          </div>
        </div>
      </article>
    </Link>
  );
}
