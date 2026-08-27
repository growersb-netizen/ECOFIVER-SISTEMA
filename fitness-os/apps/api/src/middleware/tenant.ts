/**
 * Middleware de Tenant — Fase 01.
 *
 * Extrae el tenantId de tres fuentes (en orden de prioridad):
 * 1. JWT: request.user.tenantId (si el token ya fue verificado)
 * 2. Header X-Tenant-Slug: busca el tenant en DB
 * 3. Query param ?tenant=slug: para webhooks y redirects
 *
 * Rutas públicas que no requieren tenant:
 * - /api/v1/health
 * - /api/v1/auth/login
 * - /api/v1/auth/register
 * - /api/v1/public/** (afiliadas redirect)
 */

import { FastifyRequest, FastifyReply } from "fastify";
import { PrismaClient } from "@prisma/client";

// Paths que no requieren tenant
const PUBLIC_PATHS = [
  "/api/v1/health",
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/refresh",
  "/api/v1/webhooks/",
  "/api/v1/public/",
  "/api/v1/affiliates/public/",
  "/api/v1/ml/auth/",
];

function isPublicPath(url: string): boolean {
  return PUBLIC_PATHS.some((p) => url.startsWith(p));
}

// Caché simple en memoria para slugs de tenants (evita queries repetidas)
const tenantCache = new Map<string, string>(); // slug → id

export async function tenantMiddleware(request: FastifyRequest, _reply: FastifyReply): Promise<void> {
  if (isPublicPath(request.url)) return;

  // 1. Si el JWT ya fue verificado y tiene tenantId, usarlo (rutas que ya procesaron auth)
  if (request.user?.tenantId) {
    request.tenantId = request.user.tenantId;
    request.userId = request.user.sub;
    return;
  }

  // 1b. Intentar verificar JWT manualmente si hay Bearer token (para rutas autenticadas
  //     donde el middleware corre antes que el preHandler authenticate)
  const authHeader = request.headers["authorization"];
  if (authHeader?.startsWith("Bearer ")) {
    try {
      const token = authHeader.slice(7);
      const jwt = (request.server as { jwt?: { verify: (t: string) => { sub: string; tenantId: string } } }).jwt;
      if (jwt) {
        const payload = jwt.verify(token) as { sub: string; tenantId: string };
        if (payload?.tenantId) {
          request.tenantId = payload.tenantId;
          request.userId = payload.sub;
          return;
        }
      }
    } catch {
      // Token inválido — el preHandler authenticate lo rechazará después
    }
  }

  // 2. Header X-Tenant-Slug
  const slug = (request.headers["x-tenant-slug"] as string)
    ?? (request.query as Record<string, string>)["tenant"];

  if (slug) {
    // Cache hit
    if (tenantCache.has(slug)) {
      request.tenantId = tenantCache.get(slug)!;
      return;
    }

    // Cache miss: buscar en DB
    try {
      // Necesitamos acceder a prisma — está disponible en el servidor Fastify
      const server = request.server as { prisma?: PrismaClient };
      if (server.prisma) {
        const tenant = await server.prisma.tenant.findUnique({
          where: { slug },
          select: { id: true, active: true },
        });
        if (tenant?.active) {
          tenantCache.set(slug, tenant.id);
          request.tenantId = tenant.id;
        }
      }
    } catch {
      // Silenciar error — no todos los requests necesitan tenant
    }
  }
}

declare module "fastify" {
  interface FastifyRequest {
    tenantId?: string;
    userId?: string;
  }
}
