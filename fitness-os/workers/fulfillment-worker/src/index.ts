/**
 * Fulfillment Worker — Fase 04.
 *
 * Escucha la cola BullMQ "fulfillment" y procesa entregas digitales.
 *
 * Flujo por job:
 *  1. Recibir { orderId, orderItemId, productId, customerId }
 *  2. Verificar idempotencia (idempotencyKey = orderId:productId en DB)
 *  3. Obtener archivos del producto desde Prisma
 *  4. Generar URL firmada de R2 (TTL 15 min para download inmediato)
 *  5. Registrar Delivery con status DELIVERED
 *  6. Crear CustomerLibraryItem (acceso permanente con URLs nuevas)
 *  7. Enviar email de entrega (Resend)
 *  8. Enviar WhatsApp (si el cliente tiene teléfono)
 *
 * Idempotencia:
 *  - idempotencyKey = `${orderId}:${productId}` con constraint UNIQUE en DB
 *  - Si el job llega dos veces, el segundo insert falla silenciosamente
 */

import { Worker, Queue, Job } from "bullmq";
import { PrismaClient } from "@prisma/client";
import pino from "pino";
import { R2StorageAdapter } from "./adapters/storage.js";
import { ResendEmailAdapter } from "./adapters/email.js";
import { WhatsAppDeliveryAdapter } from "./adapters/whatsapp-delivery.js";

const log = pino({ level: process.env["LOG_LEVEL"] ?? "info" });

const prisma = new PrismaClient();
const r2 = new R2StorageAdapter();
const email = new ResendEmailAdapter();
const wa = new WhatsAppDeliveryAdapter();

export interface FulfillmentJob {
  orderId: string;
  orderItemId: string;
  productId: string;
  customerId: string;
  tenantId: string;
}

// Cola de fulfillment — los jobs se encolan desde el webhook de MP
export const fulfillmentQueue = new Queue<FulfillmentJob>("fulfillment", {
  connection: {
    url: process.env["REDIS_URL"] ?? "redis://localhost:6379",
  },
  defaultJobOptions: {
    attempts: 3,
    backoff: { type: "exponential", delay: 5000 },
    removeOnComplete: { count: 1000 },
    removeOnFail: { count: 500 },
  },
});

async function processFulfillmentJob(job: Job<FulfillmentJob>): Promise<void> {
  const { orderId, orderItemId, productId, customerId, tenantId } = job.data;
  const idempotencyKey = `${orderId}:${productId}`;

  log.info({ jobId: job.id, idempotencyKey }, "Procesando fulfillment");

  // ── 1. Idempotencia ──────────────────────────────────────────────
  const existingDelivery = await prisma.delivery.findUnique({
    where: { idempotencyKey },
  });

  if (existingDelivery) {
    log.info({ idempotencyKey, deliveryId: existingDelivery.id }, "Delivery ya procesado, omitiendo");
    return;
  }

  // ── 2. Cargar datos ──────────────────────────────────────────────
  const [product, customer, order] = await Promise.all([
    prisma.product.findUnique({
      where: { id: productId },
      include: { files: true },
    }),
    prisma.customer.findUnique({ where: { id: customerId } }),
    prisma.order.findUnique({ where: { id: orderId } }),
  ]);

  if (!product || !customer || !order) {
    throw new Error(`Datos incompletos: product=${productId}, customer=${customerId}, order=${orderId}`);
  }

  // ── 3. Crear Delivery (reserva del slot idempotente) ─────────────
  const delivery = await prisma.delivery.create({
    data: {
      orderId,
      orderItemId,
      customerId,
      productId,
      tenantId,
      idempotencyKey,
      channel: "EMAIL",
      status: "PROCESSING",
    },
  });

  try {
    // ── 4. Generar URLs firmadas (TTL 15 min) ─────────────────────
    const signedUrls: Array<{ name: string; url: string }> = [];

    for (const file of product.files) {
      const url = await r2.getSignedDownloadUrl(file.storageKey, 900); // 15 min
      signedUrls.push({ name: file.name, url });
    }

    // ── 5. Crear CustomerLibraryItem para acceso permanente ────────
    await prisma.customerLibraryItem.upsert({
      where: { customerId_productId: { customerId, productId } },
      update: { active: true },
      create: {
        customerId,
        productId,
        orderId,
        active: true,
      },
    });

    // ── 6. Enviar email de entrega ─────────────────────────────────
    const emailSent = await email.sendDeliveryEmail({
      to: customer.email,
      customerName: customer.name,
      productName: product.name,
      files: signedUrls,
      orderId,
      tenantId,
    });

    // ── 7. WhatsApp si tiene teléfono ──────────────────────────────
    let waSent = false;
    if (customer.phone) {
      waSent = await wa.sendDeliveryMessage({
        phone: customer.phone,
        customerName: customer.name,
        productName: product.name,
        downloadUrl: signedUrls[0]?.url ?? "",
      });
    }

    // ── 8. Marcar entrega como DELIVERED ──────────────────────────
    await prisma.delivery.update({
      where: { id: delivery.id },
      data: {
        status: "DELIVERED",
        deliveredAt: new Date(),
        metadata: { emailSent, waSent, filesCount: signedUrls.length },
      },
    });

    // Actualizar estado de la orden
    await prisma.order.update({
      where: { id: orderId },
      data: { status: "DELIVERED" },
    });

    log.info({ idempotencyKey, emailSent, waSent }, "Fulfillment completado exitosamente");
  } catch (err) {
    // Marcar como fallido para reintento
    await prisma.delivery.update({
      where: { id: delivery.id },
      data: { status: "FAILED", error: String(err) },
    });

    // Registrar intento fallido
    await prisma.deliveryAttempt.create({
      data: {
        deliveryId: delivery.id,
        status: "FAILED",
        error: String(err),
        attemptNumber: job.attemptsMade + 1,
      },
    });

    throw err; // BullMQ reintentará
  }
}

// ── Iniciar Worker ───────────────────────────────────────────────────
const worker = new Worker<FulfillmentJob>("fulfillment", processFulfillmentJob, {
  connection: {
    url: process.env["REDIS_URL"] ?? "redis://localhost:6379",
  },
  concurrency: 5,
});

worker.on("completed", (job) => {
  log.info({ jobId: job.id }, "Job completado");
});

worker.on("failed", (job, err) => {
  log.error({ jobId: job?.id, err: err.message }, "Job fallido");
});

worker.on("error", (err) => {
  log.error({ err: err.message }, "Worker error");
});

process.on("SIGTERM", async () => {
  log.info("Shutting down fulfillment worker...");
  await worker.close();
  await prisma.$disconnect();
  process.exit(0);
});

log.info("🚚 Fulfillment Worker iniciado — escuchando cola 'fulfillment'");
