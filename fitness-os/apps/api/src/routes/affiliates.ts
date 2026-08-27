/**
 * Fase 12 — Programa de Afiliadas.
 *
 * GET  /api/v1/affiliates           — listar afiliadas
 * POST /api/v1/affiliates           — registrar afiliada
 * GET  /api/v1/affiliates/:id       — detalle + estadísticas
 * GET  /api/v1/affiliates/:id/links — links de la afiliada
 * POST /api/v1/affiliates/:id/links — crear link de afiliada
 * GET  /api/v1/affiliates/commissions — comisiones pendientes
 * POST /api/v1/affiliates/commissions/:id/pay — pagar comisión
 * GET  /api/v1/public/aff/:slug     — redirect con tracking (pública)
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { nanoid } from "nanoid";

const CreateAffiliateSchema = z.object({
  userId: z.string().uuid().optional(),
  name: z.string().min(2),
  email: z.string().email(),
  commissionRate: z.number().min(0).max(100).default(10), // porcentaje
  paymentMethod: z.string().optional(),
  paymentData: z.record(z.unknown()).optional(),
});

const CreateLinkSchema = z.object({
  productId: z.string().uuid().optional(),
  campaignName: z.string().optional(),
  customSlug: z.string().regex(/^[a-z0-9-]+$/).optional(),
});

export async function affiliateRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  // ── AFILIADAS ────────────────────────────────────────────────────

  fastify.get(
    "/",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const affiliates = await prisma.affiliate.findMany({
        where: { tenantId: request.tenantId! },
        include: {
          _count: { select: { links: true, commissions: true } },
          user: { select: { id: true, name: true, email: true } },
        },
        orderBy: { createdAt: "desc" },
      });

      return reply.send({ data: affiliates });
    }
  );

  fastify.post(
    "/",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateAffiliateSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;

      const affiliate = await prisma.affiliate.create({
        data: {
          tenantId,
          name: body.data.name,
          email: body.data.email,
          commissionRate: body.data.commissionRate,
          paymentMethod: body.data.paymentMethod,
          paymentData: body.data.paymentData,
          active: true,
          ...(body.data.userId && { userId: body.data.userId }),
        },
      });

      return reply.code(201).send({ data: affiliate });
    }
  );

  fastify.get(
    "/:id",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const affiliate = await prisma.affiliate.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
        include: {
          links: { include: { _count: { select: { attributions: true } } } },
          commissions: { orderBy: { createdAt: "desc" }, take: 20 },
          user: { select: { id: true, name: true, email: true } },
        },
      });

      if (!affiliate) return reply.code(404).send({ error: "Afiliada no encontrada" });

      // Calcular estadísticas
      const totalEarned = affiliate.commissions
        .filter((c) => c.status !== "CANCELLED")
        .reduce((acc, c) => acc + c.amount.toNumber(), 0);
      const pendingAmount = affiliate.commissions
        .filter((c) => c.status === "PENDING")
        .reduce((acc, c) => acc + c.amount.toNumber(), 0);

      return reply.send({
        data: affiliate,
        stats: { totalEarned, pendingAmount, totalLinks: affiliate.links.length },
      });
    }
  );

  // ── LINKS ────────────────────────────────────────────────────────

  fastify.post(
    "/:id/links",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = CreateLinkSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const affiliate = await prisma.affiliate.findFirst({
        where: { id: request.params.id, tenantId },
      });
      if (!affiliate) return reply.code(404).send({ error: "Afiliada no encontrada" });

      const slug = body.data.customSlug ?? `${affiliate.email.split("@")[0]}-${nanoid(6)}`;

      // Verificar que el slug no exista
      const existing = await prisma.affiliateLink.findUnique({ where: { slug } });
      if (existing) return reply.code(409).send({ error: "El slug ya está en uso" });

      const webUrl = process.env["APP_WEB_URL"] ?? "https://fitness-os.vercel.app";
      const link = await prisma.affiliateLink.create({
        data: {
          affiliateId: affiliate.id,
          slug,
          productId: body.data.productId ?? null,
          campaignName: body.data.campaignName,
          url: `${webUrl}/ref/${slug}`,
          active: true,
        },
      });

      return reply.code(201).send({ data: link });
    }
  );

  // ── REDIRECT TRACKING (pública) ──────────────────────────────────
  // Esta ruta va en el servidor web, no en el admin
  // /api/v1/public/aff/:slug

  fastify.get("/public/ref/:slug", async (request: FastifyRequest<{ Params: { slug: string } }>, reply) => {
    const link = await prisma.affiliateLink.findUnique({
      where: { slug: request.params.slug, active: true },
      include: { product: { select: { slug: true } } },
    });

    if (!link) return reply.redirect("https://fitness-os.vercel.app");

    // Registrar click (atribución se completa cuando hay compra)
    await prisma.attribution.create({
      data: {
        linkId: link.id,
        ip: request.ip,
        userAgent: request.headers["user-agent"] ?? null,
        clickedAt: new Date(),
      },
    });

    // Redirect al producto o a la tienda
    const webUrl = process.env["APP_WEB_URL"] ?? "https://fitness-os.vercel.app";
    const destination = link.product?.slug
      ? `${webUrl}/productos/${link.product.slug}?ref=${link.slug}`
      : `${webUrl}?ref=${link.slug}`;

    return reply.redirect(destination);
  });

  // ── COMISIONES ───────────────────────────────────────────────────

  fastify.get(
    "/commissions",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const commissions = await prisma.commission.findMany({
        where: {
          affiliate: { tenantId: request.tenantId! },
          status: "PENDING",
        },
        include: {
          affiliate: { select: { id: true, name: true, email: true } },
          order: { select: { id: true, total: true, createdAt: true } },
        },
        orderBy: { createdAt: "desc" },
      });

      const total = commissions.reduce((acc, c) => acc + c.amount.toNumber(), 0);
      return reply.send({ data: commissions, totalPending: total });
    }
  );
}
