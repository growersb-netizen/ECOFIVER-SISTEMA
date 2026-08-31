/**
 * seed-product-files.ts — Crea/actualiza registros ProductFile para todos los
 * productos PUBLISHED del tenant, apuntando a los ZIPs embebidos en la imagen Docker.
 *
 * Se ejecuta en el CMD del Dockerfile justo antes de iniciar el servidor.
 * También se puede ejecutar manualmente:
 *
 *   pnpm --filter @fitness-os/database seed:product-files
 *
 * Cuando se configure R2 y se suban los ZIPs, actualizar storageKey a:
 *   "products/{productId}/{sku}.zip"
 * y correr de nuevo con STORAGE_MODE=r2.
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

const TENANT_SLUG = "fitness-business-os";
const STORAGE_MODE = process.env["STORAGE_MODE"] ?? "local"; // "local" | "r2"

async function main() {
  console.log(`\n[seed-product-files] Modo: ${STORAGE_MODE}`);

  const tenant = await prisma.tenant.findUnique({
    where: { slug: TENANT_SLUG },
    select: { id: true },
  });

  if (!tenant) {
    console.error(`[seed-product-files] Tenant "${TENANT_SLUG}" no encontrado`);
    process.exit(1);
  }

  const products = await prisma.product.findMany({
    where: {
      tenantId: tenant.id,
      status: "PUBLISHED",
      NOT: { sku: null },
    },
    select: { id: true, sku: true, name: true },
    orderBy: { sku: "asc" },
  });

  console.log(`[seed-product-files] ${products.length} productos PUBLISHED encontrados`);

  let created = 0;
  let updated = 0;
  let skipped = 0;

  for (const product of products) {
    if (!product.sku) { skipped++; continue; }

    // storageKey: en modo local apunta a la ruta dentro del contenedor Docker;
    // en modo r2 apuntará al bucket.
    const storageKey = STORAGE_MODE === "r2"
      ? `products/${product.id}/${product.sku}.zip`
      : `local://zips/${product.sku}.zip`; // marcador semántico para modo local

    const existing = await prisma.productFile.findFirst({
      where: { productId: product.id, isPrimary: true },
      select: { id: true, storageKey: true },
    });

    if (existing) {
      if (existing.storageKey === storageKey) {
        skipped++;
        continue;
      }
      // Actualizar storageKey si cambió (ej: pasando de local → r2)
      await prisma.productFile.update({
        where: { id: existing.id },
        data: { storageKey },
      });
      updated++;
    } else {
      await prisma.productFile.create({
        data: {
          productId: product.id,
          name: `${product.sku}.zip`,
          fileType: "zip",
          storageKey,
          mimeType: "application/zip",
          isPrimary: true,
          sortOrder: 0,
        },
      });
      created++;
    }
  }

  console.log(
    `[seed-product-files] Listo — creados: ${created}, actualizados: ${updated}, sin cambios: ${skipped}`
  );
}

main()
  .catch((err) => {
    console.error("[seed-product-files] Error:", err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
