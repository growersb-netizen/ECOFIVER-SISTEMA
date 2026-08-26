/**
 * Rutas de administración de cupones.
 *
 * GET    /api/v1/admin/coupons         — listar
 * POST   /api/v1/admin/coupons         — crear
 * PATCH  /api/v1/admin/coupons/:id     — editar
 * DELETE /api/v1/admin/coupons/:id     — desactivar (soft delete)
 *
 * Requiere rol TENANT_ADMIN o MANAGER.
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";

const CreateCouponSchema = z.object({
  code: z.string()
    .min(3).max(50)
    .transform(s => s.toUpperCase().trim()),
  description: z.string().max(200).optional(),
  discountPct: z.number().min(1).max(100).optional(),
  discountAmt: z.number().min(1).optional(),
  maxUses: z.number().int().min(1).optional(),
  validUntil: z.string().datetime({ offset: true }).optional()
    .transform(v => v ? new Date(v) : undefined),
  active: z.boolean().default(true),
}).refine(d => d.discountPct || d.discountAmt, {
  message: "Se debe especificar descuentoPct o descuentoAmt",
});

const UpdateCouponSchema = z.object({
  description: z.string().max(200).optional(),
  discountPct: z.number().min(1).max(100).optional(),
  discountAmt: z.number().min(1).optional(),
  maxUses: z.number().int().min(1).nullable().optional(),
  validUntil: z.string().datetime({ offset: true }).nullable().optional()
    .transform(v => v ? new Date(v) : null),
  active: z.boolean().optional(),
});

export async function couponRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  /**
   * GET /admin/coupons — listar todos los cupones del tenant
   */
  fastify.get(
    "/admin/coupons",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const tenantId = request.tenantId!;
      const { active } = request.query as { active?: string };

      const coupons = await prisma.coupon.findMany({
        where: {
          tenantId,
          ...(active !== undefined ? { active: active === "true" } : {}),
        },
        orderBy: { createdAt: "desc" },
        include: {
          _count: { select: { orders: true } },
        },
      });

      return reply.send({ data: coupons });
    }
  );

  /**
   * POST /admin/coupons — crear cupón
   */
  fastify.post(
    "/admin/coupons",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateCouponSchema.safeParse(request.body);
      if (!body.success) {
        return reply.code(400).send({ error: "Datos inválidos", details: body.error.flatten() });
      }

      const tenantId = request.tenantId!;
      const { code, description, discountPct, discountAmt, maxUses, validUntil, active } = body.data;

      // Verificar unicidad del código en este tenant
      const existing = await prisma.coupon.findFirst({ where: { tenantId, code } });
      if (existing) {
        return reply.code(409).send({ error: `El código "${code}" ya existe` });
      }

      const coupon = await prisma.coupon.create({
        data: {
          tenantId,
          code,
          description: description ?? null,
          discountPct: discountPct ?? null,
          discountAmt: discountAmt ?? null,
          maxUses: maxUses ?? null,
          validUntil: validUntil ?? null,
          active,
        },
      });

      return reply.code(201).send({ data: coupon });
    }
  );

  /**
   * PATCH /admin/coupons/:id — editar cupón
   */
  fastify.patch(
    "/admin/coupons/:id",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = UpdateCouponSchema.safeParse(request.body);
      if (!body.success) {
        return reply.code(400).send({ error: "Datos inválidos", details: body.error.flatten() });
      }

      const coupon = await prisma.coupon.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!coupon) return reply.code(404).send({ error: "Cupón no encontrado" });

      const updated = await prisma.coupon.update({
        where: { id: coupon.id },
        data: {
          ...body.data,
          // null explícito para campos anulables
          maxUses: body.data.maxUses ?? undefined,
          validUntil: body.data.validUntil ?? undefined,
        },
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * DELETE /admin/coupons/:id — desactivar (no elimina físicamente)
   */
  fastify.delete(
    "/admin/coupons/:id",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const coupon = await prisma.coupon.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!coupon) return reply.code(404).send({ error: "Cupón no encontrado" });

      // Soft-delete: solo desactivar para preservar historial de órdenes
      await prisma.coupon.update({
        where: { id: coupon.id },
        data: { active: false },
      });

      return reply.send({ ok: true, message: "Cupón desactivado" });
    }
  );
}
