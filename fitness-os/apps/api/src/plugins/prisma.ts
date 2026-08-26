/**
 * Fastify plugin — Prisma client.
 * Hace disponible `fastify.prisma` en toda la app.
 * Cierra la conexión gracefully al cerrar el servidor.
 */

import fp from "fastify-plugin";
import { prisma } from "@fitness-os/database";
import type { FastifyPluginAsync } from "fastify";
import type { PrismaClient } from "@fitness-os/database";

declare module "fastify" {
  interface FastifyInstance {
    prisma: PrismaClient;
  }
}

const prismaPlugin: FastifyPluginAsync = fp(async (server) => {
  await prisma.$connect();
  server.decorate("prisma", prisma);

  server.addHook("onClose", async () => {
    await prisma.$disconnect();
  });
});

export { prismaPlugin };
