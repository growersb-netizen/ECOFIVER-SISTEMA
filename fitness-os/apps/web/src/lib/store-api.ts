/**
 * Cliente API para la tienda pública.
 * Solo operaciones de lectura + checkout.
 * NO requiere token de admin.
 */

const API_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
const TENANT_SLUG = process.env["NEXT_PUBLIC_TENANT_SLUG"] ?? "";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(TENANT_SLUG ? { "X-Tenant-Slug": TENANT_SLUG } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { error?: string };
    throw new Error(err.error ?? `API Error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface StoreProduct {
  id: string;
  name: string;
  slug: string;
  description?: string;
  objective?: string;
  level?: string;
  durationWeeks?: number;
  productType: string;
  prices: Array<{ basePrice: string; currency: string; channel?: string }>;
  files?: Array<{ fileType: string; isPrimary: boolean; isCover: boolean }>;
  category?: { name: string; slug: string };
  coverImageUrl?: string;
}

export interface StoreCategory {
  id: string;
  name: string;
  slug: string;
  description?: string;
  _count?: { products: number };
}

// ── Catalog ────────────────────────────────────────────────────────

export async function getPublishedProducts(params?: {
  categorySlug?: string;
  q?: string;
  page?: number;
  pageSize?: number;
}) {
  const qs = new URLSearchParams(
    Object.entries({ status: "PUBLISHED", ...params }).reduce((acc, [k, v]) => {
      if (v !== undefined && v !== "") acc[k] = String(v);
      return acc;
    }, {} as Record<string, string>)
  ).toString();
  return apiFetch<{ products?: StoreProduct[]; data?: StoreProduct[]; pagination?: { total: number; page: number; pageSize: number } }>(`/api/v1/products?${qs}`);
}

export async function getProductBySlug(slug: string) {
  return apiFetch<{ data?: StoreProduct; product?: StoreProduct } | StoreProduct>(`/api/v1/products/by-slug/${slug}`);
}

export async function getCategories() {
  return apiFetch<{ categories?: StoreCategory[]; data?: StoreCategory[] }>("/api/v1/categories");
}

// ── Checkout ───────────────────────────────────────────────────────

export async function initCheckout(payload: {
  items: Array<{ productId: string; quantity: number }>;
  couponCode?: string;
  affiliateSlug?: string;
  channel?: string;
}) {
  return apiFetch<{ orderId: string; checkoutUrl: string; total: number; currency: string }>(
    "/api/v1/checkout/init",
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export async function validateCoupon(code: string, productIds: string[]) {
  return apiFetch<{ valid: boolean; discountPct?: number; discountAmt?: number; message?: string }>(
    "/api/v1/checkout/coupon",
    { method: "POST", body: JSON.stringify({ code, productIds }) }
  );
}
