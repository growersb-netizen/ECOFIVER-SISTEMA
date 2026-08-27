/**
 * Fase 09 — Redes Sociales (Instagram, Facebook, TikTok, YouTube).
 *
 * Generar ≠ Publicar — siempre DRAFT → revisión → SCHEDULED → publish
 *
 * POST /api/v1/social/publications        — crear publicación (DRAFT)
 * GET  /api/v1/social/publications        — listar
 * PATCH /api/v1/social/publications/:id   — editar
 * POST /api/v1/social/publications/:id/schedule  — programar
 * POST /api/v1/social/publications/:id/publish   — publicar ahora
 * DELETE /api/v1/social/publications/:id          — cancelar
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";

const CreatePublicationSchema = z.object({
  platform: z.enum(["INSTAGRAM", "FACEBOOK", "TIKTOK", "YOUTUBE"]),
  type: z.enum(["POST", "STORY", "REEL", "VIDEO", "CAROUSEL"]),
  caption: z.string().max(2200).optional(),
  mediaUrls: z.array(z.string().url()).optional(),
  hashtags: z.array(z.string()).optional(),
  scheduledAt: z.string().datetime().optional(),
  productId: z.string().uuid().optional(),
  aiGenerated: z.boolean().default(false),
});

const UpdatePublicationSchema = CreatePublicationSchema.partial();

const SchedulePublicationSchema = z.object({
  scheduledAt: z.string().datetime(),
});

export async function socialRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  fastify.addHook("preHandler", fastify.authenticate);

  /**
   * POST /publications — crear en DRAFT
   */
  fastify.post(
    "/publications",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreatePublicationSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;

      // Armar caption completo con hashtags
      const { caption, hashtags, ...rest } = body.data;
      const fullCaption = [
        caption,
        hashtags?.length ? "\n\n" + hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ") : "",
      ]
        .filter(Boolean)
        .join("");

      const publication = await prisma.publication.create({
        data: {
          tenantId,
          platform: rest.platform,
          type: rest.type,
          caption: fullCaption || null,
          mediaUrls: rest.mediaUrls ?? [],
          status: "DRAFT",
          aiGenerated: rest.aiGenerated,
          scheduledAt: rest.scheduledAt ? new Date(rest.scheduledAt) : null,
          productId: rest.productId ?? null,
          createdById: request.user.sub,
        },
      });

      return reply.code(201).send({
        data: publication,
        note: "Publicación en DRAFT — revisar y programar antes de publicar",
      });
    }
  );

  /**
   * GET /publications
   */
  fastify.get(
    "/publications",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const q = request.query as Record<string, string>;
      const platform = q["platform"];
      const status = q["status"];

      const publications = await prisma.publication.findMany({
        where: {
          tenantId: request.tenantId!,
          ...(platform && { platform: platform as never }),
          ...(status && { status: status as never }),
        },
        orderBy: [
          { scheduledAt: "asc" },
          { createdAt: "desc" },
        ],
        include: {
          product: { select: { id: true, name: true } },
          createdBy: { select: { id: true, name: true } },
        },
      });

      return reply.send({ data: publications });
    }
  );

  /**
   * PATCH /publications/:id
   */
  fastify.patch(
    "/publications/:id",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = UpdatePublicationSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const publication = await prisma.publication.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!publication) return reply.code(404).send({ error: "Publicación no encontrada" });
      if (publication.status === "PUBLISHED") {
        return reply.code(409).send({ error: "No se puede editar una publicación ya publicada" });
      }

      const { caption, hashtags, scheduledAt, ...rest } = body.data;
      const fullCaption = caption !== undefined
        ? [
            caption,
            hashtags?.length ? "\n\n" + hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ") : "",
          ]
            .filter(Boolean)
            .join("")
        : undefined;

      const updated = await prisma.publication.update({
        where: { id: publication.id },
        data: {
          ...rest,
          ...(fullCaption !== undefined && { caption: fullCaption }),
          ...(scheduledAt !== undefined && { scheduledAt: new Date(scheduledAt) }),
        },
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * POST /publications/:id/schedule — programar publicación
   */
  fastify.post(
    "/publications/:id/schedule",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = SchedulePublicationSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Fecha inválida" });

      const publication = await prisma.publication.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!publication) return reply.code(404).send({ error: "Publicación no encontrada" });

      const scheduledAt = new Date(body.data.scheduledAt);
      if (scheduledAt <= new Date()) {
        return reply.code(422).send({ error: "La fecha de programación debe ser futura" });
      }

      const updated = await prisma.publication.update({
        where: { id: publication.id },
        data: { status: "SCHEDULED", scheduledAt },
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * POST /publications/:id/publish — publicar ahora
   * Requiere MANAGER+ — Generar ≠ Publicar
   */
  fastify.post(
    "/publications/:id/publish",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const tenantId = request.tenantId!;
      const publication = await prisma.publication.findFirst({
        where: { id: request.params.id, tenantId },
      });
      if (!publication) return reply.code(404).send({ error: "Publicación no encontrada" });
      if (publication.status === "PUBLISHED") return reply.code(409).send({ error: "Ya publicada" });

      // TODO Fase 09: llamar al adapter de la red social correspondiente
      // Por ahora se marca como PUBLISHED sin llamar a la API externa
      // La integración real requiere tokens OAuth de cada plataforma

      const updated = await prisma.publication.update({
        where: { id: publication.id },
        data: { status: "PUBLISHED", publishedAt: new Date() },
      });

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "PUBLICATION_PUBLISH",
          entity: "Publication",
          entityId: publication.id,
          after: { platform: publication.platform },
        },
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * DELETE /publications/:id — cancelar/eliminar DRAFT o SCHEDULED
   */
  fastify.delete(
    "/publications/:id",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const publication = await prisma.publication.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!publication) return reply.code(404).send({ error: "Publicación no encontrada" });
      if (publication.status === "PUBLISHED") {
        return reply.code(409).send({ error: "No se puede eliminar una publicación ya publicada" });
      }

      await prisma.publication.delete({ where: { id: publication.id } });
      return reply.send({ message: "Publicación eliminada" });
    }
  );
}
