/**
 * Fase 02 — Rutas de Categorías (árbol jerárquico).
 * GET  /api/v1/categories       — árbol completo
 * POST /api/v1/categories       — crear categoría
 * PATCH /api/v1/categories/:id  — editar
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { slugify } from "@fitness-os/shared";

const CreateCategorySchema = z.object({
  name: z.string().min(2).max(100),
  description: z.string().optional(),
  parentId: z.string().uuid().optional(),
  imageUrl: z.string().url().optional(),
  sortOrder: z.number().int().default(0),
});

export async function categoryRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  fastify.addHook("preHandler", fastify.authenticate);

  fastify.get("/", async (request: FastifyRequest, reply) => {
    const categories = await prisma.category.findMany({
      where: { tenantId: request.tenantId! },
      orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
      include: {
        children: {
          orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
          include: {
            children: { orderBy: [{ sortOrder: "asc" }, { name: "asc" }] },
          },
        },
        _count: { select: { products: true } },
      },
    });

    // Solo devolver raíces (sin padre)
    const roots = categories.filter((c) => c.parentId === null);
    return reply.send({ data: roots });
  });

  fastify.post(
    "/",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateCategorySchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const { name, description, parentId, imageUrl, sortOrder } = body.data;

      const category = await prisma.category.create({
        data: {
          tenantId,
          name,
          slug: slugify(name),
          description,
          parentId,
          imageUrl,
          sortOrder,
          active: true,
        },
      });

      return reply.code(201).send({ data: category });
    }
  );

  fastify.patch(
    "/:id",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = CreateCategorySchema.partial().safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const category = await prisma.category.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!category) return reply.code(404).send({ error: "Categoría no encontrada" });

      const updated = await prisma.category.update({
        where: { id: category.id },
        data: {
          ...body.data,
          ...(body.data.name && { slug: slugify(body.data.name) }),
        },
      });

      return reply.send({ data: updated });
    }
  );
}
