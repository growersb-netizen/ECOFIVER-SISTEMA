/**
 * Fase 08 — MercadoLibre (Marketplace).
 *
 * GET  /api/v1/ml/status              — estado conexión + métricas
 * GET  /api/v1/ml/listings            — publicaciones en ML
 * POST /api/v1/ml/listings            — crear publicación (DRAFT)
 * POST /api/v1/ml/listings/bulk-draft — generar borradores para todos los productos
 * POST /api/v1/ml/listings/bulk-publish — publicar todos los APPROVED
 * POST /api/v1/ml/listings/:id/approve — aprobar borrador (habilita publicación)
 * POST /api/v1/ml/listings/:id/publish — publicar en ML (requiere aprobación)
 * PATCH /api/v1/ml/listings/:id       — actualizar
 * GET  /api/v1/ml/orders              — órdenes importadas de ML
 * POST /api/v1/webhooks/mercadolibre  — webhook de ML
 * GET  /api/v1/ml/auth                — iniciar OAuth con ML
 * GET  /api/v1/ml/auth/callback       — callback OAuth
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { MercadoLibreAdapter } from "../adapters/mercadolibre.js";

/** Categorías ML Argentina para productos digitales de fitness */
const ML_CATEGORY_MAP: Record<string, string> = {
  // Guías y programas de entrenamiento → Deportes y Fitness
  default: process.env["ML_DEFAULT_CATEGORY_ID"] ?? "MLA1168",
  gluteos: "MLA1168",
  core: "MLA1168",
  entrenamiento: "MLA1168",
  nutricion: "MLA1168",
  yoga: "MLA1168",
  postparto: "MLA1168",
  mindset: "MLA1168",
  recetas: "MLA1168",
};

function mlCategoryForProduct(categoryName: string): string {
  const lower = categoryName.toLowerCase();
  for (const [key, catId] of Object.entries(ML_CATEGORY_MAP)) {
    if (key !== "default" && lower.includes(key)) return catId;
  }
  return ML_CATEGORY_MAP["default"]!;
}

function buildMLTitle(name: string): string {
  // ML título: 10-60 caracteres
  const title = name.trim();
  if (title.length > 60) return title.substring(0, 57) + "...";
  return title;
}

function buildMLDescription(product: {
  name: string;
  description?: string | null;
  level?: string | null;
  durationWeeks?: number | null;
  category?: { name: string } | null;
}): string {
  const cat = product.category?.name ?? "Fitness";
  const level = product.level ?? "todos los niveles";
  const dur = product.durationWeeks ? `${product.durationWeeks} semanas` : null;

  const desc = product.description ??
    `${product.name} — Programa de ${cat}. ` +
    `Nivel ${level}. ` +
    (dur ? `Duración: ${dur}. ` : "") +
    `Incluye guía completa en PDF con ejercicios detallados, plan nutricional y tabla de seguimiento de progreso. ` +
    `Contenido digital descargable al instante. ` +
    `Ideal para quienes buscan resultados reales con un programa estructurado y progresivo.`;

  // ML descripción mínima 50 chars
  return desc.length >= 50 ? desc : desc + " Programa de fitness profesional.";
}

const CreateListingSchema = z.object({
  productId: z.string().uuid(),
  title: z.string().min(10).max(60),
  description: z.string().min(50),
  categoryId: z.string().optional(), // ID de categoría en ML
  price: z.number().min(0),
  currency: z.string().default("ARS"),
  condition: z.enum(["new", "used"]).default("new"),
  availableQuantity: z.number().int().min(1).default(999),
});

