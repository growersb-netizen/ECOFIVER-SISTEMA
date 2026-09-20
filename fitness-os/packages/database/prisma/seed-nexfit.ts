/**
 * seed-nexfit.ts — Inyecta ProductPrice (canal WEB, moneda ARS) para los 205 productos.
 * Ejecutar: pnpm --filter @fitness-os/database run seed:nexfit
 *
 * Soluciona el error 422 en checkout por falta de precios activos.
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

// SKU → precio base en ARS (fuente: catalog-seed.ts)
const PRICES: Record<string, number> = {
  // Guías de Entrenamiento
  "GT-001": 4900, "GT-002": 7900, "GT-003": 6900, "GT-004": 3900, "GT-005": 5900,
  "GT-006": 4500, "GT-007": 3500, "GT-008": 4900, "GT-009": 3900, "GT-010": 5500,
  "GT-011": 6500, "GT-012": 3200, "GT-013": 3500, "GT-014": 5900, "GT-015": 2900,
  "GT-016": 6500, "GT-017": 5500, "GT-018": 2900, "GT-019": 7500, "GT-020": 2500,
  // Glúteos y Piernas
  "GP-001": 8900, "GP-002": 7500, "GP-003": 4500, "GP-004": 3500, "GP-005": 4900,
  "GP-006": 5500, "GP-007": 4900, "GP-008": 5900, "GP-009": 4500, "GP-010": 3900,
  "GP-011": 7900, "GP-012": 3200, "GP-013": 3900, "GP-014": 4200, "GP-015": 4200,
  "GP-016": 3200, "GP-017": 12900, "GP-018": 4500, "GP-019": 2900, "GP-020": 9900,
  // Abdomen y Core
  "AC-001": 4500, "AC-002": 5900, "AC-003": 6900, "AC-004": 5900, "AC-005": 3900,
  "AC-006": 5500, "AC-007": 6500, "AC-008": 5500, "AC-009": 4900, "AC-010": 6500,
  "AC-011": 3200, "AC-012": 3900, "AC-013": 4500, "AC-014": 6900, "AC-015": 5500,
  // Planes de Nutrición
  "PN-001": 7900, "PN-002": 7900, "PN-003": 6900, "PN-004": 5900, "PN-005": 8900,
  "PN-006": 3500, "PN-007": 5500, "PN-008": 5900, "PN-009": 6900, "PN-010": 4500,
  "PN-011": 4900, "PN-012": 6500, "PN-013": 4500, "PN-014": 4900, "PN-015": 4500,
  "PN-016": 3900, "PN-017": 8900, "PN-018": 5900, "PN-019": 7900, "PN-020": 5500,
  // Ejercicios en Casa
  "EC-001": 6900, "EC-002": 5900, "EC-003": 3500, "EC-004": 6500, "EC-005": 5500,
  "EC-006": 4500, "EC-007": 3500, "EC-008": 4500, "EC-009": 3900, "EC-010": 3200,
  "EC-011": 4900, "EC-012": 4500, "EC-013": 3500, "EC-014": 3900, "EC-015": 5500,
  // Yoga y Flexibilidad
  "YF-001": 5500, "YF-002": 6500, "YF-003": 5900, "YF-004": 4900, "YF-005": 6900,
  "YF-006": 5500, "YF-007": 4500, "YF-008": 5500, "YF-009": 4200, "YF-010": 4900,
  // Programas de Transformación
  "PT-001": 14900, "PT-002": 8900, "PT-003": 9900, "PT-004": 12900, "PT-005": 11900,
  "PT-006": 12900, "PT-007": 14900, "PT-008": 13900, "PT-009": 7900, "PT-010": 5900,
  "PT-011": 14900, "PT-012": 7900, "PT-013": 11900, "PT-014": 8900, "PT-015": 9900,
  // Postparto y Recuperación
  "PR-001": 6900, "PR-002": 7900, "PR-003": 5500, "PR-004": 6500, "PR-005": 5900,
  "PR-006": 5500, "PR-007": 4500, "PR-008": 8900, "PR-009": 5900, "PR-010": 6500,
  // Mindset y Hábitos
  "MH-001": 4900, "MH-002": 5500, "MH-003": 3900, "MH-004": 3500, "MH-005": 5900,
  "MH-006": 4900, "MH-007": 3900, "MH-008": 4500, "MH-009": 4500, "MH-010": 3500,
  // Recetas Fit
  "RF-001": 5900, "RF-002": 4500, "RF-003": 3900, "RF-004": 4900, "RF-005": 3500,
  "RF-006": 3200, "RF-007": 3900, "RF-008": 3900, "RF-009": 4500, "RF-010": 4500,
  // Desafíos 30 Días
  "D30-001": 2900, "D30-002": 2900, "D30-003": 3500, "D30-004": 2500, "D30-005": 3500,
  "D30-006": 3200, "D30-007": 2900, "D30-008": 3200, "D30-009": 3500, "D30-010": 4500,
  // Programas VIP
  "VIP-001": 24900, "VIP-002": 19900, "VIP-003": 34900, "VIP-004": 14900, "VIP-005": 16900,
  // Para Hombres
  "MASC-001": 9900, "MASC-002": 8900, "MASC-003": 6900, "MASC-004": 5900, "MASC-005": 5500,
  "MASC-006": 6900, "MASC-007": 5500, "MASC-008": 11900, "MASC-009": 7900, "MASC-010": 7900,
  "MASC-011": 9900, "MASC-012": 5900, "MASC-013": 5500, "MASC-014": 6500, "MASC-015": 7500,
  "MASC-016": 6500, "MASC-017": 10900, "MASC-018": 5500, "MASC-019": 19900, "MASC-020": 7500,
  // Fuerza y Musculación
  "FM-001": 5900, "FM-002": 6900, "FM-003": 7900, "FM-004": 5500, "FM-005": 7900,
  "FM-006": 6500, "FM-007": 6900, "FM-008": 5900, "FM-009": 8900, "FM-010": 5500,
  "FM-011": 4900, "FM-012": 8900, "FM-013": 4500, "FM-014": 7900, "FM-015": 6900,
  // Rendimiento Deportivo
  "RD-001": 6900, "RD-002": 5900, "RD-003": 7900, "RD-004": 6900, "RD-005": 6500,
  "RD-006": 7500, "RD-007": 7500, "RD-008": 6500, "RD-009": 7900, "RD-010": 4500,
};

async function seedNexfit() {
  console.log("🚀 NexFit — inyectando precios WEB para los 205 productos...");

  const tenant = await prisma.tenant.findFirst({ where: { active: true } });
  if (!tenant) {
    console.error("❌ No hay tenant activo. Ejecutar seed principal primero.");
    process.exit(1);
  }
  console.log(`✓ Tenant: ${tenant.name} (${tenant.id})`);

  let upserted = 0;
  let notFound = 0;

  for (const [sku, price] of Object.entries(PRICES)) {
    const product = await prisma.product.findUnique({
      where: { tenantId_sku: { tenantId: tenant.id, sku } },
    });

    if (!product) {
      console.warn(`  ⚠️  Producto no encontrado: ${sku}`);
      notFound++;
      continue;
    }

    const existing = await prisma.productPrice.findFirst({
      where: { productId: product.id, channel: "WEB", currency: "ARS" },
    });

    if (existing) {
      await prisma.productPrice.update({
        where: { id: existing.id },
        data: { basePrice: price, active: true },
      });
    } else {
      await prisma.productPrice.create({
        data: {
          productId: product.id,
          basePrice: price,
          currency: "ARS",
          channel: "WEB",
          country: "AR",
          active: true,
        },
      });
    }

    upserted++;
    if (upserted % 50 === 0) console.log(`   ${upserted} precios procesados...`);
  }

  console.log(`\n✅ ${upserted} precios WEB/ARS activos`);
  if (notFound > 0) console.warn(`⚠️  ${notFound} SKUs no encontrados (ejecutar catalog:seed primero)`);
  console.log("🎉 Checkout desbloqueado — el error 422 está resuelto.");
}

seedNexfit()
  .catch(e => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
