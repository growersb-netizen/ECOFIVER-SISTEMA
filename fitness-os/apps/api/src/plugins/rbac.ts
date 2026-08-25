/**
 * Fase 01 — RBAC (Role-Based Access Control).
 * 9 roles jerárquicos según la especificación.
 *
 * Jerarquía (de mayor a menor):
 * SUPER_ADMIN > TENANT_ADMIN > MANAGER > CONTENT_MANAGER > SALES > SUPPORT > COACH > AFFILIATE > CUSTOMER
 */

import { FastifyRequest, FastifyReply } from "fastify";

export type UserRole =
  | "SUPER_ADMIN"
  | "TENANT_ADMIN"
  | "MANAGER"
  | "CONTENT_MANAGER"
  | "SALES"
  | "SUPPORT"
  | "COACH"
  | "AFFILIATE"
  | "CUSTOMER";

// Nivel numérico por rol — más alto = más permisos
const ROLE_LEVELS: Record<UserRole, number> = {
  SUPER_ADMIN:      900,
  TENANT_ADMIN:     800,
  MANAGER:          700,
  CONTENT_MANAGER:  600,
  SALES:            500,
  SUPPORT:          400,
  COACH:            300,
  AFFILIATE:        200,
  CUSTOMER:         100,
};

export function hasRole(userRole: string, requiredRole: UserRole): boolean {
  const userLevel = ROLE_LEVELS[userRole as UserRole] ?? 0;
  const requiredLevel = ROLE_LEVELS[requiredRole] ?? 999;
  return userLevel >= requiredLevel;
}

/**
 * Factory que devuelve un hook de preHandler que verifica el rol mínimo.
 *
 * Uso:
 *   fastify.get("/admin/products", { preHandler: [fastify.authenticate, requireRole("MANAGER")] }, handler)
 */
export function requireRole(minRole: UserRole) {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    const userRole = request.user?.role;
    if (!userRole || !hasRole(userRole, minRole)) {
      reply.code(403).send({
        error: "Acceso denegado",
        message: `Se requiere el rol ${minRole} o superior`,
      });
    }
  };
}

/**
 * Verifica que el usuario solo acceda a recursos de su propio tenant
 * (excepto SUPER_ADMIN, que puede ver todos).
 */
export function requireOwnTenant() {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    if (request.user?.role === "SUPER_ADMIN") return;
    if (request.user?.tenantId !== request.tenantId) {
      reply.code(403).send({ error: "Acceso denegado: tenant incorrecto" });
    }
  };
}

// Aliases semánticos frecuentes
export const requireAdmin = requireRole("TENANT_ADMIN");
export const requireManager = requireRole("MANAGER");
export const requireContent = requireRole("CONTENT_MANAGER");
export const requireSales = requireRole("SALES");
export const requireSupport = requireRole("SUPPORT");
