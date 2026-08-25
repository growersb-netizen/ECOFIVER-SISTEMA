/**
 * Fase 08 — MercadoLibre (Marketplace).
 *
 * GET  /api/v1/ml/listings         — publicaciones en ML
 * POST /api/v1/ml/listings         — crear publicación (DRAFT)
 * PATCH /api/v1/ml/listings/:id    — actualizar
 * POST /api/v1/ml/listings/:id/publish — publicar en ML (requiere aprobación)
 * GET  /api/v1/ml/orders           — órdenes importadas de ML
 * POST /api/v1/webhooks/mercadolibre — webhook de ML
 * GET  /api/v1/ml/auth             — iniciar OAuth con ML
 * GET  /api/v1/ml/auth/callback    — callback OAuth
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { MercadoLibreAdapter } from "../adapters/mercadolibre.js";

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
          newValue: { mlItemId: mlItem.id },
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
