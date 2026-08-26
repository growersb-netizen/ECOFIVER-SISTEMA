/**
 * Fase 03 — Rutas de Órdenes y Checkout.
 *
 * POST /api/v1/checkout/init     — iniciar checkout (pública)
 * POST /api/v1/checkout/coupon   — aplicar cupón
 * POST /api/v1/webhooks/mercadopago — webhook MP
 * GET  /api/v1/orders            — listar órdenes del tenant
 * GET  /api/v1/orders/:id        — detalle de orden
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { MercadoPagoAdapter } from "../adapters/mercadopago.js";
import { fulfillOrder } from "./fulfillment.js";

// ── Schemas ────────────────────────────────────────────────────────
const CheckoutInitSchema = z.object({
  items: z.array(z.object({
    productId: z.string().uuid(),
    quantity: z.number().int().min(1).default(1),
  })).min(1),
  couponCode: z.string().optional(),
  customer: z.object({
    email: z.string().email(),
    name: z.string().min(2).max(200),
    phone: z.string().optional(),
  }),
  successUrl: z.string().url().optional(),
  failureUrl: z.string().url().optional(),
});

const ApplyCouponSchema = z.object({
  code: z.string().min(1),
  productIds: z.array(z.string().uuid()),
  subtotal: z.number().min(0),
});

const ListOrdersQuerySchema = z.object({
  page: z.string().transform(Number).default("1"),
  pageSize: z.string().transform(Number).default("20"),
  status: z.string().optional(),
  customerId: z.string().optional(),
  from: z.string().optional(),
  to: z.string().optional(),
});

// ── Plugin ─────────────────────────────────────────────────────────
export async function orderRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;
  const mp = new MercadoPagoAdapter();

  /**
   * POST /checkout/init
   * Pública (el tenant se infiere del header X-Tenant-Slug).
   */
  fastify.post("/checkout/init", async (request: FastifyRequest, reply) => {
    const body = CheckoutInitSchema.safeParse(request.body);
    if (!body.success) return reply.code(400).send({ error: "Datos inválidos", details: body.error.flatten() });

    const tenantId = request.tenantId;
    if (!tenantId) return reply.code(400).send({ error: "Tenant requerido" });

    const { items, couponCode, customer, successUrl, failureUrl } = body.data;

    // Cargar productos con precios
    const productIds = items.map((i) => i.productId);
    const products = await prisma.product.findMany({
      where: { id: { in: productIds }, tenantId, status: "PUBLISHED" },
      include: { prices: { where: { channel: "WEB" } } },
    });

    if (products.length !== productIds.length) {
      return reply.code(422).send({ error: "Uno o más productos no están disponibles" });
    }

    // Calcular subtotal
    let subtotal = 0;
    const lineItems = items.map((item) => {
      const product = products.find((p) => p.id === item.productId)!;
      const price = product.prices[0];
      if (!price) throw new Error(`Producto ${product.name} sin precio WEB`);
      const unitPrice = price.promoPrice?.toNumber() ?? price.basePrice.toNumber();
      subtotal += unitPrice * item.quantity;
      return { product, price, quantity: item.quantity, unitPrice };
    });

    // Aplicar cupón si corresponde
    let discount = 0;
    let coupon = null;
    if (couponCode) {
      coupon = await prisma.coupon.findFirst({
        where: {
          tenantId,
          code: couponCode,
          active: true,
          OR: [{ validUntil: null }, { validUntil: { gt: new Date() } }],
        },
      });
      if (coupon) {
        if (coupon.discountPct) {
          discount = subtotal * (coupon.discountPct.toNumber() / 100);
        } else if (coupon.discountAmt) {
          discount = Math.min(coupon.discountAmt.toNumber(), subtotal);
        }
      }
    }

    const total = Math.max(0, subtotal - discount);

    // Buscar o crear customer
    const dbCustomer = await prisma.customer.upsert({
      where: { tenantId_email: { tenantId, email: customer.email } },
      update: { name: customer.name, phone: customer.phone },
      create: { tenantId, email: customer.email, name: customer.name, phone: customer.phone },
    });

    // Crear orden
    const order = await prisma.$transaction(async (tx) => {
      const o = await tx.order.create({
        data: {
          tenantId,
          customerId: dbCustomer.id,
          status: "PENDING_PAYMENT",
          currency: lineItems[0]?.price.currency ?? "ARS",
          subtotal,
          discount,
          total,
          couponId: coupon?.id ?? null,
          notes: null,
        },
      });

      await tx.orderItem.createMany({
        data: lineItems.map((li) => ({
          orderId: o.id,
          productId: li.product.id,
          productName: li.product.name,
          productSku: li.product.sku,
          quantity: li.quantity,
          unitPrice: li.unitPrice,
          total: li.unitPrice * li.quantity,
        })),
      });

      return o;
    });

    // Crear preferencia en Mercado Pago
    const baseUrl = process.env["APP_WEB_URL"] ?? "https://fitness-os.vercel.app";
    const preference = await mp.createPreference({
      items: lineItems.map((li) => ({
        id: li.product.sku,
        title: li.product.name,
        quantity: li.quantity,
        unit_price: li.unitPrice,
        currency_id: "ARS",
      })),
      payer: { email: customer.email, name: customer.name },
      external_reference: order.id,
      back_urls: {
        success: successUrl ?? `${baseUrl}/checkout/success?order=${order.id}`,
        failure: failureUrl ?? `${baseUrl}/checkout/failure?order=${order.id}`,
        pending: `${baseUrl}/checkout/pending?order=${order.id}`,
      },
      notification_url: `${process.env["API_URL"] ?? "https://fitness-os-api.railway.app"}/api/v1/webhooks/mercadopago`,
    });

    return reply.code(201).send({
      orderId: order.id,
      total,
      discount,
      subtotal,
      checkoutUrl: preference.init_point,
      preferenceId: preference.id,
    });
  });

  /**
   * POST /checkout/coupon — verificar cupón antes del pago
   */
  fastify.post("/checkout/coupon", async (request: FastifyRequest, reply) => {
    const body = ApplyCouponSchema.safeParse(request.body);
    if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

    const tenantId = request.tenantId;
    if (!tenantId) return reply.code(400).send({ error: "Tenant requerido" });

    const coupon = await prisma.coupon.findFirst({
      where: {
        tenantId,
        code: body.data.code,
        active: true,
        OR: [{ validUntil: null }, { validUntil: { gt: new Date() } }],
      },
    });

    if (!coupon) return reply.code(404).send({ error: "Cupón no válido o expirado" });

    const subtotal = body.data.subtotal;
    const discount = coupon.discountPct
      ? subtotal * (coupon.discountPct.toNumber() / 100)
      : coupon.discountAmt
        ? Math.min(coupon.discountAmt.toNumber(), subtotal)
        : 0;

    return reply.send({
      valid: true,
      discount,
      discountPct: coupon.discountPct,
      discountAmt: coupon.discountAmt,
      description: coupon.description,
    });
  });

  /**
   * POST /webhooks/mercadopago
   * Idempotente: externalId UNIQUE en Payment table.
   */
  fastify.post("/webhooks/mercadopago", async (request: FastifyRequest, reply) => {
    const body = request.body as { type?: string; data?: { id?: string } };
    if (body.type !== "payment" || !body.data?.id) {
      return reply.code(200).send({ ok: true }); // MP espera 200 siempre
    }

    const paymentId = String(body.data.id);

    // Idempotencia: si ya procesamos este pago, ignorar
    const existing = await prisma.payment.findUnique({ where: { externalId: paymentId } });
    if (existing) return reply.code(200).send({ ok: true, deduplicated: true });

    // Obtener detalles del pago desde MP
    const mpPayment = await mp.getPayment(paymentId);
    if (!mpPayment) return reply.code(200).send({ ok: true });

    const orderId = mpPayment.external_reference;
    if (!orderId) return reply.code(200).send({ ok: true });

    const order = await prisma.order.findUnique({ where: { id: orderId } });
    if (!order) return reply.code(200).send({ ok: true });

    const mpStatus = mpPayment.status; // "approved" | "rejected" | "pending"

    await prisma.$transaction(async (tx) => {
      // Registrar pago (UNIQUE en externalId previene duplicados)
      await tx.payment.create({
        data: {
          orderId: order.id,
          externalId: paymentId,
          provider: "MERCADOPAGO",
          status: mpStatus === "approved" ? "APPROVED" : mpStatus === "rejected" ? "REJECTED" : "PENDING",
          amount: order.total,
          currency: order.currency,
          rawData: mpPayment as never,
        },
      });

      if (mpStatus === "approved") {
        await tx.order.update({
          where: { id: order.id },
          data: { status: "PAID", paidAt: new Date() },
        });

        // Audit
        await tx.auditLog.create({
          data: {
            tenantId: order.tenantId,
            action: "ORDER_PAID",
            entity: "Order",
            entityId: order.id,
            after: { paymentId, amount: order.total.toNumber() },
          },
        });

        await tx.order.update({
          where: { id: order.id },
          data: { status: "READY_FOR_FULFILLMENT" },
        });
      }
    });

    // Fulfillment inline — fuera de la transacción para no bloquear el webhook
    if (mpStatus === "approved") {
      fulfillOrder(order.id, prisma).catch((err: unknown) => {
        fastify.log.error({ err, orderId: order.id }, "Error en fulfillment inline");
      });
    }

    return reply.code(200).send({ ok: true });
  });

  /**
   * GET /orders — listado (requiere autenticación)
   */
  fastify.get(
    "/orders",
    { preHandler: [fastify.authenticate, requireRole("SALES")] },
    async (request: FastifyRequest, reply) => {
      const query = ListOrdersQuerySchema.safeParse(request.query);
      if (!query.success) return reply.code(400).send({ error: "Parámetros inválidos" });

      const { page, pageSize, status, customerId, from, to } = query.data;
      const skip = (Math.max(1, page) - 1) * Math.min(100, pageSize);

      const where = {
        tenantId: request.tenantId!,
        ...(status && { status: status as never }),
        ...(customerId && { customerId }),
        ...(from || to ? {
          createdAt: {
            ...(from && { gte: new Date(from) }),
            ...(to && { lte: new Date(to) }),
          },
        } : {}),
      };

      const [total, items] = await Promise.all([
        prisma.order.count({ where }),
        prisma.order.findMany({
          where,
          skip,
          take: Math.min(100, pageSize),
          orderBy: { createdAt: "desc" },
          include: {
            customer: { select: { id: true, email: true, name: true } },
            items: { include: { product: { select: { id: true, name: true, sku: true } } } },
            payments: { select: { id: true, status: true, amount: true, externalId: true } },
          },
        }),
      ]);

      return reply.send({
        data: items,
        pagination: { page, pageSize, total, totalPages: Math.ceil(total / pageSize) },
      });
    }
  );

  /**
   * GET /orders/my-purchases?email=&orderId=
   * Pública — usa X-Tenant-Slug para resolver el tenant.
   * Devuelve órdenes PAID/DELIVERED del cliente con links de descarga.
   */
  fastify.get("/orders/my-purchases", async (request: FastifyRequest, reply) => {
    const { email, orderId } = request.query as { email?: string; orderId?: string };

    if (!email || !email.includes("@")) {
      return reply.code(400).send({ error: "Email válido requerido" });
    }

    const tenantId = request.tenantId;
    if (!tenantId) return reply.code(400).send({ error: "Tenant requerido" });

    // Buscar customer por email en este tenant
    const customer = await prisma.customer.findFirst({
      where: { tenantId, email: email.toLowerCase().trim() },
    });

    if (!customer) return reply.send({ data: [] });

    const where = {
      tenantId,
      customerId: customer.id,
      status: { in: ["PAID", "DELIVERED", "READY_FOR_FULFILLMENT"] as never[] },
      ...(orderId ? { id: orderId } : {}),
    };

    const orders = await prisma.order.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: 50,
      include: {
        items: {
          include: {
            product: { select: { id: true, name: true, sku: true } },
          },
        },
        deliveries: {
          select: { id: true, productId: true, downloadUrl: true, downloadExpiresAt: true },
        },
      },
    });

    const result = orders.map((o) => ({
      id: o.id,
      status: o.status,
      totalAmount: o.total.toNumber(),
      currency: o.currency,
      createdAt: o.createdAt.toISOString(),
      items: o.items.map((item) => {
        // Buscar la entrega correspondiente a este producto
        const delivery = o.deliveries.find((d) => d.productId === item.productId);
        const downloadExpired =
          delivery?.downloadExpiresAt && new Date() > new Date(delivery.downloadExpiresAt);
        return {
          productName: item.productName,
          productSku: item.productSku,
          downloadUrl: delivery && !downloadExpired ? delivery.downloadUrl ?? undefined : undefined,
        };
      }),
    }));

    return reply.send({ data: result });
  });

  /**
   * GET /orders/:id
   */
  fastify.get(
    "/orders/:id",
    { preHandler: [fastify.authenticate, requireRole("SALES")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const order = await prisma.order.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
        include: {
          customer: true,
          items: { include: { product: true } },
          payments: true,
          deliveries: true,
          coupon: { select: { code: true, discountPct: true, discountAmt: true } },
        },
      });

      if (!order) return reply.code(404).send({ error: "Orden no encontrada" });
      return reply.send({ data: order });
    }
  );

  /**
   * POST /orders/:id/simulate-payment
   * SOLO SANDBOX/TESTING — simula un pago aprobado sin MercadoPago.
   * Solo disponible si NODE_ENV !== "production" OR SANDBOX_MODE=true.
   */
  fastify.post(
    "/orders/:id/simulate-payment",
    { preHandler: [fastify.authenticate, requireRole("TENANT_ADMIN")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const sandboxEnabled = process.env["SANDBOX_MODE"] === "true" || process.env["NODE_ENV"] !== "production";
      if (!sandboxEnabled) {
        return reply.code(403).send({ error: "simulate-payment solo disponible en sandbox" });
      }

      const order = await prisma.order.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!order) return reply.code(404).send({ error: "Orden no encontrada" });
      if (order.status === "DELIVERED") return reply.send({ ok: true, message: "Orden ya entregada" });

      // Simular pago
      await prisma.$transaction(async (tx) => {
        await tx.payment.create({
          data: {
            orderId: order.id,
            externalId: `SANDBOX_${Date.now()}`,
            provider: "MERCADOPAGO",
            status: "APPROVED",
            amount: order.total,
            currency: order.currency,
            rawData: { simulated: true, ts: new Date().toISOString() } as never,
          },
        });
        await tx.order.update({
          where: { id: order.id },
          data: { status: "PAID", paidAt: new Date() },
        });
      });

      // Fulfillment inline
      await fulfillOrder(order.id, prisma);

      return reply.send({ ok: true, message: "Pago simulado y producto entregado", orderId: order.id });
    }
  );
}
