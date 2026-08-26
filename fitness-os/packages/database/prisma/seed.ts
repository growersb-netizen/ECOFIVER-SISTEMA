/**
 * Seed de desarrollo — Fase 00.
 * Crea el tenant inicial y el usuario admin.
 *
 * Ejecutar: pnpm --filter @fitness-os/database run seed
 */

import { PrismaClient } from "@prisma/client";
import { hash } from "argon2";

const prisma = new PrismaClient();

async function main() {
  console.log("🌱 Iniciando seed...");

  // ── Tenant principal ─────────────────────────────────────────────
  const tenantSlug = process.env["SEED_TENANT_SLUG"] ?? "fitness-os";
  const tenantName = process.env["SEED_TENANT_NAME"] ?? "Fitness Business OS";

  const tenant = await prisma.tenant.upsert({
    where: { slug: tenantSlug },
    update: { name: tenantName },
    create: {
      slug: tenantSlug,
      name: tenantName,
      active: true,
    },
  });

  console.log(`✅ Tenant: ${tenant.name} (${tenant.slug})`);

  // ── Brand por defecto ────────────────────────────────────────────
  await prisma.brand.upsert({
    where: { tenantId: tenant.id },
    update: {},
    create: {
      tenantId: tenant.id,
      name: tenantName,
      primaryColor: "#00FF87",
      secondaryColor: "#00F5FF",
      accentColor: "#FF2D9C",
      welcomeMessage:
        "¡Bienvenida! Gracias por tu compra. Encontrarás todo lo que necesitás en tu biblioteca.",
      thankYouMessage: "Gracias por confiar en nosotras.",
      postSaleMessage:
        "¿Tenés alguna duda? Contactanos por WhatsApp o Instagram, estamos para ayudarte.",
    },
  });

  console.log("✅ Brand configurada");

  // ── Admin user ───────────────────────────────────────────────────
  const adminEmail =
    process.env["SEED_ADMIN_EMAIL"] ?? "admin@fitness-os.local";
  const adminPassword =
    process.env["SEED_ADMIN_PASSWORD"] ?? "cambiar-en-produccion-12345!";

  // Hash argon2 — mismo algoritmo que usa la ruta /auth/login
  const passwordHash = await hash(adminPassword);

  const adminUser = await prisma.user.upsert({
    where: { tenantId_email: { tenantId: tenant.id, email: adminEmail } },
    update: {},
    create: {
      tenantId: tenant.id,
      email: adminEmail,
      name: "Admin",
      passwordHash,
      role: "TENANT_ADMIN",
      active: true,
      emailVerified: new Date(),
    },
  });

  console.log(`✅ Admin user: ${adminUser.email} (role: ${adminUser.role})`);

  // ── Knowledge Base vacía ─────────────────────────────────────────
  const kb = await prisma.knowledgeBase.upsert({
    where: {
      id:
        (
          await prisma.knowledgeBase.findFirst({
            where: { tenantId: tenant.id },
          })
        )?.id ?? "new",
    },
    update: {},
    create: {
      tenantId: tenant.id,
      name: "Base de conocimiento principal",
      active: true,
    },
  });

  console.log(`✅ Knowledge Base: ${kb.name}`);

  // ── Autopilot configs por canal — todos MANUAL por defecto ───────
  const channels = [
    "WHATSAPP",
    "INSTAGRAM",
    "FACEBOOK",
    "TIKTOK",
    "YOUTUBE",
    "EMAIL",
    "WEB",
    "MERCADOLIBRE",
  ] as const;

  for (const channel of channels) {
    await prisma.autopilotConfig.upsert({
      where: { tenantId_channel: { tenantId: tenant.id, channel } },
      update: {},
      create: {
        tenantId: tenant.id,
        channel,
        mode: "MANUAL",
        enabled: false,
        kbId: kb.id,
      },
    });
  }

  console.log("✅ Autopilot configs (todos MANUAL por defecto)");

  // ── AI Model configs por defecto ─────────────────────────────────
  const aiFunctions = [
    { function: "GENERATION" as const, model: "openai/gpt-4o-mini" },
    { function: "ATTENTION" as const, model: "openai/gpt-4o-mini" },
    { function: "REASONING" as const, model: "openai/o3-mini" },
    { function: "ECONOMIC" as const, model: "openai/gpt-4o-mini" },
  ];

  for (const config of aiFunctions) {
    await prisma.aIModelConfig.upsert({
      where: {
        tenantId_function: { tenantId: tenant.id, function: config.function },
      },
      update: {},
      create: {
        tenantId: tenant.id,
        function: config.function,
        model: config.model,
        active: true,
      },
    });
  }

  console.log("✅ AI Model configs (OpenRouter)");

  console.log("");
  console.log("🚀 Seed completado exitosamente");
  console.log(`   Tenant ID: ${tenant.id}`);
  console.log(`   Admin: ${adminUser.email}`);
}

main()
  .catch((e) => {
    console.error("❌ Error en seed:", e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
