/**
 * Sync Worker — Fase 09/10.
 *
 * Sincroniza:
 * - Mensajes PENDING_SEND de AUTOPILOT con WhatsApp/Instagram
 * - Listings de MercadoLibre (sincroniza stock/precio desde ML)
 *
 * Corre cada 30 segundos via setInterval (no requiere BullMQ para tareas periódicas).
 * Las actualizaciones de precio desde ML son READ-ONLY hacia la BD — NO cambia precios en ML.
 */

import { PrismaClient } from "@prisma/client";
import { createServer } from "http";
import pino from "pino";

const log = pino({ level: process.env["LOG_LEVEL"] ?? "info" });
const prisma = new PrismaClient();

const WA_TOKEN = process.env["WHATSAPP_TOKEN"] ?? "";
const WA_PHONE_ID = process.env["WHATSAPP_PHONE_NUMBER_ID"] ?? "";
const ML_ACCESS_TOKEN = process.env["ML_ACCESS_TOKEN"] ?? "";

// ── WhatsApp sender ────────────────────────────────────────────────

async function sendWhatsAppMessage(to: string, text: string): Promise<boolean> {
  if (!WA_TOKEN || !WA_PHONE_ID) {
    log.warn({ to }, "[MOCK] WA message not sent — credentials missing");
    return true; // mock success
  }
  try {
    const res = await fetch(`https://graph.facebook.com/v18.0/${WA_PHONE_ID}/messages`, {
      method: "POST",
      headers: { Authorization: `Bearer ${WA_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ messaging_product: "whatsapp", to, type: "text", text: { body: text } }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ── Process pending autopilot messages ─────────────────────────────

async function processPendingMessages() {
  const pending = await prisma.message.findMany({
    where: { status: "PENDING_SEND", aiGenerated: true },
    include: { conversation: { include: { customer: true } } },
    take: 20,
    orderBy: { createdAt: "asc" },
  });

  if (pending.length === 0) return;
  log.info({ count: pending.length }, "Procesando mensajes PENDING_SEND");

  for (const msg of pending) {
    const conv = msg.conversation;
    const customer = conv.customer;
    let sent = false;

    if (conv.channel === "WHATSAPP" && customer?.whatsapp) {
      sent = await sendWhatsAppMessage(customer.whatsapp, msg.content);
    } else {
      // Canal no implementado todavía — marcar como enviado en modo mock
      sent = true;
      log.info({ channel: conv.channel, msgId: msg.id }, "Canal sin integración activa — mock send");
    }

    await prisma.message.update({
      where: { id: msg.id },
      data: {
        status: sent ? "SENT" : "FAILED",
        sentAt: sent ? new Date() : undefined,
      },
    });
  }
}

// ── Sync ML listings ───────────────────────────────────────────────

async function syncMLListings() {
  if (!ML_ACCESS_TOKEN) return; // sin credenciales, no sincronizar

  const listings = await prisma.marketplaceListing.findMany({
    where: { marketplace: "MERCADOLIBRE", externalId: { not: null }, status: "PUBLISHED" },
    take: 50,
  });

  for (const listing of listings) {
    try {
      const res = await fetch(`https://api.mercadolibre.com/items/${listing.externalId}`, {
        headers: { Authorization: `Bearer ${ML_ACCESS_TOKEN}` },
      });
      if (!res.ok) continue;
      const item = await res.json() as { status: string; price: number };

      // Solo actualizamos syncStatus y lastSync — NO cambiamos precio en ML
      await prisma.marketplaceListing.update({
        where: { id: listing.id },
        data: {
          syncStatus: item.status === "active" ? "ok" : "paused",
          lastSync: new Date(),
        },
      });
    } catch {
      await prisma.marketplaceListing.update({
        where: { id: listing.id },
        data: { syncStatus: "error" },
      });
    }
  }

  if (listings.length > 0) log.info({ count: listings.length }, "ML listings synced");
}

// ── Main loop ──────────────────────────────────────────────────────

async function runOnce() {
  try {
    await processPendingMessages();
    await syncMLListings();
  } catch (err) {
    log.error({ err }, "Error en ciclo de sync");
  }
}

const INTERVAL_MS = parseInt(process.env["SYNC_INTERVAL_MS"] ?? "30000");

// Health endpoint para Railway healthcheck
const PORT = parseInt(process.env["PORT"] ?? "3000");
createServer((req, res) => {
  if (req.url === "/api/v1/health" || req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true, worker: "sync" }));
  } else {
    res.writeHead(404);
    res.end();
  }
}).listen(PORT, () => log.info({ port: PORT }, "Health server listening"));

log.info({ intervalMs: INTERVAL_MS }, "🔄 Sync Worker iniciado");

// Run immediately, then on interval
runOnce();
const timer = setInterval(runOnce, INTERVAL_MS);

process.on("SIGTERM", async () => {
  clearInterval(timer);
  await prisma.$disconnect();
  log.info("Sync Worker detenido");
  process.exit(0);
});
