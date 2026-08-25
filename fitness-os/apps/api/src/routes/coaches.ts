/**
 * Fase 13 — Portal de Coaches.
 *
 * GET  /api/v1/coaches             — listar coaches del tenant
 * POST /api/v1/coaches             — registrar coach
 * GET  /api/v1/coaches/:id         — perfil + clientes
 * POST /api/v1/coaches/:id/customers — asignar cliente
 * GET  /api/v1/coaches/:id/programs — programas del coach
 * POST /api/v1/coaches/:id/programs — crear programa
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";

const CreateCoachSchema = z.object({
  userId: z.string().uuid().optional(),
  name: z.string().min(2),
  email: z.string().email(),
  bio: z.string().optional(),
  specialties: z.array(z.string()).optional(),
  instagramHandle: z.string().optional(),
  calendarUrl: z.string().url().optional(),
});

const CreateProgramSchema = z.object({
  name: z.string().min(2),
  description: z.string().optional(),
  durationWeeks: z.number().int().min(1).optional(),
  sessionFrequency: z.string().optional(),
  price: z.number().min(0).optional(),
  currency: z.string().default("ARS"),
  productIds: z.array(z.string().uuid()).optional(),
});

const AssignCustomerSchema = z.object({
  customerId: z.string().uuid(),
  programId: z.string().uuid().optional(),
  notes: z.string().optional(),
});

export async function coachRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  fastify.addHook("preHandler", fastify.authenticate);

  fastify.get(
    "/",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const coaches = await prisma.coach.findMany({
        where: { tenantId: request.tenantId! },
        include: {
          profile: true,
          _count: { select: { coachCustomers: true, programs: true } },
          user: { select: { id: true, name: true, email: true } },
        },
        orderBy: { createdAt: "desc" },
      });

      return reply.send({ data: coaches });
    }
  );

  fastify.post(
    "/",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateCoachSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const { userId, name, email, bio, specialties, instagramHandle, calendarUrl } = body.data;

      const coach = await prisma.$transaction(async (tx) => {
        const c = await tx.coach.create({
          data: {
            tenantId,
            name,
            email,
            active: true,
            ...(userId && { userId }),
          },
        });

        await tx.coachProfile.create({
          data: {
            coachId: c.id,
            bio,
            specialties: specialties ?? [],
            instagramHandle,
            calendarUrl,
          },
        });

        return c;
      });

      return reply.code(201).send({ data: coach });
    }
  );

  fastify.get(
    "/:id",
    { preHandler: [requireRole("SUPPORT")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const coach = await prisma.coach.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
        include: {
          profile: true,
          programs: true,
          coachCustomers: {
            include: {
              customer: { select: { id: true, name: true, email: true } },
              program: { select: { id: true, name: true } },
            },
          },
        },
      });

      if (!coach) return reply.code(404).send({ error: "Coach no encontrada" });
      return reply.send({ data: coach });
    }
  );

  fastify.post(
    "/:id/customers",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = AssignCustomerSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const coach = await prisma.coach.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!coach) return reply.code(404).send({ error: "Coach no encontrada" });

      const assignment = await prisma.coachCustomer.upsert({
        where: { coachId_customerId: { coachId: coach.id, customerId: body.data.customerId } },
        update: {
          programId: body.data.programId ?? null,
          notes: body.data.notes,
          active: true,
        },
        create: {
          coachId: coach.id,
          customerId: body.data.customerId,
          programId: body.data.programId ?? null,
          notes: body.data.notes,
          active: true,
        },
      });

      return reply.code(201).send({ data: assignment });
    }
  );

  fastify.get(
    "/:id/programs",
    { preHandler: [requireRole("SUPPORT")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const programs = await prisma.coachProgram.findMany({
        where: { coachId: request.params.id },
        orderBy: { createdAt: "desc" },
      });
      return reply.send({ data: programs });
    }
  );

  fastify.post(
    "/:id/programs",
    { preHandler: [requireRole("COACH")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = CreateProgramSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const coach = await prisma.coach.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!coach) return reply.code(404).send({ error: "Coach no encontrada" });

      // Solo la coach o MANAGER+ puede crear programas para esa coach
      const isOwnProfile = request.user.sub === coach.userId;
      const isManager = ["MANAGER", "TENANT_ADMIN", "SUPER_ADMIN"].includes(request.user.role);
      if (!isOwnProfile && !isManager) {
        return reply.code(403).send({ error: "Solo la coach o un manager puede crear sus programas" });
      }

      const program = await prisma.coachProgram.create({
        data: {
          coachId: coach.id,
          name: body.data.name,
          description: body.data.description,
          durationWeeks: body.data.durationWeeks,
          sessionFrequency: body.data.sessionFrequency,
          price: body.data.price,
          currency: body.data.currency,
          productIds: body.data.productIds ?? [],
          active: true,
        },
      });

      return reply.code(201).send({ data: program });
    }
  );
}
