/**
 * Fase 04 — Fulfillment de Productos Digitales.
 *
 * Responsabilidades:
 * - fulfillOrder(orderId): crea Delivery records + genera download URLs
 * - GET /deliveries/download/:token — endpoint seguro de descarga (redirige a R2 o sirve fallback)
 *
 * Sin R2: genera URLs con token firmado en DB (válido 72h) que redirigen a este endpoint.
 * Con R2: genera URLs firmadas S3 directamente.
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { PrismaClient } from "@prisma/client";
import { R2StorageAdapter } from "../adapters/storage.js";
import { createHash, randomBytes } from "crypto";

const DOWNLOAD_TTL_HOURS = 72;
const API_BASE = process.env["API_URL"] ?? "https://fitness-api-production-fff4.up.railway.app";

// ── R2 availability ────────────────────────────────────────────────

function r2Available(): boolean {
  return !!(
    process.env["CLOUDFLARE_ACCOUNT_ID"] &&
    process.env["R2_ACCESS_KEY_ID"] &&
    process.env["R2_SECRET_ACCESS_KEY"]
  );
}

// ── Generar token de descarga ──────────────────────────────────────

function generateDownloadToken(orderId: string, productId: string): string {
  const secret = process.env["JWT_SECRET"] ?? "default-secret";
  const nonce = randomBytes(8).toString("hex");
  const data = `${orderId}:${productId}:${nonce}:${Date.now()}`;
  const hash = createHash("sha256").update(`${data}:${secret}`).digest("hex").slice(0, 32);
  return Buffer.from(JSON.stringify({ orderId, productId, hash, nonce, ts: Date.now() })).toString("base64url");
}

function verifyDownloadToken(token: string): { orderId: string; productId: string } | null {
  try {
    const decoded = JSON.parse(Buffer.from(token, "base64url").toString()) as {
      orderId: string; productId: string; hash: string; nonce: string; ts: number;
    };
    const secret = process.env["JWT_SECRET"] ?? "default-secret";
    const data = `${decoded.orderId}:${decoded.productId}:${decoded.nonce}:${decoded.ts}`;
    const expected = createHash("sha256").update(`${data}:${secret}`).digest("hex").slice(0, 32);
    if (decoded.hash !== expected) return null;
    // Verificar TTL
    const ageHours = (Date.now() - decoded.ts) / (1000 * 60 * 60);
    if (ageHours > DOWNLOAD_TTL_HOURS) return null;
    return { orderId: decoded.orderId, productId: decoded.productId };
  } catch {
    return null;
  }
}

// ── Core fulfillment ───────────────────────────────────────────────

export async function fulfillOrder(orderId: string, prisma: PrismaClient): Promise<void> {
  const order = await prisma.order.findUnique({
    where: { id: orderId },
    include: {
      items: {
        include: {
          product: {
            include: {
              files: { where: { isPrimary: true }, take: 1 },
            },
          },
        },
      },
      customer: true,
    },
  });

  if (!order) return;

  const r2 = r2Available() ? new R2StorageAdapter() : null;

  for (const item of order.items) {
    // Verificar si ya existe una entrega para este item (idempotencia)
    const existing = await prisma.delivery.findUnique({
      where: { idempotencyKey: `${order.id}:${item.productId}` },
    });
    if (existing) continue;

    // Generar URL de descarga
    let downloadUrl: string;
    let storageKey: string | undefined;

    const productFile = item.product.files[0];

    if (r2 && productFile?.storageKey) {
      // R2 disponible: URL firmada con TTL de 72h
      try {
        downloadUrl = await r2.getSignedDownloadUrl(productFile.storageKey, DOWNLOAD_TTL_HOURS * 3600);
        storageKey = productFile.storageKey;
      } catch {
        // Fallback a token interno
        const token = generateDownloadToken(order.id, item.productId);
        downloadUrl = `${API_BASE}/api/v1/deliveries/download/${token}`;
      }
    } else {
      // Sin R2: URL de descarga vía endpoint interno (con token firmado)
      const token = generateDownloadToken(order.id, item.productId);
      downloadUrl = `${API_BASE}/api/v1/deliveries/download/${token}`;
    }

    const expiresAt = new Date(Date.now() + DOWNLOAD_TTL_HOURS * 60 * 60 * 1000);

    // Crear Delivery record (idempotencyKey = orderId:productId)
    await prisma.delivery.create({
      data: {
        tenantId: order.tenantId,
        orderId: order.id,
        productId: item.productId,
        customerId: order.customerId ?? undefined,
        idempotencyKey: `${order.id}:${item.productId}`,
        status: "DELIVERED",
        downloadUrl,
        downloadExpiresAt: expiresAt,
        ...(storageKey && { packageKey: storageKey }),
        deliveredAt: new Date(),
      },
    });
  }

  // Marcar orden como entregada
  await prisma.order.update({
    where: { id: orderId },
    data: { status: "DELIVERED" },
  });
}

// ── Routes ─────────────────────────────────────────────────────────

export async function fulfillmentRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  /**
   * GET /deliveries/download/:token
   * Endpoint de descarga segura (sin auth, autenticado por el token).
   * Redirige a R2 o devuelve 503 si el archivo no está disponible.
   */
  fastify.get(
    "/deliveries/download/:token",
    async (request: FastifyRequest<{ Params: { token: string } }>, reply) => {
      const { token } = request.params;

      const payload = verifyDownloadToken(token);
      if (!payload) {
        return reply.code(403).send({ error: "Link de descarga inválido o expirado" });
      }

      // Buscar la entrega
      const delivery = await prisma.delivery.findFirst({
        where: { orderId: payload.orderId, productId: payload.productId },
        include: {
          product: {
            include: {
              files: { where: { isPrimary: true }, take: 1 },
            },
          },
        },
      });

      if (!delivery) {
        return reply.code(404).send({ error: "Entrega no encontrada" });
      }

      // Verificar expiración
      if (delivery.downloadExpiresAt && new Date() > new Date(delivery.downloadExpiresAt)) {
        return reply.code(410).send({
          error: "El link de descarga expiró",
          hint: "Ingresá a /mis-compras y solicitá un nuevo link"
        });
      }

      // Si hay storageKey en R2, generar URL fresca
      const productFile = delivery.product?.files[0];
      if (r2Available() && (productFile?.storageKey ?? delivery.storageKey)) {
        const key = productFile?.storageKey ?? delivery.storageKey!;
        const r2 = new R2StorageAdapter();
        const freshUrl = await r2.getSignedDownloadUrl(key, 300); // 5 min
        return reply.redirect(302, freshUrl);
      }

      // Sin R2: informar que el archivo está pendiente de configuración
      return reply.code(503).send({
        error: "Archivo pendiente de configuración",
        product: delivery.product?.name,
        hint: "El administrador necesita configurar el storage (R2) para habilitar las descargas",
        contact: "soporte@fitnessbusiness.com",
      });
    }
  );

  /**
   * POST /deliveries/refresh/:orderId/:productId
   * Regenera el link de descarga (para cuando expira).
   */
  fastify.get(
    "/deliveries/refresh",
    async (request: FastifyRequest, reply) => {
      const { email, orderId } = request.query as { email?: string; orderId?: string };
      if (!email || !orderId) return reply.code(400).send({ error: "email y orderId requeridos" });

      const tenantId = request.tenantId;
      if (!tenantId) return reply.code(400).send({ error: "Tenant requerido" });

      const order = await prisma.order.findFirst({
        where: { id: orderId, tenantId },
        include: { customer: true, deliveries: true },
      });

      if (!order || order.customer.email.toLowerCase() !== email.toLowerCase()) {
        return reply.code(403).send({ error: "No autorizado" });
      }

      const updatedDeliveries = [];
      const newExpiry = new Date(Date.now() + DOWNLOAD_TTL_HOURS * 60 * 60 * 1000);

      for (const delivery of order.deliveries) {
        const token = generateDownloadToken(order.id, delivery.productId);
        const downloadUrl = `${API_BASE}/api/v1/deliveries/download/${token}`;
        const updated = await prisma.delivery.update({
          where: { id: delivery.id },
          data: { downloadUrl, downloadExpiresAt: newExpiry },
        });
        updatedDeliveries.push(updated);
      }

      return reply.send({ data: { refreshed: updatedDeliveries.length, expiresAt: newExpiry.toISOString() } });
    }
  );
}
