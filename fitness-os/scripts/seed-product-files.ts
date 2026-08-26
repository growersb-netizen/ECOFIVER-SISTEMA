/**
 * scripts/seed-product-files.ts
 *
 * Crea registros ProductFile para todos los productos usando las rutas
 * de R2 esperadas (products/{productId}/{sku}.zip).
 *
 * Usar cuando:
 * - Ya subiste los ZIPs a R2 con upload-to-r2.ts
 * - O querés pre-crear los registros para que la descarga funcione en cuanto subas
 *
 * Uso:
 *   FITNESS_ADMIN_TOKEN=xxx tsx scripts/seed-product-files.ts
 *
 * Opciones:
 *   DRY_RUN=true        — muestra qué haría sin crear nada
 *   SKIP_EXISTING=true  — omite productos que ya tienen ProductFile (default true)
 *   ONLY_SKU=GT-001     — solo procesa ese SKU
 */

const API_URL     = process.env["FITNESS_API_URL"] ?? "https://fitness-api-production-fff4.up.railway.app";
const TOKEN       = process.env["FITNESS_ADMIN_TOKEN"] ?? "";
const DRY_RUN     = process.env["DRY_RUN"] === "true";
const SKIP_EXISTING = process.env["SKIP_EXISTING"] !== "false"; // default true
const ONLY_SKU    = process.env["ONLY_SKU"];
const TENANT_SLUG = "fitness-business-os";

if (!TOKEN) { console.error("❌ FITNESS_ADMIN_TOKEN requerido"); process.exit(1); }

const headers = {
  "Content-Type": "application/json",
  "Authorization": `Bearer ${TOKEN}`,
  "X-Tenant-Slug": TENANT_SLUG,
};

interface ProductFromAPI {
  id: string;
  sku: string;
  name: string;
  status: string;
  files?: Array<{ id: string; storageKey: string; isPrimary: boolean }>;
}

async function fetchProducts(): Promise<ProductFromAPI[]> {
  let all: ProductFromAPI[] = [];
  let page = 1;
  while (true) {
    const res = await fetch(`${API_URL}/api/v1/products?pageSize=100&page=${page}`, { headers });
    const data = await res.json() as { data?: ProductFromAPI[]; products?: ProductFromAPI[]; pagination?: { total: number; pageSize: number } };
    const batch = data.data ?? data.products ?? [];
    all = all.concat(batch);
    const pg = data.pagination;
    if (!pg || all.length >= pg.total || batch.length === 0) break;
    page++;
  }
  return all;
}

async function createProductFile(productId: string, storageKey: string, sku: string): Promise<boolean> {
  const res = await fetch(`${API_URL}/api/v1/products/${productId}/files`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      storageKey,
      filename: `${sku}.zip`,
      mimeType: "application/zip",
      isPrimary: true,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { error?: string };
    console.error(`  ✕ Error creando file para ${sku}: ${JSON.stringify(err)}`);
    return false;
  }
  return true;
}

async function main() {
  console.log(`\n📦 Seed ProductFiles — ${DRY_RUN ? "DRY RUN" : "PRODUCCIÓN"}`);
  console.log(`   API: ${API_URL}`);
  if (ONLY_SKU) console.log(`   Filtrando solo: ${ONLY_SKU}`);
  console.log();

  const products = await fetchProducts();
  console.log(`✓ ${products.length} productos encontrados`);

  let filtered = products;
  if (ONLY_SKU) filtered = products.filter(p => p.sku === ONLY_SKU);

  const results = { created: 0, skipped: 0, failed: 0 };

  for (const product of filtered) {
    const hasFile = Array.isArray(product.files) && product.files.length > 0;
    const primaryFile = product.files?.find(f => f.isPrimary);

    if (hasFile && SKIP_EXISTING) {
      const key = primaryFile?.storageKey ?? "(desconocida)";
      console.log(`  ⏭ ${product.sku} — ya tiene file (${key})`);
      results.skipped++;
      continue;
    }

    // Ruta esperada en R2: products/{productId}/{sku}.zip
    const storageKey = `products/${product.id}/${product.sku}.zip`;

    if (DRY_RUN) {
      console.log(`  [dry] ${product.sku} → ${storageKey}`);
      results.created++;
      continue;
    }

    const ok = await createProductFile(product.id, storageKey, product.sku);
    if (ok) {
      console.log(`  ✓ ${product.sku} — ProductFile creado → ${storageKey}`);
      results.created++;
    } else {
      results.failed++;
    }
  }

  console.log(`\n─────────────────────────────────────`);
  console.log(`  ✓ Creados: ${results.created}`);
  console.log(`  ⏭ Omitidos: ${results.skipped}`);
  console.log(`  ✕ Errores: ${results.failed}`);
  console.log(`─────────────────────────────────────`);

  if (results.failed > 0) {
    console.error(`\n⚠ Completado con ${results.failed} error(es).`);
    process.exit(1);
  }
  console.log(`\n✅ Listo. Cuando subas los ZIPs a R2 en esas rutas, las descargas funcionarán.`);
}

main().catch(err => {
  console.error("Error fatal:", err);
  process.exit(1);
});
