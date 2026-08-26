/**
 * Catálogo de productos — Fase 03.
 * Mobile-first: filtros como strip horizontal en mobile, sidebar en desktop.
 */
import { Suspense } from "react";
import Link from "next/link";
import { getPublishedProducts, getCategories, StoreProduct } from "@/lib/store-api";

const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";

interface SearchParams {
  categoria?: string;
  q?: string;
  page?: string;
}

export const revalidate = 60;

async function ProductGrid({ searchParams }: { searchParams: SearchParams }) {
  const page = Number(searchParams.page ?? 1);
  const data = await getPublishedProducts({
    categorySlug: searchParams.categoria,
    q: searchParams.q,
    page,
    pageSize: 24,
  }).catch(() => ({ products: [] as StoreProduct[], pagination: { total: 0, page: 1, pageSize: 24 } }));

  const products = data.products ?? (data as { data?: StoreProduct[] }).data ?? [];
  const pagination = (data as { pagination?: { total: number; page: number; pageSize: number } }).pagination;

  if (products.length === 0) {
    return (
      <div style={{ padding: "4rem 1rem", textAlign: "center", color: "#4A5070" }}>
        <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>🔍</div>
        <p style={{ fontSize: "1rem" }}>No encontramos productos con esos filtros.</p>
        <Link href="/tienda" style={{ color: NEON, marginTop: "0.75rem", display: "inline-block" }}>Limpiar filtros →</Link>
      </div>
    );
  }

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1.1rem" }}>
        {products.map(p => <StoreCard key={p.id} product={p} />)}
      </div>

      {pagination && pagination.total > pagination.pageSize && (
        <div style={{ marginTop: "2rem", display: "flex", justifyContent: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          {page > 1 && (
            <Link href={`/tienda?page=${page - 1}${searchParams.categoria ? `&categoria=${searchParams.categoria}` : ""}`}
              style={{ padding: "0.5rem 1rem", background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#A0AAC8", textDecoration: "none", fontSize: "0.85rem" }}>
              ← Anterior
            </Link>
          )}
          <span style={{ padding: "0.5rem 1rem", color: "#4A5070", fontSize: "0.85rem", alignSelf: "center" }}>
            {page} / {Math.ceil(pagination.total / pagination.pageSize)}
          </span>
          {page * pagination.pageSize < pagination.total && (
            <Link href={`/tienda?page=${page + 1}${searchParams.categoria ? `&categoria=${searchParams.categoria}` : ""}`}
              style={{ padding: "0.5rem 1rem", background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#A0AAC8", textDecoration: "none", fontSize: "0.85rem" }}>
              Siguiente →
            </Link>
          )}
        </div>
      )}
    </>
  );
}

function StoreCard({ product }: { product: StoreProduct }) {
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const levelColor = product.level === "principiante" ? NEON : product.level === "intermedio" ? CYAN : PINK;

  const emoji =
    product.category?.slug?.includes("glut") || product.category?.slug?.includes("pierna") ? "🍑" :
    product.category?.slug?.includes("yoga") || product.category?.slug?.includes("flex") ? "🧘" :
    product.category?.slug?.includes("nutri") || product.category?.slug?.includes("receta") ? "🥗" :
    product.category?.slug?.includes("abdomen") || product.category?.slug?.includes("core") ? "⚡" :
    product.category?.slug?.includes("postparto") ? "💪" :
    product.category?.slug?.includes("mindset") ? "🧠" :
    product.category?.slug?.includes("desafio") ? "🔥" :
    product.category?.slug?.includes("casa") ? "🏠" :
    product.category?.slug?.includes("vip") || product.category?.slug?.includes("bundle") ? "⭐" : "🏋️";

  return (
    <Link href={`/tienda/${product.slug}`} style={{ textDecoration: "none", display: "block" }}>
      <article style={{
        background: "#0D0F1A", borderRadius: 12, border: "1px solid #1A1F35",
        overflow: "hidden", height: "100%", display: "flex", flexDirection: "column",
        transition: "border-color 0.2s, transform 0.2s",
      }}
        className="store-card"
      >
        <div style={{ height: 140, background: `linear-gradient(135deg, #0A0C18 0%, ${NEON}09 100%)`, display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
          <span style={{ fontSize: "2.25rem" }}>{emoji}</span>
          {product.level && (
            <span style={{ position: "absolute", top: 8, right: 8, padding: "2px 7px", borderRadius: 4, fontSize: "0.68rem", fontWeight: 700, background: `${levelColor}22`, color: levelColor, border: `1px solid ${levelColor}44` }}>
              {product.level}
            </span>
          )}
          {product.productType === "BUNDLE" && (
            <span style={{ position: "absolute", top: 8, left: 8, padding: "2px 7px", borderRadius: 4, fontSize: "0.68rem", fontWeight: 700, background: `${PINK}22`, color: PINK, border: `1px solid ${PINK}44` }}>
              PACK
            </span>
          )}
        </div>

        <div style={{ padding: "0.85rem 0.95rem", flex: 1, display: "flex", flexDirection: "column" }}>
          {product.category && (
            <div style={{ fontSize: "0.68rem", color: CYAN, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.3rem" }}>
              {product.category.name}
            </div>
          )}
          <h3 style={{ color: "#E8EDFF", fontSize: "0.9rem", fontWeight: 600, margin: "0 0 auto", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {product.name}
          </h3>
          <div style={{ marginTop: "0.7rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            {price && (
              <div style={{ color: NEON, fontWeight: 700, fontSize: "1.05rem", fontVariantNumeric: "tabular-nums" }}>
                ${Number(price.basePrice).toLocaleString("es-AR")} <span style={{ fontSize: "0.68rem", color: "#4A5070", fontWeight: 400 }}>{price.currency}</span>
              </div>
            )}
            {product.durationWeeks && <span style={{ fontSize: "0.7rem", color: "#4A5070" }}>{product.durationWeeks} sem.</span>}
          </div>
        </div>
      </article>
    </Link>
  );
}

export default async function TiendaPage({ searchParams }: { searchParams: SearchParams }) {
  const catsData = await getCategories().catch(() => ({ categories: [] }));
  const categories = (
    (catsData as { categories?: { id: string; name: string; slug: string; _count?: { products: number } }[] }).categories ??
    (catsData as { data?: { id: string; name: string; slug: string }[] }).data ?? []
  );

  return (
    <>
      {/* Nav */}
      <nav style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "rgba(6,8,15,0.97)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid #1A1F35",
        padding: "0 1rem", height: 56,
        display: "flex", alignItems: "center", gap: "1rem",
      }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none", whiteSpace: "nowrap" }}>
          FITNESS OS
        </Link>
        <div style={{ flex: 1 }} />
        <span style={{ color: "#6B7494", fontSize: "0.82rem" }}>Tienda</span>
      </nav>

      {/* Mobile category strip */}
      <div className="mobile-cat-strip" style={{ borderBottom: "1px solid #1A1F35", overflowX: "auto", WebkitOverflowScrolling: "touch", scrollbarWidth: "none" }}>
        <div style={{ display: "flex", gap: "0.5rem", padding: "0.65rem 1rem", width: "max-content" }}>
          <Link href="/tienda" style={{ padding: "0.3rem 0.85rem", borderRadius: 20, textDecoration: "none", fontSize: "0.8rem", fontWeight: 600, whiteSpace: "nowrap", background: !searchParams.categoria ? `${NEON}18` : "transparent", color: !searchParams.categoria ? NEON : "#6B7494", border: `1px solid ${!searchParams.categoria ? `${NEON}44` : "#1A1F35"}` }}>
            Todos
          </Link>
          {categories.map((cat: { id: string; name: string; slug: string; _count?: { products: number } }) => (
            <Link key={cat.id} href={`/tienda?categoria=${cat.slug}`} style={{ padding: "0.3rem 0.85rem", borderRadius: 20, textDecoration: "none", fontSize: "0.8rem", fontWeight: 600, whiteSpace: "nowrap", background: searchParams.categoria === cat.slug ? `${NEON}18` : "transparent", color: searchParams.categoria === cat.slug ? NEON : "#6B7494", border: `1px solid ${searchParams.categoria === cat.slug ? `${NEON}44` : "#1A1F35"}` }}>
              {cat.name}
            </Link>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 1rem 3rem" }}>
        <div className="tienda-layout" style={{ display: "flex", gap: "2rem", alignItems: "flex-start" }}>

          {/* Sidebar — hidden on mobile, shown on desktop via CSS */}
          <aside className="tienda-sidebar" style={{ width: 210, flexShrink: 0, position: "sticky", top: 68 }}>
            <h3 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "0.85rem", fontWeight: 700, color: "#4A5070", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: "0.65rem", marginTop: 0 }}>
              Categorías
            </h3>
            <Link href="/tienda" style={{ display: "block", padding: "0.4rem 0.75rem", borderRadius: 6, textDecoration: "none", fontSize: "0.85rem", color: !searchParams.categoria ? NEON : "#6B7494", background: !searchParams.categoria ? `${NEON}12` : "transparent", marginBottom: "0.2rem" }}>
              Todos
            </Link>
            {categories.map((cat: { id: string; name: string; slug: string }) => (
              <Link key={cat.id} href={`/tienda?categoria=${cat.slug}`} style={{ display: "block", padding: "0.4rem 0.75rem", borderRadius: 6, textDecoration: "none", fontSize: "0.85rem", color: searchParams.categoria === cat.slug ? NEON : "#6B7494", background: searchParams.categoria === cat.slug ? `${NEON}12` : "transparent", marginBottom: "0.2rem" }}>
                {cat.name}
              </Link>
            ))}
          </aside>

          {/* Main content */}
          <main style={{ flex: 1, minWidth: 0 }}>
            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
              <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "clamp(1.5rem, 5vw, 2rem)", fontWeight: 800, color: "#E8EDFF", margin: 0, lineHeight: 1 }}>
                {searchParams.categoria ? (categories.find((c: { slug: string; name: string }) => c.slug === searchParams.categoria)?.name ?? "Categoría") : "Todos los programas"}
              </h1>
            </div>

            {/* Search */}
            <form method="GET" action="/tienda" style={{ marginBottom: "1.5rem", display: "flex", gap: "0.6rem" }}>
              <input
                name="q"
                defaultValue={searchParams.q ?? ""}
                placeholder="Buscar programas, guías…"
                style={{ flex: 1, background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#E8EDFF", padding: "0.6rem 0.9rem", fontSize: "0.9rem", outline: "none", minWidth: 0 }}
              />
              {searchParams.categoria && <input type="hidden" name="categoria" value={searchParams.categoria} />}
              <button type="submit" style={{ padding: "0.6rem 1.1rem", background: NEON, border: "none", borderRadius: 8, color: "#06080F", fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>
                Buscar
              </button>
            </form>

            <Suspense fallback={<div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando productos…</div>}>
              <ProductGrid searchParams={searchParams} />
            </Suspense>
          </main>
        </div>
      </div>

      <style>{`
        /* Mobile: hide sidebar, show category strip */
        .mobile-cat-strip { display: block; }
        .tienda-sidebar { display: none !important; }

        /* Desktop: show sidebar, hide strip */
        @media (min-width: 768px) {
          .mobile-cat-strip { display: none; }
          .tienda-sidebar { display: block !important; }
        }

        /* Card hover */
        .store-card:hover {
          border-color: ${NEON}55 !important;
          transform: translateY(-2px);
        }

        /* Hide scrollbar in category strip */
        .mobile-cat-strip::-webkit-scrollbar { display: none; }
      `}</style>
    </>
  );
}
