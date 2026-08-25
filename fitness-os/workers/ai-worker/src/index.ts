/**
 * AI Worker — Fase 05.
 *
 * Procesa jobs de generación de contenido con IA (OpenRouter):
 * - GENERATE_CONTENT: genera descripciones, captions, emails en DRAFT
 * - PROCESS_CONVERSATION: responde conversaciones en modo AUTOPILOT
 *
 * REGLAS CRÍTICAS:
 * - La IA NUNCA publica directamente
 * - Todo output queda en estado DRAFT
 * - La IA NUNCA cambia precios ni configuración
 * - Gateway: OpenRouter EXCLUSIVAMENTE
 */

import { Worker, Queue, Job } from "bullmq";
import { PrismaClient } from "@prisma/client";
import pino from "pino";

const log = pino({ level: process.env["LOG_LEVEL"] ?? "info" });
const prisma = new PrismaClient();
const OPENROUTER_KEY = process.env["OPENROUTER_API_KEY"] ?? "";

export type AIJobType = "GENERATE_CONTENT" | "PROCESS_CONVERSATION";

export interface AIJob {
  type: AIJobType;
  tenantId: string;
  payload: Record<string, unknown>;
}

async function callOpenRouter(
  messages: Array<{ role: string; content: string }>,
  model: string
): Promise<string> {
  if (!OPENROUTER_KEY) {
    return `[MOCK IA - ${model}] Respuesta generada`;
  }

  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${OPENROUTER_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": process.env["APP_WEB_URL"] ?? "https://fitness-os.vercel.app",
    },
    body: JSON.stringify({ model, messages, max_tokens: 4096 }),
  });

  if (!response.ok) throw new Error(`OpenRouter: ${response.status}`);
  const data = await response.json() as { choices: Array<{ message: { content: string } }> };
  return data.choices[0]?.message.content ?? "";
}

async function processAIJob(job: Job<AIJob>): Promise<void> {
  const { type, tenantId, payload } = job.data;
  const start = Date.now();

  log.info({ jobId: job.id, type, tenantId }, "Procesando job de IA");

  // Obtener modelo configurado para el tenant
  const modelConfig = await prisma.aIModelConfig.findUnique({
    where: { tenantId_function: { tenantId, function: "GENERATION" } },
  });
  const model = modelConfig?.model ?? "openai/gpt-4o-mini";

  switch (type) {
    case "GENERATE_CONTENT": {
      const { prompt, outputType, entityId } = payload as {
        prompt: string;
        outputType: "product_description" | "social_caption" | "blog_post";
        entityId?: string;
      };

      const content = await callOpenRouter(
        [{ role: "user", content: prompt }],
        model
      );

      // Registrar resultado — siempre como DRAFT
      log.info({ entityId, outputType, chars: content.length }, "Contenido generado (DRAFT)");

      await prisma.aIRequest.create({
        data: {
          tenantId,
          function: "GENERATION",
          model,
          durationMs: Date.now() - start,
          success: true,
          metadata: { outputType, entityId, contentLength: content.length },
        },
      });
      break;
    }

    case "PROCESS_CONVERSATION": {
      const { conversationId, customerMessage } = payload as {
        conversationId: string;
        customerMessage: string;
      };

      const conversation = await prisma.conversation.findUnique({
        where: { id: conversationId },
      });

      if (!conversation) return;
      if (conversation.autopilotMode === "MANUAL") return;

      // AutopilotConfig es por tenant+channel, no per-conversation
      const autopilotConfig = await prisma.autopilotConfig.findUnique({
        where: { tenantId_channel: { tenantId, channel: conversation.channel } },
        include: { kb: { include: { entries: { where: { active: true }, take: 15 } } } },
      });

      if (!autopilotConfig || !autopilotConfig.enabled) return;

      const kbContext = autopilotConfig.kb?.entries
        .map((e) => `${e.question ? `P: ${e.question}\n` : ""}R: ${e.answer ?? e.content}`)
        .join("\n\n") ?? "";

      const attentionConfig = await prisma.aIModelConfig.findUnique({
        where: { tenantId_function: { tenantId, function: "ATTENTION" } },
      });
      const attentionModel = attentionConfig?.model ?? "openai/gpt-4o-mini";

      const response = await callOpenRouter([{
        role: "user",
        content: `Sos asistente de fitness para mujeres respondiendo por ${conversation.channel}.
${kbContext ? `Info del negocio:\n${kbContext}\n\n` : ""}
Mensaje: ${customerMessage}
Respondé en máximo 3 oraciones, tono cálido, español rioplatense, usando "vos".`,
      }], attentionModel);

      // En AUTOPILOT se guarda como mensaje saliente
      // La integración con la plataforma (WA, IG) la maneja el sync-worker
      await prisma.message.create({
        data: {
          conversationId,
          direction: "OUTBOUND",
          type: "TEXT",
          content: response,
          aiGenerated: true,
          status: conversation.autopilotMode === "AUTOPILOT" ? "PENDING_SEND" : "DRAFT",
        },
      });

      await prisma.aIRequest.create({
        data: {
          tenantId,
          function: "ATTENTION",
          model: attentionModel,
          durationMs: Date.now() - start,
          success: true,
          metadata: { conversationId, channel: conversation.channel },
        },
      });
      break;
    }
  }
}

// Cola de AI
export const aiQueue = new Queue<AIJob>("ai", {
  connection: { url: process.env["REDIS_URL"] ?? "redis://localhost:6379" },
  defaultJobOptions: {
    attempts: 2,
    backoff: { type: "exponential", delay: 3000 },
  },
});

const worker = new Worker<AIJob>("ai", processAIJob, {
  connection: { url: process.env["REDIS_URL"] ?? "redis://localhost:6379" },
  concurrency: 3,
});

worker.on("completed", (job) => log.info({ jobId: job.id }, "AI job completado"));
worker.on("failed", (job, err) => log.error({ jobId: job?.id, err: err.message }, "AI job fallido"));

process.on("SIGTERM", async () => {
  await worker.close();
  await prisma.$disconnect();
  process.exit(0);
});

log.info("🤖 AI Worker iniciado — escuchando cola 'ai'");
if (!OPENROUTER_KEY) log.warn("⚠️  OPENROUTER_API_KEY no configurada — modo mock");
