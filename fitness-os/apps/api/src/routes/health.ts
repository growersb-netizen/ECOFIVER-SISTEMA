/**
 * Health check y status del sistema.
 * Útil para Railway health probes y monitoreo.
 */

import type { FastifyPluginAsync } from "fastify";

export const healthRoutes: FastifyPluginAsync = async (app) => {
  // GET /api/v1/health
  app.get("/health", async (request, reply) => {
    // Verificar conexión a DB
    let dbStatus: "ok" | "error" = "ok";
    try {
      await app.prisma.$queryRaw`SELECT 1`;
    } catch {
      dbStatus = "error";
    }

    const status = dbStatus === "ok" ? "ok" : "degraded";
    const httpStatus = status === "ok" ? 200 : 503;

    return reply.status(httpStatus).send({
      ok: status === "ok",
      status,
      version: process.env["npm_package_version"] ?? "0.1.0",
      timestamp: new Date().toISOString(),
      services: {
        api: "ok",
        database: dbStatus,
      },
    });
  });

  // GET /api/v1/health/ready
  app.get("/health/ready", async (_request, reply) => {
    return reply.send({ ok: true, ready: true });
  });
};
