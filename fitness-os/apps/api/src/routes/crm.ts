/**
 * Fase 06 — Rutas de CRM (Leads y Conversaciones).
 *
 * GET  /api/v1/crm/leads          — listar leads
 * POST /api/v1/crm/leads          — crear lead
 * GET  /api/v1/crm/leads/:id      — detalle
 * PATCH /api/v1/crm/leads/:id     — actualizar status/nota
 * GET  /api/v1/crm/conversations  — listar conversaciones
 * GET  /api/v1/crm/conversations/:id — detalle con mensajes
 * POST /api/v1/crm/conversations/:id/messages — enviar mensaje
 * GET  /api/v1/crm/customers      — clientes con historial
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";

const CreateLeadSchema = z.object({
  name: z.string().min(2).max(200),
  email: z.string().email().optional(),
  phone: z.string().optional(),
  source: z.enum(["WHATSAPP", "INSTAGRAM", "FACEBOOK", "TIKTOK", "YOUTUBE", "EMAIL", "WEB", "MERCADOLIBRE"]),
  notes: z.string().optional(),
  tags: z.array(z.string()).optional(),
  productInterest: z.string().optional(),
});

const UpdateLeadSchema = z.object({
  status: z.enum(["NEW", "CONTACTED", "INTERESTED", "NEGOTIATING", "CONVERTED", "LOST", "UNQUALIFIED"]).optional(),
  notes: z.string().optional(),
  tags: z.array(z.string()).optional(),
  assignedToId: z.string().uuid().optional(),
});

const SendMessageSchema = z.object({
  content: z.string().min(1).max(4000),
  type: z.enum(["TEXT", "IMAGE", "DOCUMENT", "AUDIO", "VIDEO"]).default("TEXT"),
  mediaUrl: z.string().url().optional(),
});

const ListLeadsQuerySchema = z.object({
  page: z.string().transform(Number).default("1"),
  pageSize: z.string().transform(Number).default("20"),
  status: z.string().optional(),
  source: z.string().optional(),
  assignedToId: z.string().optional(),
  q: z.string().optional(),
  from: z.string().optional(),
  to: z.string().optional(),
});

export async function crmRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  fastify.addHook("preHandler", fastify.authenticate);

  // ── LEADS ────────────────────────────────────────────────────────

  fastify.get(
    "/leads",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest, reply) => {
      const query = ListLeadsQuerySchema.safeParse(request.query);
      if (!query.success) return reply.code(400).send({ error: "Parámetros inválidos" });

      const { page, pageSize, status, source, assignedToId, q, from, to } = query.data;
      const skip = (Math.max(1, page) - 1) * Math.min(100, pageSize);

      const where = {
        tenantId: request.tenantId!,
        ...(status && { status: status as never }),
        ...(source && { source: source as never }),
        ...(assignedToId && { assignedToId }),
        ...(q && {
          OR: [
            { name: { contains: q, mode: "insensitive" as const } },
            { email: { contains: q, mode: "insensitive" as const } },
            { phone: { contains: q } },
          ],
        }),
        ...(from || to ? {
          createdAt: {
            ...(from && { gte: new Date(from) }),
            ...(to && { lte: new Date(to) }),
          },
        } : {}),
      };

      const [total, items] = await Promise.all([
        prisma.lead.count({ where }),
        prisma.lead.findMany({
          where,
          skip,
          take: Math.min(100, pageSize),
          orderBy: { createdAt: "desc" },
          include: {
            assignedTo: { select: { id: true, name: true, email: true } },
            _count: { select: { conversations: true } },
          },
        }),
      ]);

      return reply.send({
        data: items,
        pagination: { page, pageSize, total, totalPages: Math.ceil(total / pageSize) },
      });
    }
  );

  fastify.post(
    "/leads",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateLeadSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const lead = await prisma.lead.create({
        data: {
          tenantId,
          ...body.data,
          status: "NEW",
        },
      });

      return reply.code(201).send({ data: lead });
    }
  );

  fastify.get(
    "/leads/:id",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const lead = await prisma.lead.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
        include: {
          assignedTo: { select: { id: true, name: true, email: true } },
          conversations: {
            orderBy: { updatedAt: "desc" },
            take: 5,
            include: { _count: { select: { messages: true } } },
          },
        },
      });

      if (!lead) return reply.code(404).send({ error: "Lead no encontrado" });
      return reply.send({ data: lead });
    }
  );

  fastify.patch(
    "/leads/:id",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = UpdateLeadSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const lead = await prisma.lead.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!lead) return reply.code(404).send({ error: "Lead no encontrado" });

      // Si se convierte a CONVERTED, crear Customer si no existe
      if (body.data.status === "CONVERTED" && lead.email) {
        await prisma.customer.upsert({
          where: { tenantId_email: { tenantId: request.tenantId!, email: lead.email } },
          update: {},
          create: {
            tenantId: request.tenantId!,
            email: lead.email,
            name: lead.name,
            phone: lead.phone,
          },
        });
      }

      const updated = await prisma.lead.update({
        where: { id: lead.id },
        data: body.data,
      });

      return reply.send({ data: updated });
    }
  );

  // ── CONVERSACIONES ────────────────────────────────────────────────

  fastify.get(
    "/conversations",
    { preHandler: [requireRole("SUPPORT")] },
    async (request: FastifyRequest, reply) => {
      const q = (request.query as Record<string, string>)["q"];
      const channel = (request.query as Record<string, string>)["channel"];

      const conversations = await prisma.conversation.findMany({
        where: {
          tenantId: request.tenantId!,
          ...(channel && { channel: channel as never }),
        },
        orderBy: { updatedAt: "desc" },
        take: 50,
        include: {
          lead: { select: { id: true, name: true, phone: true } },
          customer: { select: { id: true, name: true, email: true } },
          messages: { orderBy: { createdAt: "desc" }, take: 1 },
          _count: { select: { messages: true } },
        },
      });

      const filtered = q
        ? conversations.filter(
            (c) =>
              c.lead?.name.toLowerCase().includes(q.toLowerCase()) ||
              c.customer?.name.toLowerCase().includes(q.toLowerCase())
          )
        : conversations;

      return reply.send({ data: filtered });
    }
  );

  fastify.get(
    "/conversations/:id",
    { preHandler: [requireRole("SUPPORT")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const conversation = await prisma.conversation.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
        include: {
          lead: true,
          customer: true,
          messages: { orderBy: { createdAt: "asc" }, take: 200 },
        },
      });

      if (!conversation) return reply.code(404).send({ error: "Conversación no encontrada" });
      return reply.send({ data: conversation });
    }
  );

  fastify.post(
    "/conversations/:id/messages",
    { preHandler: [requireRole("SUPPORT")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = SendMessageSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const conversation = await prisma.conversation.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!conversation) return reply.code(404).send({ error: "Conversación no encontrada" });

      const message = await prisma.message.create({
        data: {
          conversationId: conversation.id,
          direction: "OUTBOUND",
          type: body.data.type,
          content: body.data.content,
          mediaUrl: body.data.mediaUrl,
          sentBy: request.user.sub,
          status: "SENT",
        },
      });

      // Actualizar updatedAt de la conversación
      await prisma.conversation.update({
        where: { id: conversation.id },
        data: { updatedAt: new Date() },
      });

      return reply.code(201).send({ data: message });
    }
  );

  // ── CUSTOMERS ────────────────────────────────────────────────────

  fastify.get(
    "/customers",
    { preHandler: [requireRole("SALES")] },
    async (request: FastifyRequest, reply) => {
      const q = (request.query as Record<string, string>)["q"];
      const page = parseInt((request.query as Record<string, string>)["page"] ?? "1");
      const pageSize = Math.min(100, parseInt((request.query as Record<string, string>)["pageSize"] ?? "20"));

      const where = {
        tenantId: request.tenantId!,
        ...(q && {
          OR: [
            { name: { contains: q, mode: "insensitive" as const } },
            { email: { contains: q, mode: "insensitive" as const } },
            { phone: { contains: q } },
          ],
        }),
      };

      const [total, items] = await Promise.all([
        prisma.customer.count({ where }),
        prisma.customer.findMany({
          where,
          skip: (page - 1) * pageSize,
          take: pageSize,
          orderBy: { createdAt: "desc" },
          include: {
            _count: { select: { orders: true, libraryItems: true } },
          },
        }),
      ]);

      return reply.send({
        data: items,
        pagination: { page, pageSize, total, totalPages: Math.ceil(total / pageSize) },
      });
    }
  );
}
