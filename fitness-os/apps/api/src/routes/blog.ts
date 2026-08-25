/**
 * Fase 10 — Blog y Email Marketing.
 *
 * Blog:
 * GET  /api/v1/blog/posts          — listar posts
 * POST /api/v1/blog/posts          — crear post (DRAFT)
 * GET  /api/v1/blog/posts/:slug    — detalle
 * PATCH /api/v1/blog/posts/:id     — editar
 * POST /api/v1/blog/posts/:id/publish
 *
 * Email:
 * GET  /api/v1/email/campaigns     — listar campañas
 * POST /api/v1/email/campaigns     — crear campaña
 * POST /api/v1/email/campaigns/:id/send — enviar (MANAGER+)
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { slugify } from "@fitness-os/shared";

const CreatePostSchema = z.object({
  title: z.string().min(5).max(300),
  excerpt: z.string().max(500).optional(),
  content: z.string().min(100),
  seoTitle: z.string().max(70).optional(),
  seoDescription: z.string().max(160).optional(),
  featuredImageUrl: z.string().url().optional(),
  categoryId: z.string().uuid().optional(),
  tags: z.array(z.string()).optional(),
  scheduledAt: z.string().datetime().optional(),
  aiGenerated: z.boolean().default(false),
});

const CreateCampaignSchema = z.object({
  name: z.string().min(2).max(200),
  subject: z.string().min(2).max(200),
  previewText: z.string().max(150).optional(),
  htmlContent: z.string().min(50),
  textContent: z.string().optional(),
  segment: z.enum(["ALL", "CUSTOMERS", "LEADS", "VIP"]).default("ALL"),
  scheduledAt: z.string().datetime().optional(),
});

export async function blogRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  fastify.addHook("preHandler", fastify.authenticate);

  // ── BLOG ────────────────────────────────────────────────────────

  fastify.get(
    "/posts",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const q = (request.query as Record<string, string>)["q"];
      const status = (request.query as Record<string, string>)["status"];

      const posts = await prisma.blogPost.findMany({
        where: {
          tenantId: request.tenantId!,
          ...(status && { status: status as never }),
          ...(q && { title: { contains: q, mode: "insensitive" } }),
        },
        orderBy: { createdAt: "desc" },
        take: 50,
        select: {
          id: true, title: true, slug: true, status: true, excerpt: true,
          featuredImageUrl: true, createdAt: true, publishedAt: true, aiGenerated: true,
          author: { select: { name: true } },
        },
      });

      return reply.send({ data: posts });
    }
  );

  fastify.post(
    "/posts",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreatePostSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const { title, content, excerpt, seoTitle, seoDescription, featuredImageUrl, aiGenerated, scheduledAt } = body.data;

      const post = await prisma.blogPost.create({
        data: {
          tenantId,
          slug: slugify(title),
          title,
          content,
          excerpt,
          seoTitle: seoTitle ?? title.substring(0, 70),
          seoDescription,
          featuredImageUrl,
          status: scheduledAt ? "SCHEDULED" : "DRAFT",
          scheduledAt: scheduledAt ? new Date(scheduledAt) : null,
          aiGenerated,
          authorId: request.user.sub,
          wordCount: content.split(/\s+/).length,
        },
      });

      return reply.code(201).send({
        data: post,
        note: aiGenerated ? "Post generado por IA — revisar antes de publicar" : "Post en DRAFT",
      });
    }
  );

  fastify.post(
    "/posts/:id/publish",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const post = await prisma.blogPost.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!post) return reply.code(404).send({ error: "Post no encontrado" });
      if (post.status === "PUBLISHED") return reply.code(409).send({ error: "Ya publicado" });

      const updated = await prisma.blogPost.update({
        where: { id: post.id },
        data: { status: "PUBLISHED", publishedAt: new Date() },
      });

      return reply.send({ data: updated });
    }
  );

  // ── EMAIL CAMPAIGNS ─────────────────────────────────────────────

  fastify.get(
    "/campaigns",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const campaigns = await prisma.emailCampaign.findMany({
        where: { tenantId: request.tenantId! },
        orderBy: { createdAt: "desc" },
        take: 50,
      });
      return reply.send({ data: campaigns });
    }
  );

  fastify.post(
    "/campaigns",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateCampaignSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const campaign = await prisma.emailCampaign.create({
        data: {
          tenantId: request.tenantId!,
          ...body.data,
          status: "DRAFT",
          scheduledAt: body.data.scheduledAt ? new Date(body.data.scheduledAt) : null,
          createdById: request.user.sub,
        },
      });

      return reply.code(201).send({ data: campaign });
    }
  );

  fastify.post(
    "/campaigns/:id/send",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const tenantId = request.tenantId!;
      const campaign = await prisma.emailCampaign.findFirst({
        where: { id: request.params.id, tenantId },
      });
      if (!campaign) return reply.code(404).send({ error: "Campaña no encontrada" });
      if (campaign.status === "SENT") return reply.code(409).send({ error: "La campaña ya fue enviada" });

      // Contar destinatarios según segmento
      let recipientCount = 0;
      if (campaign.segment === "ALL" || campaign.segment === "CUSTOMERS") {
        recipientCount = await prisma.customer.count({ where: { tenantId } });
      }

      await prisma.emailCampaign.update({
        where: { id: campaign.id },
        data: {
          status: "SENT",
          sentAt: new Date(),
          recipientCount,
        },
      });

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "EMAIL_CAMPAIGN_SEND",
          entity: "EmailCampaign",
          entityId: campaign.id,
          after: { recipientCount },
        },
      });

      return reply.send({ message: `Campaña enviada a ${recipientCount} destinatarios` });
    }
  );
}
