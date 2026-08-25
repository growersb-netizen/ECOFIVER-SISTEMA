/**
 * Fastify app factory — Fases 00-13.
 * Registra plugins, middlewares y todas las rutas de la plataforma.
 */

import Fastify from "fastify";
import cors from "@fastify/cors";
import helmet from "@fastify/helmet";
import rateLimit from "@fastify/rate-limit";

import { prismaPlugin } from "./plugins/prisma.js";
import { jwtPlugin } from "./plugins/jwt.js";
import { registerSecurityHooks, getSecurityHeaders } from "./middleware/security.js";
import { healthRoutes } from "./routes/health.js";
import { authRoutes } from "./routes/auth.js";
import { productRoutes } from "./routes/products.js";
import { categoryRoutes } from "./routes/categories.js";
import { orderRoutes } from "./routes/orders.js";
import { aiRoutes } from "./routes/ai.js";
import { crmRoutes } from "./routes/crm.js";
import { whatsappRoutes } from "./routes/whatsapp.js";
import { mercadolibreRoutes } from "./routes/mercadolibre.js";
import { socialRoutes } from "./routes/social.js";
import { affiliateRoutes } from "./routes/affiliates.js";
import { coachRoutes } from "./routes/coaches.js";
import { blogRoutes } from "./routes/blog.js";
import { tenantMiddleware } from "./middleware/tenant.js";

const ADMIN_URL = process.env["APP_ADMIN_URL"] ?? "http://localhost:3000";
const WEB_URL = process.env["APP_WEB_URL"] ?? "http://localhost:3002";

export async function buildApp() {
  const app = Fastify({
    logger: {
      level: process.env["LOG_LEVEL"] ?? "info",
      transport:
        process.env["NODE_ENV"] === "development"
          ? { target: "pino-pretty", options: { colorize: true } }
          : undefined,
    },
  });

  // ── Seguridad ──────────────────────────────────────────────────
  await app.register(helmet, {
    contentSecurityPolicy: false,
  });

  // Rate limiting por defecto: 100 req/min
  // Rutas de webhooks tienen rate limit más generoso (configurado por ruta)
  await app.register(rateLimit, {
    max: 100,
    timeWindow: "1 minute",
    errorResponseBuilder: () => ({
      ok: false,
      error: { code: "RATE_LIMIT", message: "Demasiadas solicitudes. Intentá en un momento." },
    }),
  });

  // ── CORS ───────────────────────────────────────────────────────
  await app.register(cors, {
    origin: [ADMIN_URL, WEB_URL],
    credentials: true,
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization", "X-Tenant-Slug"],
  });

  // ── Plugins internos ───────────────────────────────────────────
  await app.register(prismaPlugin);
  await app.register(jwtPlugin);

  // ── Security hooks (Fase 15) ───────────────────────────────────
  registerSecurityHooks(app);

  // Agregar headers de seguridad adicionales a todas las respuestas
  app.addHook("onSend", (_request, reply, payload, done) => {
    const headers = getSecurityHeaders();
    for (const [k, v] of Object.entries(headers)) reply.header(k, v);
    done(null, payload);
  });

  // ── Middleware global de tenant ────────────────────────────────
  app.addHook("onRequest", tenantMiddleware);

  // ── Rutas públicas ─────────────────────────────────────────────
  await app.register(healthRoutes, { prefix: "/api/v1" });

  // Auth (login, register, refresh, logout, me)
  await app.register(
    async (fastify) => { await fastify.register(authRoutes); },
    { prefix: "/api/v1/auth" }
  );

  // Redirect de afiliadas (pública, no requiere auth)
  await app.register(
    async (fastify) => { await fastify.register(affiliateRoutes); },
    { prefix: "/api/v1/affiliates" }
  );

  // ── Webhooks (no requieren auth pero sí firma del proveedor) ───
  await app.register(
    async (fastify) => {
      await fastify.register(
        async (inner) => {
          await inner.register(orderRoutes);
          await inner.register(mercadolibreRoutes);
          await inner.register(whatsappRoutes);
        }
      );
    },
    { prefix: "/api/v1" }
  );

  // ── Rutas autenticadas ─────────────────────────────────────────
  await app.register(
    async (fastify) => { await fastify.register(categoryRoutes); },
    { prefix: "/api/v1/categories" }
  );

  await app.register(
    async (fastify) => { await fastify.register(productRoutes); },
    { prefix: "/api/v1/products" }
  );

  await app.register(
    async (fastify) => { await fastify.register(aiRoutes); },
    { prefix: "/api/v1/ai" }
  );

  await app.register(
    async (fastify) => { await fastify.register(crmRoutes); },
    { prefix: "/api/v1/crm" }
  );

  await app.register(
    async (fastify) => { await fastify.register(socialRoutes); },
    { prefix: "/api/v1/social" }
  );

  await app.register(
    async (fastify) => { await fastify.register(coachRoutes); },
    { prefix: "/api/v1/coaches" }
  );

  // Blog + Email routes registradas juntas (blogRoutes maneja ambos prefijos internamente)
  await app.register(
    async (fastify) => { await fastify.register(blogRoutes); },
    { prefix: "/api/v1" }
  );

  // ── 404 handler ────────────────────────────────────────────────
  app.setNotFoundHandler((request, reply) => {
    reply.status(404).send({
      ok: false,
      error: { code: "NOT_FOUND", message: `Ruta no encontrada: ${request.url}` },
    });
  });

  // ── Error handler ──────────────────────────────────────────────
  app.setErrorHandler((error, request, reply) => {
    app.log.error({ err: error, url: request.url }, "Error no manejado");

    const statusCode = error.statusCode ?? 500;
    reply.status(statusCode).send({
      ok: false,
      error: {
        code: error.code ?? "INTERNAL_ERROR",
        message:
          process.env["NODE_ENV"] === "production"
            ? "Error interno del servidor"
            : error.message,
      },
    });
  });

  return app;
}
