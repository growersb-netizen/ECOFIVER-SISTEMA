/**
 * GET /api/v1/stats/overview — KPIs del dashboard admin.
 * Requiere autenticación (tenantId viene del JWT).
 */
import { FastifyInstance, FastifyRequest } from "fastify";

export async function statsRoutes(fastify: FastifyInstance) {
  fastify.get(
    "/overview",
    { preHandler: [fastify.authenticate] },
    async (request: FastifyRequest, reply) => {
      const tenantId = request.user.tenantId;
      const prisma = fastify.prisma;

      const now = new Date();
      const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
      const startOfWeek = new Date(now);
      startOfWeek.setDate(now.getDate() - 7);

      const [
        totalProducts,
        publishedProducts,
        totalOrders,
        pendingOrders,
        revenueResult,
        totalLeads,
        newLeads,
        totalCustomers,
        recentOrders,
      ] = await Promise.all([
        prisma.product.count({ where: { tenantId } }),
        prisma.product.count({ where: { tenantId, status: "PUBLISHED" } }),
        prisma.order.count({ where: { tenantId } }),
        prisma.order.count({ where: { tenantId, status: "PENDING" } }),
        prisma.order.aggregate({
          where: { tenantId, status: { in: ["PAID", "DELIVERED"] } },
          _sum: { totalAmount: true },
        }),
        prisma.lead.count({ where: { tenantId } }),
        prisma.lead.count({ where: { tenantId, createdAt: { gte: startOfWeek } } }),
        prisma.customer.count({ where: { tenantId } }),
        prisma.order.findMany({
          where: { tenantId },
          orderBy: { createdAt: "desc" },
          take: 5,
          select: {
            id: true,
            status: true,
            totalAmount: true,
            currency: true,
            createdAt: true,
            customer: { select: { name: true, email: true } },
          },
        }),
      ]);

      return reply.send({
        data: {
          totalProducts,
          publishedProducts,
          totalOrders,
          pendingOrders,
          totalRevenue: Number(revenueResult._sum.totalAmount ?? 0),
          totalLeads,
          newLeads,
          totalCustomers,
          recentOrders,
          updatedAt: now.toISOString(),
        },
      });
    }
  );
}
