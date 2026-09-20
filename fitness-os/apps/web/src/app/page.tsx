/**
 * Home — Tienda NexFit
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

const STORE_NAME = process.env["NEXT_PUBLIC_STORE_NAME"] ?? "NEXFIT";

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

        {/* Hero image panel */}
        <div style={{
          borderRadius: 16,
          overflow: "hidden",
          position: "relative",
          minHeight: 420,
          background: "#0D0F1A",
          border: "1px solid #1A1F35",
        }}>
          <img
            src="/images/hero-1.webp"
            alt="Entrenamiento NexFit"
            style={{
              width: "100%", height: "100%",
              objectFit: "cover", objectPosition: "center",
              position: "absolute", inset: 0,
              display: "block",
            }}
          />
          {/* dark overlay so any overlay text is legible */}
          <div style={{
            position: "absolute", inset: 0,
            background: "linear-gradient(160deg, rgba(6,8,15,0.15) 0%, rgba(6,8,15,0.65) 100%)",
          }} />
          {/* floating category count badge */}
          <div style={{
            position: "absolute", bottom: "1.5rem", left: "1.5rem", right: "1.5rem",
            background: "rgba(6,8,15,0.82)", backdropFilter: "blur(12px)",
            border: "1px solid rgba(222,49,99,0.3)",
            borderRadius: 12, padding: "1rem 1.25rem",
          }}>
            <p style={{ color: CEREZA, fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", margin: "0 0 0.6rem" }}>
              Categorías disponibles
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
              {categories.slice(0, 6).map((cat) => (
                <Link key={cat.id} href={`/tienda?categoria=${cat.slug}`} style={{
                  padding: "0.22rem 0.7rem", borderRadius: 20,
                  background: "rgba(255,255,255,0.07)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  color: "#D0D8F0", fontSize: "0.75rem", fontWeight: 500,
                  textDecoration: "none", whiteSpace: "nowrap",
                }}>
                  {cat.name}
                </Link>
              ))}
              {categories.length > 6 && (
                <Link href="/tienda" style={{
                  padding: "0.22rem 0.7rem", borderRadius: 20,
                  background: `rgba(222,49,99,0.18)`,
                  border: `1px solid ${CEREZA}44`,
                  color: CEREZA, fontSize: "0.75rem", fontWeight: 700,
                  textDecoration: "none", whiteSpace: "nowrap",
                }}>
                  +{categories.length - 6} más →
                </Link>
              )}
            </div>
          </div>
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

// ── Category visual art — CSS-based branded thumbnails ──────────────
function categoryArt(slug: string): { bg: string; accent: string; label: string } {
  if (slug.includes("glut") || slug.includes("pierna"))  return { bg: "linear-gradient(135deg,#0A0418 0%,#2A0830 60%,#DE316322 100%)", accent: "#FF6B9D", label: "GLÚTEOS & PIERNAS" };
  if (slug.includes("yoga") || slug.includes("flex"))    return { bg: "linear-gradient(135deg,#040A14 0%,#071830 60%,#00F5FF18 100%)", accent: "#00F5FF", label: "YOGA & FLEX" };
  if (slug.includes("nutri") || slug.includes("receta")) return { bg: "linear-gradient(135deg,#030E06 0%,#062010 60%,#00FF8720 100%)", accent: "#00FF87", label: "NUTRICIÓN" };
  if (slug.includes("abdomen") || slug.includes("core")) return { bg: "linear-gradient(135deg,#0A0A04 0%,#1A1800 60%,#FFDD0020 100%)", accent: "#FFD700", label: "ABDOMEN & CORE" };
  if (slug.includes("postparto"))                        return { bg: "linear-gradient(135deg,#0A040E 0%,#1A0824 60%,#C97BFF22 100%)", accent: "#C97BFF", label: "POSTPARTO" };
  if (slug.includes("mindset") || slug.includes("habit")) return { bg: "linear-gradient(135deg,#04080E 0%,#081420 60%,#00BFFF20 100%)", accent: "#00BFFF", label: "MINDSET" };
  if (slug.includes("desafio"))                          return { bg: "linear-gradient(135deg,#0E0400 0%,#200800 60%,#FF450020 100%)", accent: "#FF4500", label: "DESAFÍOS" };
  if (slug.includes("hombre"))                           return { bg: "linear-gradient(135deg,#040A0E 0%,#081420 60%,#00C8FF22 100%)", accent: "#00C8FF", label: "PARA HOMBRES" };
  if (slug.includes("vip") || slug.includes("bundle") || slug.includes("pack")) return { bg: "linear-gradient(135deg,#0A0800 0%,#1A1200 60%,#FFD70025 100%)", accent: "#FFD700", label: "VIP / PACK" };
  if (slug.includes("transformacion"))                   return { bg: "linear-gradient(135deg,#06000E 0%,#100018 60%,#DE316328 100%)", accent: "#DE3163", label: "TRANSFORMACIÓN" };
  if (slug.includes("fuerza") || slug.includes("musc"))  return { bg: "linear-gradient(135deg,#060008 0%,#120020 60%,#AA00FF22 100%)", accent: "#AA00FF", label: "FUERZA" };
  if (slug.includes("rendimiento") || slug.includes("deport")) return { bg: "linear-gradient(135deg,#000A08 0%,#001A12 60%,#00FF8728 100%)", accent: "#00FF87", label: "RENDIMIENTO" };
  if (slug.includes("casa"))                             return { bg: "linear-gradient(135deg,#08080A 0%,#101018 60%,#8888FF22 100%)", accent: "#8888FF", label: "EN CASA" };
  return { bg: "linear-gradient(135deg,#06080F 0%,#0D1020 60%,#DE316318 100%)", accent: "#DE3163", label: "FITNESS" };
}

// ── ProductCard — diseño de e-commerce real ─────────────────────────
function ProductCard({ product }: { product: StoreProduct }) {
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const levelColors: Record<string, string> = { principiante: NEON, intermedio: CYAN, avanzado: CEREZA };
  const levelColor = product.level ? (levelColors[product.level] ?? CYAN) : CYAN;
  const isBundle = product.productType === "BUNDLE";
  const art = categoryArt(product.category?.slug ?? "");

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
        {/* Cover — CSS art branded per category */}
        <div style={{
          height: 160,
          background: art.bg,
          display: "flex", alignItems: "center", justifyContent: "center",
          position: "relative",
          borderBottom: `1px solid ${art.accent}22`,
          overflow: "hidden",
        }}>
          {/* Geometric accent circle */}
          <div style={{
            position: "absolute", bottom: -24, right: -24,
            width: 120, height: 120, borderRadius: "50%",
            border: `2px solid ${art.accent}30`,
            pointerEvents: "none",
          }} />
          <div style={{
            position: "absolute", top: -16, left: -16,
            width: 80, height: 80, borderRadius: "50%",
            border: `1px solid ${art.accent}20`,
            pointerEvents: "none",
          }} />
          {/* Category label */}
          <span style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontSize: "0.68rem", fontWeight: 800,
            letterSpacing: "0.18em", textTransform: "uppercase",
            color: art.accent, opacity: 0.85,
            position: "absolute", bottom: 10, left: 12,
          }}>
            {art.label}
          </span>
          {/* Accent line */}
          <div style={{
            position: "absolute", bottom: 0, left: 0, right: 0,
            height: 2, background: `linear-gradient(90deg, ${art.accent}88 0%, transparent 100%)`,
          }} />

          {/* Badges */}
          <div style={{ position: "absolute", top: 10, left: 10, display: "flex", gap: "0.4rem" }}>
            {isBundle && (
              <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: "0.65rem", fontWeight: 700, background: `${CEREZA}20`, color: CEREZA, border: `1px solid ${CEREZA}44`, letterSpacing: "0.06em" }}>
                PACK
              </span>
            )}
          </div>
          {product.level && (
            <span style={{ position: "absolute", top: 10, right: 10, padding: "2px 7px", borderRadius: 4, fontSize: "0.65rem", fontWeight: 700, background: `${levelColor}18`, color: levelColor, border: `1px solid ${levelColor}35` }}>
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