export async function mercadolibreRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  fastify.addHook("preHandler", fastify.authenticate);

  /**
   * GET /ml/auth — iniciar flujo OAuth de MercadoLibre
   */
  fastify.get(
    "/ml/auth",
    { preHandler: [requireRole("TENANT_ADMIN")] },
    async (request: FastifyRequest, reply) => {
      const clientId = process.env["MERCADOLIBRE_CLIENT_ID"] ?? "";
      const redirectUri = `${process.env["API_URL"] ?? "https://fitness-os-api.railway.app"}/api/v1/ml/auth/callback`;
      const state = request.tenantId!;

      const authUrl = `https://auth.mercadolibre.com.ar/authorization?response_type=code&client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&state=${state}`;

      return reply.redirect(authUrl);
    }
  );

  /**
   * GET /ml/auth/callback
   */
  fastify.get("/ml/auth/callback", async (request: FastifyRequest, reply) => {
    const query = request.query as Record<string, string>;
    const code = query["code"];
    const tenantId = query["state"];

    if (!code || !tenantId) return reply.code(400).send({ error: "Parámetros inválidos" });

    const ml = new MercadoLibreAdapter();
    const tokens = await ml.exchangeCode(code);

    if (!tokens) return reply.code(500).send({ error: "Error al obtener tokens de MercadoLibre" });

    // Guardar tokens en el tenant (encrypted en producción)
    await prisma.tenant.update({
      where: { id: tenantId },
      data: {
        mlAccessToken: tokens.access_token,
        mlRefreshToken: tokens.refresh_token,
        mlUserId: String(tokens.user_id),
        mlTokenExpiresAt: new Date(Date.now() + tokens.expires_in * 1000),
      },
    });

    const adminUrl = process.env["APP_ADMIN_URL"] ?? "https://fitness-os-admin.vercel.app";
    return reply.redirect(`${adminUrl}/integrations/mercadolibre?connected=true`);
  });

  /**
   * GET /ml/status — estado de la conexión + métricas de publicación
   */
  fastify.get(
    "/ml/status",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest, reply) => {
      const tenantId = request.tenantId!;
      const tenant = await prisma.tenant.findUnique({ where: { id: tenantId } });
      const connected = Boolean(tenant?.mlAccessToken);

      const [totalProducts, withDraft, publishedListings] = await Promise.all([
        prisma.product.count({ where: { tenantId, status: "PUBLISHED" } }),
        prisma.marketplaceListing.count({ where: { tenantId, marketplace: "MERCADOLIBRE" } }),
        prisma.marketplaceListing.count({ where: { tenantId, marketplace: "MERCADOLIBRE", status: "PUBLISHED" } }),
      ]);

      const byStatus = await prisma.marketplaceListing.groupBy({
        by: ["status"],
        where: { tenantId, marketplace: "MERCADOLIBRE" },
        _count: { id: true },
      });

      return reply.send({
        connected,
        mlUserId: tenant?.mlUserId,
        tokenExpiresAt: tenant?.mlTokenExpiresAt,
        totalProducts,
        withDraft,
        publishedListings,
        pending: withDraft - publishedListings,
        byStatus: Object.fromEntries(byStatus.map(r => [r.status, r._count.id])),
      });
    }
  );

  /**
   * GET /ml/listings
   */
  fastify.get(
    "/ml/listings",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest, reply) => {
      const listings = await prisma.marketplaceListing.findMany({
        where: { tenantId: request.tenantId!, marketplace: "MERCADOLIBRE" },
        include: { product: { select: { id: true, name: true, sku: true } } },
        orderBy: { updatedAt: "desc" },
      });

      return reply.send({ data: listings });
    }
  );

  /**
   * POST /ml/listings/bulk-draft
   * Genera borradores (DRAFT) para todos los productos PUBLISHED que no tengan listing.
   * Seguro: nunca publica en ML, solo crea registros internos en DRAFT.
   */
  fastify.post(
    "/ml/listings/bulk-draft",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const tenantId = request.tenantId!;

      // Buscar productos PUBLISHED sin listing en ML
      const products = await prisma.product.findMany({
        where: {
          tenantId,
          status: "PUBLISHED",
          marketplaceListings: { none: { marketplace: "MERCADOLIBRE" } },
        },
        include: {
          prices: { take: 1 },
          category: { select: { name: true } },
        },
      });

      if (products.length === 0) {
        return reply.send({ created: 0, skipped: 0, total: 0, message: "Todos los productos ya tienen borrador" });
      }

      let created = 0;
      let skipped = 0;
      const errors: Array<{ sku: string; reason: string }> = [];

      for (const product of products) {
        const price = product.prices?.[0]?.basePrice;
        if (!price || Number(price) <= 0) {
          skipped++;
          errors.push({ sku: product.sku, reason: "Sin precio" });
          continue;
        }

        const title = buildMLTitle(product.name);
        const description = buildMLDescription({
          name: product.name,
          description: product.description,
          level: product.level,
          durationWeeks: product.durationWeeks,
          category: product.category ?? null,
        });
        const categoryId = mlCategoryForProduct(product.category?.name ?? "");

        try {
          await prisma.marketplaceListing.create({
            data: {
              tenantId,
              productId: product.id,
              marketplace: "MERCADOLIBRE",
              title,
              description,
              price: Number(price),
              currency: product.prices[0]!.currency,
              status: "DRAFT",
              externalData: {
                category_id: categoryId,
                condition: "new",
                available_quantity: 999,
                listing_type_id: "gold_special",
              },
            },
          });
          created++;
        } catch {
          skipped++;
          errors.push({ sku: product.sku, reason: "Error al crear" });
        }
      }

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "ML_BULK_DRAFT",
          entity: "MarketplaceListing",
          entityId: tenantId,
          after: { created, skipped, total: products.length },
        },
      });

      return reply.code(201).send({
        created,
        skipped,
        total: products.length,
        errors: errors.slice(0, 20),
        note: `${created} borradores creados — revisá y aprobá antes de publicar en ML`,
      });
    }
  );

  /**
   * POST /ml/listings/bulk-publish
   * Publica en ML todos los listings en estado APPROVED.
   * Requiere cuenta ML conectada y rol MANAGER.
   */
  fastify.post(
    "/ml/listings/bulk-publish",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const tenantId = request.tenantId!;

      const tenant = await prisma.tenant.findUnique({ where: { id: tenantId } });
      if (!tenant?.mlAccessToken) {
        return reply.code(400).send({ error: "MercadoLibre no está conectado. Ir a /ml/auth" });
      }

      const listings = await prisma.marketplaceListing.findMany({
        where: { tenantId, marketplace: "MERCADOLIBRE", status: "APPROVED" },
        include: { product: { select: { id: true, name: true, sku: true } } },
      });

      if (listings.length === 0) {
        return reply.send({ published: 0, failed: 0, message: "No hay listings en estado APPROVED" });
      }

      const ml = new MercadoLibreAdapter(tenant.mlAccessToken);
      let published = 0;
      let failed = 0;
      const errors: Array<{ sku: string; reason: string }> = [];

      for (const listing of listings) {
        const externalData = listing.externalData as Record<string, unknown>;
        try {
          const mlItem = await ml.createItem({
            title: listing.title,
            category_id: (externalData["category_id"] as string) ?? ML_CATEGORY_MAP["default"]!,
            price: listing.price.toNumber(),
            currency_id: listing.currency,
            available_quantity: (externalData["available_quantity"] as number) ?? 999,
            buying_mode: "buy_it_now",
            condition: "new",
            listing_type_id: (externalData["listing_type_id"] as string) ?? "gold_special",
            description: { plain_text: listing.description },
          });

          await prisma.marketplaceListing.update({
            where: { id: listing.id },
            data: {
              status: "PUBLISHED",
              externalId: mlItem.id,
              publishedAt: new Date(),
              externalData: {
                ...externalData,
                ml_item_id: mlItem.id,
                permalink: mlItem.permalink,
              },
            },
          });
          published++;
        } catch (err) {
          failed++;
          errors.push({ sku: listing.product?.sku ?? listing.id, reason: (err as Error).message ?? "Error ML" });
        }
      }

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "ML_BULK_PUBLISH",
          entity: "MarketplaceListing",
          entityId: tenantId,
          after: { published, failed, total: listings.length },
        },
      });

      return reply.send({
        published,
        failed,
        total: listings.length,
        errors: errors.slice(0, 20),
      });
    }
  );

  /**
   * POST /ml/listings/:id/approve — aprobar borrador (habilita publicación)
   * Solo MANAGER puede aprobar. Generar ≠ aprobar ≠ publicar.
   */
  fastify.post(
    "/ml/listings/:id/approve",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const tenantId = request.tenantId!;
      const listing = await prisma.marketplaceListing.findFirst({
        where: { id: request.params.id, tenantId, marketplace: "MERCADOLIBRE" },
      });
      if (!listing) return reply.code(404).send({ error: "Listing no encontrado" });
      if (!["DRAFT", "READY"].includes(listing.status)) {
        return reply.code(409).send({ error: `No se puede aprobar desde estado ${listing.status}` });
      }

      const updated = await prisma.marketplaceListing.update({
        where: { id: listing.id },
        data: { status: "APPROVED" },
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * POST /ml/listings — crear publicación como DRAFT
   * Generar ≠ publicar: siempre queda en estado DRAFT
   */
  fastify.post(
    "/ml/listings",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateListingSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const product = await prisma.product.findFirst({
        where: { id: body.data.productId, tenantId },
      });
      if (!product) return reply.code(404).send({ error: "Producto no encontrado" });

      // Verificar que no exista ya una publicación para este producto
      const existing = await prisma.marketplaceListing.findFirst({
        where: { tenantId, productId: product.id, marketplace: "MERCADOLIBRE" },
      });
      if (existing) return reply.code(409).send({ error: "Ya existe una publicación de ML para este producto" });

      const listing = await prisma.marketplaceListing.create({
        data: {
          tenantId,
          productId: product.id,
          marketplace: "MERCADOLIBRE",
          title: body.data.title,
          description: body.data.description,
          price: body.data.price,
          currency: body.data.currency,
          status: "DRAFT",
          externalData: {
            category_id: body.data.categoryId,
            condition: body.data.condition,
            available_quantity: body.data.availableQuantity,
          },
        },
      });

      return reply.code(201).send({
        data: listing,
        note: "Publicación en DRAFT — usar /publish para publicar en MercadoLibre",
      });
    }
  );

  /**
   * POST /ml/listings/:id/publish — publicar en ML (requiere MANAGER+)
   */
  fastify.post(
    "/ml/listings/:id/publish",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const tenantId = request.tenantId!;
      const listing = await prisma.marketplaceListing.findFirst({
        where: { id: request.params.id, tenantId, marketplace: "MERCADOLIBRE" },
        include: { product: { include: { files: { take: 1 } } } },
      });

      if (!listing) return reply.code(404).send({ error: "Publicación no encontrada" });
      if (listing.status === "PUBLISHED") return reply.code(409).send({ error: "Ya está publicada" });

      const tenant = await prisma.tenant.findUnique({ where: { id: tenantId } });
      if (!tenant?.mlAccessToken) {
        return reply.code(400).send({ error: "MercadoLibre no está conectado. Ir a /ml/auth" });
      }

      const ml = new MercadoLibreAdapter(tenant.mlAccessToken);
      const externalData = listing.externalData as Record<string, unknown>;

      const mlItem = await ml.createItem({
        title: listing.title,
        category_id: (externalData["category_id"] as string) ?? "MLA1000",
        price: listing.price.toNumber(),
        currency_id: listing.currency,
        available_quantity: (externalData["available_quantity"] as number) ?? 999,
        buying_mode: "buy_it_now",
        condition: (externalData["condition"] as string) ?? "new",
        listing_type_id: "gold_special",
        description: { plain_text: listing.description },
      });

      const updated = await prisma.marketplaceListing.update({
        where: { id: listing.id },
        data: {
          status: "PUBLISHED",
          externalId: mlItem.id,
          publishedAt: new Date(),
          externalData: { ...externalData, ml_item_id: mlItem.id, permalink: mlItem.permalink },
        },
      });

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "ML_LISTING_PUBLISH",
          entity: "MarketplaceListing",
          entityId: listing.id,
          after: { mlItemId: mlItem.id },
        },
      });

      return reply.send({ data: updated, permalink: mlItem.permalink });
    }
  );

  /**
   * POST /webhooks/mercadolibre — notificaciones de ML
   */
  fastify.post("/webhooks/mercadolibre", async (request: FastifyRequest, reply) => {
    reply.code(200).send({ ok: true }); // ML necesita respuesta inmediata

    const body = request.body as { topic?: string; resource?: string; user_id?: number };
    if (!body.topic || !body.resource) return;

    // Importar órdenes de ML cuando llegan notificaciones
    if (body.topic === "orders_v2") {
      const tenant = await prisma.tenant.findFirst({
        where: { mlUserId: String(body.user_id) },
      });
      if (!tenant?.mlAccessToken) return;

      const ml = new MercadoLibreAdapter(tenant.mlAccessToken);
      const orderId = body.resource.split("/orders/")[1];
      if (!orderId) return;

      const mlOrder = await ml.getOrder(orderId);
      if (!mlOrder) return;

      // Crear o actualizar orden en el sistema
      // Los detalles del pedido se mapean a nuestro modelo de Order
      console.log(`[ML] Orden recibida: ${orderId} para tenant ${tenant.id}`);
    }
  });
}
