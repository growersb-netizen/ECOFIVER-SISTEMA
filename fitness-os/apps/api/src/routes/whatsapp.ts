/**
 * Fase 07 — WhatsApp Business API.
 *
 * GET  /api/v1/webhooks/whatsapp     — verificación del webhook (Meta)
 * POST /api/v1/webhooks/whatsapp     — recibir mensajes entrantes
 * POST /api/v1/whatsapp/send         — enviar mensaje manual
 * GET  /api/v1/whatsapp/autopilot    — config de autopilot
 * PATCH /api/v1/whatsapp/autopilot   — actualizar modo
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { OpenRouterAdapter } from "../adapters/openrouter.js";
import { WhatsAppAdapter } from "../adapters/whatsapp.js";

const SendMessageSchema = z.object({
  to: z.string().min(10).max(20), // número con código de país
  message: z.string().min(1).max(4096),
  type: z.enum(["text", "template"]).default("text"),
  templateName: z.string().optional(),
  templateParams: z.array(z.string()).optional(),
});

const UpdateAutopilotSchema = z.object({
  mode: z.enum(["MANUAL", "COPILOT", "AUTOPILOT"]),
  enabled: z.boolean().optional(),
});

export async function whatsappRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;
  const wa = new WhatsAppAdapter();
  const openrouter = new OpenRouterAdapter();

  /**
   * GET /webhooks/whatsapp — verificación del webhook de Meta
   */
  fastify.get("/webhooks/whatsapp", async (request: FastifyRequest, reply) => {
    const query = request.query as Record<string, string>;
    const mode = query["hub.mode"];
    const token = query["hub.verify_token"];
    const challenge = query["hub.challenge"];

    if (mode === "subscribe" && token === process.env["WHATSAPP_VERIFY_TOKEN"]) {
      return reply.code(200).send(challenge);
    }

    return reply.code(403).send("Forbidden");
  });

  /**
   * POST /webhooks/whatsapp — recibir mensajes entrantes
   */
  fastify.post("/webhooks/whatsapp", async (request: FastifyRequest, reply) => {
    // Meta espera respuesta 200 en menos de 5 segundos
    reply.code(200).send({ ok: true });

    const body = request.body as {
      entry?: Array<{
        changes?: Array<{
          value?: {
            messages?: Array<{
              from: string;
              id: string;
              type: string;
              text?: { body: string };
              timestamp: string;
            }>;
            contacts?: Array<{ profile?: { name?: string }; wa_id?: string }>;
          };
        }>;
      }>;
    };

    const entry = body.entry?.[0];
    const change = entry?.changes?.[0]?.value;
    const messages = change?.messages;

    if (!messages?.length) return;

    for (const msg of messages) {
      if (msg.type !== "text" || !msg.text?.body) continue;

      const from = msg.from;
      const text = msg.text.body;
      const contact = change.contacts?.[0];
      const customerName = contact?.profile?.name ?? "Clienta";

      // Buscar el tenant por el número de teléfono del negocio
      // En un sistema multi-tenant real, el número de teléfono identifica al tenant
      // Por ahora buscamos el primer tenant activo con config de WhatsApp
      const autopilotConfig = await prisma.autopilotConfig.findFirst({
        where: { channel: "WHATSAPP", enabled: true },
        include: {
          tenant: true,
          kb: { include: { entries: { where: { active: true }, take: 20 } } },
        },
      });

      if (!autopilotConfig) return;

      const tenantId = autopilotConfig.tenantId;

      // Buscar o crear lead
      const lead = await prisma.lead.upsert({
        where: {
          // Lead identificado por teléfono dentro del tenant
          id: (await prisma.lead.findFirst({
            where: { tenantId, phone: from },
          }))?.id ?? "new-lead-placeholder",
        },
        update: { name: customerName },
        create: {
          tenantId,
          name: customerName,
          phone: from,
          source: "WHATSAPP",
          status: "NEW",
        },
      });

      // Buscar o crear conversación
      const conversation = await prisma.conversation.upsert({
        where: {
          id: (await prisma.conversation.findFirst({
            where: { tenantId, channel: "WHATSAPP", externalId: from, open: true },
          }))?.id ?? "new-conv-placeholder",
        },
        update: { updatedAt: new Date() },
        create: {
          tenantId,
          channel: "WHATSAPP",
          externalId: from,
          leadId: lead.id,
          open: true,
        },
      });

      // Guardar mensaje entrante
      await prisma.message.create({
        data: {
          conversationId: conversation.id,
          direction: "INBOUND",
          type: "TEXT",
          content: text,
          externalId: msg.id,
          status: "DELIVERED",
          sentAt: new Date(parseInt(msg.timestamp) * 1000),
        },
      });

      // Responder según modo de autopilot
      if (autopilotConfig.mode === "MANUAL") {
        // No responder — la agente lo hace manualmente desde el CRM
        return;
      }

      // COPILOT o AUTOPILOT: generar respuesta con IA
      const kbContext = autopilotConfig.kb?.entries
        .map((e) => `${e.question ? `P: ${e.question}\n` : ""}R: ${e.answer}`)
        .join("\n\n") ?? "";

      const modelConfig = await prisma.aIModelConfig.findUnique({
        where: { tenantId_function: { tenantId, function: "ATTENTION" } },
      });

      const model = OpenRouterAdapter.getModelForFunction("ATTENTION", modelConfig?.model);

      try {
        const aiResult = await openrouter.complete([
          {
            role: "user",
            content: `Sos una asistente de fitness para mujeres respondiendo por WhatsApp.
${kbContext ? `Información del negocio:\n${kbContext}\n\n` : ""}
Mensaje de ${customerName}: ${text}

Respondé en máximo 2-3 oraciones, en tono cálido y profesional, en español rioplatense usando "vos".`,
          },
        ], { model, maxTokens: 300, temperature: 0.7 });

        const responseText = aiResult.content;

        if (autopilotConfig.mode === "AUTOPILOT") {
          // Enviar directamente
          await wa.sendTextMessage(from, responseText);

          await prisma.message.create({
            data: {
              conversationId: conversation.id,
              direction: "OUTBOUND",
              type: "TEXT",
              content: responseText,
              status: "SENT",
              aiGenerated: true,
            },
          });

          await prisma.aIRequest.create({
            data: {
              tenantId,
              function: "ATTENTION",
              model: aiResult.model,
              promptTokens: aiResult.usage.promptTokens,
              completionTokens: aiResult.usage.completionTokens,
              totalTokens: aiResult.usage.totalTokens,
              durationMs: aiResult.durationMs,
              success: true,
              metadata: { channel: "WHATSAPP", conversationId: conversation.id },
            },
          });
        }
        // Si es COPILOT, la sugerencia queda guardada pero no se envía automáticamente
        // El agente la ve en el CRM y decide
      } catch (err) {
        console.error("Error generando respuesta IA para WhatsApp:", err);
      }
    }
  });

  /**
   * POST /whatsapp/send — enviar mensaje manual desde el panel
   */
  fastify.post(
    "/whatsapp/send",
    { preHandler: [fastify.authenticate, requireRole("SUPPORT")] },
    async (request: FastifyRequest, reply) => {
      const body = SendMessageSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const { to, message, type } = body.data;

      if (type === "text") {
        const result = await wa.sendTextMessage(to, message);
        return reply.send({ ok: true, messageId: result.messages?.[0]?.id });
      }

      return reply.code(400).send({ error: "Tipo de mensaje no soportado" });
    }
  );

  /**
   * GET /whatsapp/autopilot
   */
  fastify.get(
    "/whatsapp/autopilot",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const config = await prisma.autopilotConfig.findUnique({
        where: { tenantId_channel: { tenantId: request.tenantId!, channel: "WHATSAPP" } },
        include: { kb: { select: { id: true, name: true } } },
      });

      return reply.send({ data: config });
    }
  );

  /**
   * PATCH /whatsapp/autopilot
   */
  fastify.patch(
    "/whatsapp/autopilot",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = UpdateAutopilotSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const config = await prisma.autopilotConfig.upsert({
        where: { tenantId_channel: { tenantId, channel: "WHATSAPP" } },
        update: body.data,
        create: {
          tenantId,
          channel: "WHATSAPP",
          ...body.data,
        },
      });

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "AUTOPILOT_CHANGE",
          entity: "AutopilotConfig",
          entityId: config.id,
          newValue: body.data,
        },
      });

      return reply.send({ data: config });
    }
  );
}
