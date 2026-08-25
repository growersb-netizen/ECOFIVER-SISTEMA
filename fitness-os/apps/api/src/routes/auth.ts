/**
 * Fase 01 — Rutas de autenticación.
 * POST /api/v1/auth/register
 * POST /api/v1/auth/login
 * POST /api/v1/auth/refresh
 * POST /api/v1/auth/logout
 * GET  /api/v1/auth/me
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { hash, compare } from "argon2";

// ── Schemas ────────────────────────────────────────────────────────
const RegisterSchema = z.object({
  tenantSlug: z.string().min(3).max(50).regex(/^[a-z0-9-]+$/),
  tenantName: z.string().min(2).max(100),
  email: z.string().email(),
  password: z.string().min(8).max(128),
  name: z.string().min(2).max(100),
});

const LoginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
  tenantSlug: z.string().optional(),
});

const RefreshSchema = z.object({
  refreshToken: z.string().min(1),
});

// ── Helpers ────────────────────────────────────────────────────────
function signTokens(fastify: FastifyInstance, payload: { sub: string; tenantId: string; role: string }) {
  const access = fastify.jwt.sign(
    { ...payload, type: "access" },
    { expiresIn: "15m" }
  );
  const refresh = fastify.jwt.sign(
    { ...payload, type: "refresh" },
    { expiresIn: "30d" }
  );
  return { access, refresh };
}

// ── Plugin ─────────────────────────────────────────────────────────
export async function authRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  /**
   * POST /register
   * Crea tenant + brand + usuario TENANT_ADMIN.
   * Solo para onboarding inicial. Fases posteriores añaden invitaciones.
   */
  fastify.post("/register", async (request, reply) => {
    const body = RegisterSchema.safeParse(request.body);
    if (!body.success) {
      return reply.code(400).send({ error: "Datos inválidos", details: body.error.flatten() });
    }

    const { tenantSlug, tenantName, email, password, name } = body.data;

    // Verificar que el slug no exista
    const existing = await prisma.tenant.findUnique({ where: { slug: tenantSlug } });
    if (existing) {
      return reply.code(409).send({ error: "El slug del tenant ya existe" });
    }

    const passwordHash = await hash(password);

    const tenant = await prisma.$transaction(async (tx) => {
      const t = await tx.tenant.create({
        data: { slug: tenantSlug, name: tenantName, active: true },
      });

      await tx.brand.create({
        data: {
          tenantId: t.id,
          name: tenantName,
          primaryColor: "#00FF87",
          secondaryColor: "#00F5FF",
          accentColor: "#FF2D9C",
          welcomeMessage: "¡Bienvenida! Tu compra ya está lista en tu biblioteca.",
          thankYouMessage: "Gracias por confiar en nosotras.",
          postSaleMessage: "¿Dudas? Escribinos por WhatsApp, estamos para ayudarte.",
        },
      });

      await tx.user.create({
        data: {
          tenantId: t.id,
          email,
          name,
          passwordHash,
          role: "TENANT_ADMIN",
          active: true,
          emailVerified: new Date(),
        },
      });

      return t;
    });

    return reply.code(201).send({ message: "Tenant creado exitosamente", tenantId: tenant.id });
  });

  /**
   * POST /login
   */
  fastify.post("/login", async (request, reply) => {
    const body = LoginSchema.safeParse(request.body);
    if (!body.success) {
      return reply.code(400).send({ error: "Datos inválidos" });
    }

    const { email, password, tenantSlug } = body.data;

    // Buscar usuario (opcionalmente filtrando por tenant)
    const whereClause = tenantSlug
      ? { email, tenant: { slug: tenantSlug } }
      : undefined;

    const user = await prisma.user.findFirst({
      where: whereClause ?? { email },
      include: { tenant: { select: { id: true, slug: true, name: true, active: true } } },
    });

    if (!user || !user.active || !user.tenant.active) {
      return reply.code(401).send({ error: "Credenciales inválidas" });
    }

    const validPassword = await compare(user.passwordHash ?? "", password);
    if (!validPassword) {
      return reply.code(401).send({ error: "Credenciales inválidas" });
    }

    const { access, refresh } = signTokens(fastify, {
      sub: user.id,
      tenantId: user.tenantId,
      role: user.role,
    });

    // Guardar sesión
    const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    await prisma.session.create({
      data: {
        userId: user.id,
        token: refresh,
        expiresAt,
      },
    });

    // Audit log
    await prisma.auditLog.create({
      data: {
        tenantId: user.tenantId,
        userId: user.id,
        action: "AUTH_LOGIN",
        entity: "User",
        entityId: user.id,
        ip: request.ip,
        userAgent: request.headers["user-agent"] ?? null,
      },
    });

    return reply.send({
      accessToken: access,
      refreshToken: refresh,
      expiresIn: 900, // 15 min en segundos
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        tenant: {
          id: user.tenant.id,
          slug: user.tenant.slug,
          name: user.tenant.name,
        },
      },
    });
  });

  /**
   * POST /refresh
   */
  fastify.post("/refresh", async (request, reply) => {
    const body = RefreshSchema.safeParse(request.body);
    if (!body.success) {
      return reply.code(400).send({ error: "Token requerido" });
    }

    let payload: { sub: string; tenantId: string; role: string; type: string };
    try {
      payload = fastify.jwt.verify(body.data.refreshToken) as typeof payload;
    } catch {
      return reply.code(401).send({ error: "Token inválido o expirado" });
    }

    if (payload.type !== "refresh") {
      return reply.code(401).send({ error: "Token de refresco requerido" });
    }

    // Verificar que la sesión exista y no esté expirada
    const session = await prisma.session.findFirst({
      where: {
        token: body.data.refreshToken,
        expiresAt: { gt: new Date() },
      },
    });

    if (!session) {
      return reply.code(401).send({ error: "Sesión inválida o expirada" });
    }

    const { access, refresh } = signTokens(fastify, {
      sub: payload.sub,
      tenantId: payload.tenantId,
      role: payload.role,
    });

    // Rotar refresh token
    const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    await prisma.session.update({
      where: { id: session.id },
      data: { token: refresh, expiresAt },
    });

    return reply.send({ accessToken: access, refreshToken: refresh, expiresIn: 900 });
  });

  /**
   * POST /logout
   */
  fastify.post(
    "/logout",
    { preHandler: [fastify.authenticate] },
    async (request: FastifyRequest, reply) => {
      const body = RefreshSchema.safeParse(request.body);
      if (body.success) {
        await prisma.session.deleteMany({ where: { token: body.data.refreshToken } });
      }
      return reply.send({ message: "Sesión cerrada" });
    }
  );

  /**
   * GET /me
   */
  fastify.get(
    "/me",
    { preHandler: [fastify.authenticate] },
    async (request: FastifyRequest, reply) => {
      const user = await prisma.user.findUnique({
        where: { id: request.user.sub },
        select: {
          id: true,
          email: true,
          name: true,
          role: true,
          avatar: true,
          active: true,
          createdAt: true,
          tenant: { select: { id: true, slug: true, name: true } },
        },
      });

      if (!user) return reply.code(404).send({ error: "Usuario no encontrado" });

      return reply.send({ user });
    }
  );
}
