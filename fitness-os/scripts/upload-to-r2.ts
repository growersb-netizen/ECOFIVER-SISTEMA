/**
 * scripts/upload-to-r2.ts
 *
 * Sube todos los ZIPs de generated/zips/ a Cloudflare R2 y crea
 * los registros ProductFile en la base de datos via la API.
 *
 * Uso:
 *   FITNESS_ADMIN_TOKEN=xxx \
 *   CLOUDFLARE_ACCOUNT_ID=xxx \
 *   R2_ACCESS_KEY_ID=xxx \
 *   R2_SECRET_ACCESS_KEY=xxx \
 *   R2_BUCKET_NAME=fitness-os \
 *   tsx scripts/upload-to-r2.ts
 *
 * Variables opcionales:
 *   FITNESS_API_URL  — default: https://fitness-api-production-fff4.up.railway.app
 *   DRY_RUN=true     — muestra qué haría sin subir ni crear nada
 */

import { readdir, readFile } from "fs/promises";
import { join, basename } from "path";
import { S3Client, PutObjectCommand, HeadObjectCommand } from "@aws-sdk/client-s3";

// ── Config ──────────────────────────────────────────────────────────
const API_URL   = process.env["FITNESS_API_URL"] ?? "https://fitness-api-production-fff4.up.railway.app";
const TOKEN     = process.env["FITNESS_ADMIN_TOKEN"] ?? "";
const DRY_RUN   = process.env["DRY_RUN"] === "true";
const TENANT_SLUG = "fitness-business-os";

const ACCOUNT_ID = process.env["CLOUDFLARE_ACCOUNT_ID"] ?? "";
const ACCESS_KEY = process.env["R2_ACCESS_KEY_ID"] ?? "";
const SECRET_KEY = process.env["R2_SECRET_ACCESS_KEY"] ?? "";
const BUCKET     = process.env["R2_BUCKET_NAME"] ?? "fitness-os";

if (!TOKEN) { console.error("❌ FITNESS_ADMIN_TOKEN requerido"); process.exit(1); }
if (!ACCOUNT_ID || !ACCESS_KEY || !SECRET_KEY) {
  console.error("❌ CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY requeridos");
  process.exit(1);
}

const ZIPS_DIR = join(new URL("../generated/zips", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));

// ── R2 client ───────────────────────────────────────────────────────
const r2 = new S3Client({
  region: "auto",
  endpoint: `https://${ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: { accessKeyId: ACCESS_KEY, secretAccessKey: SECRET_KEY },
});

// ── API helpers ─────────────────────────────────────────────────────
const headers = {
  "Content-Type": "application/json",
  "Authorization": `Bearer ${TOKEN}`,
  "X-Tenant-Slug": TENANT_SLUG,
};

async function apiGet(path: string) {
  const res = await fetch(`${API_URL}${path}`, { headers });
  return res.json() as Promise<Record<string, unknown>>;
}

async function apiPost(path: string, body: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST", headers, body: JSON.stringify(body),
  });
  return res.json() as Promise<Record<string, unknown>>;
}

// ── Key builder — igual que R2StorageAdapter pero aquí ──────────────
function buildKey(productId: string, sku: string): string {
  return `products/${productId}/${sku}.zip`;
}

// ── Verificar si ya existe en R2 ───────────────────────────────────
async function r2Exists(key: string): Promise<boolean> {
  try {
    await r2.send(new HeadObjectCommand({ Bucket: BUCKET, Key: key }));
    return true;
  } catch {
    return false;
  }
}

// ── Subir a R2 ─────────────────────────────────────────────────────
async function uploadZip(key: string, data: Buffer, sku: string): Promise<void> {
  await r2.send(new PutObjectCommand({
    Bucket: BUCKET,
    Key: key,
    Body: data,
    ContentType: "application/zip",
    ContentDisposition: `attachment; filename="${sku}.zip"`,
    Metadata: { sku, uploadedAt: new Date().toISOString() },
  }));
}

// ── Main ─────────────────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Upload script — ${DRY_RUN ? "DRY RUN" : "PRODUCCIÓN"}`);
  console.log(`   API: ${API_URL}`);
  console.log(`   R2:  ${BUCKET} (${ACCOUNT_ID.slice(0, 8)}...)`);
  console.log(`   ZIPs: ${ZIPS_DIR}\n`);

  // 1. Cargar todos los productos del tenant
  const data = await apiGet("/api/v1/products?pageSize=300&page=1");
  const products = ((data.data ?? data.products ?? []) as Array<{ id: string; sku: string; name: string; files?: unknown[] }>);
  console.log(`✓ Encontrados ${products.length} productos en la API`);

  // 2. Listar ZIPs disponibles
  const files = (await readdir(ZIPS_DIR)).filter(f => f.endsWith(".zip"));
  console.log(`✓ Encontrados ${files.length} ZIPs en ${ZIPS_DIR}\n`);

  const results = { uploaded: 0, skipped: 0, alreadyInR2: 0, failed: 0, noProduct: 0 };

  for (const filename of files.sort()) {
    const sku = basename(filename, ".zip");            // "GT-001"
    const product = products.find(p => p.sku === sku);

    if (!product) {
      console.warn(`  ⚠ Sin producto para SKU ${sku}`);
      results.noProduct++;
      continue;
    }

    const storageKey = buildKey(product.id, sku);
    const zipPath = join(ZIPS_DIR, filename);

    // Verificar si ya tiene ProductFile en la API
    const hasFile = Array.isArray(product.files) && product.files.length > 0;
    if (hasFile) {
      console.log(`  ⏭ ${sku} ya tiene ProductFile — omitido`);
      results.skipped++;
      continue;
    }

    if (DRY_RUN) {
      console.log(`  [dry] ${sku} → r2://${BUCKET}/${storageKey}`);
      results.uploaded++;
      continue;
    }

    try {
      // Verificar si ya está en R2
      const existsInR2 = await r2Exists(storageKey);
      if (!existsInR2) {
        const data = await readFile(zipPath);
        await uploadZip(storageKey, data, sku);
        console.log(`  ✓ Subido ${sku} (${(data.length / 1024).toFixed(0)} KB) → ${storageKey}`);
      } else {
        console.log(`  ✓ ${sku} ya existe en R2 — creando ProductFile`);
        results.alreadyInR2++;
      }

      // Crear ProductFile record
      await apiPost(`/api/v1/products/${product.id}/files`, {
        storageKey,
        filename: `${sku}.zip`,
        mimeType: "application/zip",
        isPrimary: true,
      });

      console.log(`    → ProductFile creado para ${product.name}`);
      results.uploaded++;
    } catch (err) {
      console.error(`  ✕ Error en ${sku}:`, err);
      results.failed++;
    }
  }

  console.log(`\n─────────────────────────────────────`);
  console.log(`Resultados:`);
  console.log(`  ✓ Subidos/procesados: ${results.uploaded}`);
  console.log(`  ⏭ Omitidos (ya tenían file): ${results.skipped}`);
  console.log(`  ☁ Ya en R2: ${results.alreadyInR2}`);
  console.log(`  ✕ Errores: ${results.failed}`);
  console.log(`  ⚠ Sin producto: ${results.noProduct}`);
  console.log(`─────────────────────────────────────\n`);

  if (results.failed > 0) process.exit(1);
}

main().catch(err => {
  console.error("Error fatal:", err);
  process.exit(1);
});
