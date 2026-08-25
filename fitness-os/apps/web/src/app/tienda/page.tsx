/**
 * Catálogo de productos — Fase 03.
 * Filtros por categoría, búsqueda, ordenamiento.
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

export const revalidate = 60; // ISR cada 60 segundos

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
      <div style={{ padding: "4rem", textAlign: "center", color: "#4A5070" }}>
        <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>🔍</div>
        <p style={{ fontSize: "1rem" }}>No encontramos productos con esos filtros.</p>
        <Link href="/tienda" style={{ color: NEON, marginTop: "0.75rem", display: "inline-block" }}>Limpiar filtros →</Link>
      </div>
    );
  }

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: "1.25rem" }}>
        {products.map(p => <StoreCard key={p.id} product={p} />)}
      </div>

      {/* Pagination */}
      {pagination && pagination.total > pagination.pageSize && (
        <div style={{ marginTop: "2rem", display: "flex", justifyContent: "center", gap: "0.5rem" }}>
          {page > 1 && <Link href={`/tienda?page=${page - 1}${searchParams.categoria ? `&categoria=${searchParams.categoria}` : ""}`} style={{ padding: "0.5rem 1rem", background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#A0AAC8", textDecoration: "none" }}>← Anterior</Link>}
          <span style={{ padding: "0.5rem 1rem", color: "#4A5070", fontSize: "0.85rem" }}>
            Página {page} de {Math.ceil(pagination.total / pagination.pageSize)}
          </span>
          {page * pagination.pageSize < pagination.total && <Link href={`/tienda?page=${page + 1}${searchParams.categoria ? `&categoria=${searchParams.categoria}` : ""}`} style={{ padding: "0.5rem 1rem", background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#A0AAC8", textDecoration: "none" }}>Siguiente →</Link>}
        </div>
      )}
    </>
  );
}

function StoreCard({ product }: { product: StoreProduct }) {
  const price = product.prices?.find(p => p.channel === "WEB" || !p.channel) ?? product.prices?.[0];
  const levelColor = product.level === "principiante" ? NEON : product.level === "intermedio" ? CYAN : PINK;

  return (
    <Link href={`/tienda/${product.slug}`} style={{ textDecoration: "none", display: "block" }}>
      <article style={{
        background: "#0D0F1A", borderRadius: 14, border: "1px solid #1A1F35",
        overflow: "hidden", height: "100%", display: "flex", flexDirection: "column",
      }}>
        {/* Image/placeholder */}
        <div style={{ height: 148, background: `linear-gradient(135deg, #0A0C18 0%, ${NEON}09 100%)`, display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
          <span style={{ fontSize: "2.25rem" }}>
            {product.category?.slug?.includes("glut") ? "🍑" : product.category?.slug?.includes("yoga") ? "🧘" : product.category?.slug?.includes("nutri") ? "🥗" : "🏋️"}
          </span>
          {product.level && (
            <span style={{ position: "absolute", top: 8, right: 8, padding: "2px 7px", borderRadius: 4, fontSize: "0.68rem", fontWeight: 700, background: `${levelColor}22`, color: levelColor, border: `1px solid ${levelColor}44` }}>
              {product.level}
            </span>
          )}
          {product.productType === "BUNDLE" && (
            <span style={{ position: "absolute", top: 8, left: 8, padding: "2px 7px", borderRadius: 4, fontSize: "0.68rem", fontWeight: 700, background: `${PINK}22`, color: PINK, border: `1px solid ${PINK}44` }}>
              BUNDLE
            </span>
          )}
        </div>

        <div style={{ padding: "0.9rem 1rem", flex: 1, display: "flex", flexDirection: "column" }}>
          {product.category && <div style={{ fontSize: "0.68rem", color: CYAN, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.3rem" }}>{product.category.name}</div>}
          <h3 style={{ color: "#E8EDFF", fontSize: "0.9rem", fontWeight: 600, margin: "0 0 auto", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {product.name}
          </h3>
          <div style={{ marginTop: "0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            {price && (
              <div style={{ color: NEON, fontWeight: 700, fontSize: "1.1rem", fontVariantNumeric: "tabular-nums" }}>
                ${Number(price.basePrice).toLocaleString("es-AR")} <span style={{ fontSize: "0.7rem", color: "#4A5070", fontWeight: 400 }}>{price.currency}</span>
              </div>
            )}
            {product.durationWeeks && <span style={{ fontSize: "0.72rem", color: "#4A5070" }}>{product.durationWeeks} sem.</span>}
          </div>
        </div>
      </article>
    </Link>
  );
}

export default async function TiendaPage({ searchParams }: { searchParams: SearchParams }) {
  const catsData = await getCategories().catch(() => ({ categories: [] }));
  const categories = (catsData as { categories?: { id: string; name: string; slug: string; _count?: { products: number } }[]; data?: { id: string; name: string; slug: string }[] }).categories ??
    (catsData as { data?: { id: string; name: string; slug: string }[] }).data ?? [];

  return (
    <>
      {/* Nav */}
      <nav style={{ position: "sticky", top: 0, zIndex: 100, background: "rgba(6,8,15,0.95)", backdropFilter: "blur(12px)", borderBottom: "1px solid #1A1F35", padding: "0 1.5rem", height: 60, display: "flex", alignItems: "center", gap: "1.5rem" }}>
        <Link href="/" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, fontSize: "1.1rem", letterSpacing: "0.08em", color: NEON, textDecoration: "none" }}>
          FITNESS BUSINESS OS
        </Link>
        <div style={{ flex: 1 }} />
        <Link href="/tienda" style={{ color: "#A0AAC8", textDecoration: "none", fontSize: "0.85rem" }}>Tienda</Link>
      </nav>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "2rem 1.5rem" }}>
        <div style={{ display: "flex", gap: "2rem", alignItems: "flex-start" }}>
          {/* Sidebar */}
          <aside style={{ width: 220, flexShrink: 0, position: "sticky", top: 80 }}>
            <h3 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1rem", fontWeight: 700, color: "#6B7494", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: "0.75rem" }}>Categorías</h3>
            <Link href="/tienda" style={{ display: "block", padding: "0.4rem 0.75rem", borderRadius: 6, textDecoration: "none", fontSize: "0.85rem", color: !searchParams.categoria ? NEON : "#6B7494", background: !searchParams.categoria ? `${NEON}12` : "transparent", marginBottom: "0.25rem" }}>
              Todos
            </Link>
            {categories.map((cat: { id: string; name: string; slug: string; _count?: { products: number } }) => (
              <Link key={cat.id} href={`/tienda?categoria=${cat.slug}`} style={{ display: "block", padding: "0.4rem 0.75rem", borderRadius: 6, textDecoration: "none", fontSize: "0.85rem", color: searchParams.categoria === cat.slug ? NEON : "#6B7494", background: searchParams.categoria === cat.slug ? `${NEON}12` : "transparent", marginBottom: "0.25rem" }}>
                {cat.name}
              </Link>
            ))}
          </aside>

          {/* Main */}
          <main style={{ flex: 1, minWidth: 0 }}>
            {/* Search */}
            <form method="GET" action="/tienda" style={{ marginBottom: "1.5rem", display: "flex", gap: "0.75rem" }}>
              <input
                name="q"
                defaultValue={searchParams.q ?? ""}
                placeholder="Buscar programas, guías…"
                style={{ flex: 1, background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 8, color: "#E8EDFF", padding: "0.6rem 0.9rem", fontSize: "0.9rem", outline: "none" }}
              />
              {searchParams.categoria && <input type="hidden" name="categoria" value={searchParams.categoria} />}
              <button type="submit" style={{ padding: "0.6rem 1.25rem", background: NEON, border: "none", borderRadius: 8, color: "#06080F", fontWeight: 700, cursor: "pointer" }}>
                Buscar
              </button>
            </form>

            <Suspense fallback={<div style={{ padding: "3rem", textAlign: "center", color: "#4A5070" }}>Cargando productos…</div>}>
              <ProductGrid searchParams={searchParams} />
            </Suspense>
          </main>
        </div>
      </div>
    </>
  );
}
