/**
 * Fase 01 — Plugin JWT para Fastify.
 * Access token: 15 min · Refresh token: 30 días.
 */

import fp from "fastify-plugin";
import { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import jwt from "@fastify/jwt";

declare module "@fastify/jwt" {
  interface FastifyJWT {
    payload: {
      sub: string;       // userId
      tenantId: string;
      role: string;
      type: "access" | "refresh";
    };
    user: {
      sub: string;
      tenantId: string;
      role: string;
      type: "access" | "refresh";
    };
  }
}

declare module "fastify" {
  interface FastifyInstance {
    authenticate: (request: FastifyRequest, reply: FastifyReply) => Promise<void>;
    authenticateOptional: (request: FastifyRequest, reply: FastifyReply) => Promise<void>;
  }
}

export const jwtPlugin = fp(async (fastify: FastifyInstance) => {
  const secret = process.env["AUTH_SECRET"];
  if (!secret || secret.length < 32) {
    throw new Error("AUTH_SECRET debe tener al menos 32 caracteres");
  }

  await fastify.register(jwt, {
    secret,
    sign: { expiresIn: "15m" },
  });

  // Decorador: requiere token válido
  fastify.decorate("authenticate", async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      await request.jwtVerify();
      if (request.user.type !== "access") {
        reply.code(401).send({ error: "Token de acceso requerido" });
        return;
      }
    } catch {
      reply.code(401).send({ error: "No autorizado" });
    }
  });

  // Decorador: autenticación opcional (para rutas públicas con contenido personalizable)
  fastify.decorate("authenticateOptional", async (request: FastifyRequest, _reply: FastifyReply) => {
    try {
      await request.jwtVerify();
    } catch {
      // Sin token — continúa como usuario anónimo
    }
  });
});
