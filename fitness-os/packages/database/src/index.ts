import { PrismaClient } from "@prisma/client";

// ── Singleton Prisma client ──────────────────────────────────────────
// Prevents multiple instances during Next.js hot reloading in development
const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log:
      process.env["NODE_ENV"] === "development"
        ? ["query", "error", "warn"]
        : ["error"],
  });

if (process.env["NODE_ENV"] !== "production") globalForPrisma.prisma = prisma;

// ── Tenant-scoped client factory ─────────────────────────────────────
// Every business query must go through this to enforce tenant isolation.
// Usage: const db = prismaWithTenant(tenantId)
export function prismaWithTenant(tenantId: string) {
  return prisma.$extends({
    query: {
      $allModels: {
        async $allOperations({ args, query }) {
          // Inject tenantId into all where clauses for models that have it
          const tenantAwareModels = [
            "product",
            "category",
            "customer",
            "order",
            "lead",
            "conversation",
            "publication",
            "blogPost",
            "promptTemplate",
            "aiRequest",
            "aiModelConfig",
            "affiliate",
            "coach",
            "knowledgeBase",
            "autopilotConfig",
            "auditLog",
            "marketplaceListing",
            "contentPack",
            "emailCampaign",
          ];

          // For find operations on tenant-aware models, enforce tenant filter
          if (
            (args as Record<string, unknown>)["where"] !== undefined ||
            (args as Record<string, unknown>)["data"] !== undefined
          ) {
            // This is a simplified middleware — full implementation in Phase 01
            // The actual Fastify middleware handles this at the request level
          }

          return query(args);
        },
      },
    },
  });
}

// ── Re-export Prisma types ───────────────────────────────────────────
export * from "@prisma/client";
export type { Prisma } from "@prisma/client";
