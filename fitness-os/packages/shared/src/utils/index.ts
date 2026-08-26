// ── Utilidades compartidas ───────────────────────────────────────

/**
 * Genera un idempotency key para entregas.
 * El mismo orderId + productId nunca produce dos entregas.
 */
export function deliveryIdempotencyKey(orderId: string, productId: string): string {
  return `delivery:${orderId}:${productId}`;
}

/**
 * Genera slug URL-safe desde un string.
 */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

/**
 * Formatea precio en ARS con símbolo.
 */
export function formatPrice(amount: number, currency = "ARS"): string {
  const symbols: Record<string, string> = {
    ARS: "$",
    UYU: "$U",
    USD: "US$",
    EUR: "€",
    MXN: "$",
    CLP: "$",
    COP: "$",
    PEN: "S/",
  };
  const symbol = symbols[currency] ?? "$";
  return `${symbol} ${amount.toLocaleString("es-AR")}`;
}

/**
 * Valida que un tenantId esté presente — helper de seguridad.
 */
export function assertTenantId(tenantId: string | undefined): asserts tenantId is string {
  if (!tenantId) {
    throw new Error("tenantId is required — tenant context not set");
  }
}

/**
 * Sleep utility para retries.
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Paginación segura: clamp de page y pageSize.
 */
export function safePagination(
  page: number | undefined,
  pageSize: number | undefined,
  maxPageSize = 100
): { skip: number; take: number; page: number; pageSize: number } {
  const p = Math.max(1, page ?? 1);
  const ps = Math.min(Math.max(1, pageSize ?? 20), maxPageSize);
  return { skip: (p - 1) * ps, take: ps, page: p, pageSize: ps };
}
