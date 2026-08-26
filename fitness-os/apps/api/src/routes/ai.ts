/**
 * Fase 05 — Rutas de IA (solo DRAFT, nunca publicación directa).
 *
 * POST /api/v1/ai/generate/product-description
 * POST /api/v1/ai/generate/social-caption
 * POST /api/v1/ai/generate/email-subject
 * POST /api/v1/ai/generate/whatsapp-response
 * GET  /api/v1/ai/models         — modelos configurados del tenant
 * GET  /api/v1/ai/history        — historial de requests de IA
 *
 * REGLA: La IA NUNCA publica directamente.
 * Todo resultado va a estado DRAFT y requiere aprobación humana.
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { OpenRouterAdapter } from "../adapters/openrouter.js";

const ProductDescriptionSchema = z.object({
  productId: z.string().uuid(),
  productName: z.string().optional(),
  tone: z.enum(["motivacional", "profesional", "empático", "energético"]).default("motivacional"),
  length: z.enum(["corta", "media", "larga"]).default("media"),
  targetAudience: z.string().optional(),
  benefits: z.array(z.string()).optional(),
});

const SocialCaptionSchema = z.object({
  platform: z.enum(["INSTAGRAM", "FACEBOOK", "TIKTOK"]),
  productId: z.string().uuid().optional(),
  topic: z.string().min(3),
  tone: z.enum(["motivacional", "educativo", "testimonial", "pregunta"]).default("motivacional"),
  includeHashtags: z.boolean().default(true),
  includeEmojis: z.boolean().default(true),
  cta: z.string().optional(),
});

const EmailSubjectSchema = z.object({
  type: z.enum(["bienvenida", "producto", "oferta", "abandono_carrito", "reengagement"]),
  productName: z.string().optional(),
  discount: z.number().optional(),
  customerName: z.string().optional(),
  count: z.number().int().min(1).max(5).default(3),
});

const WhatsAppResponseSchema = z.object({
  customerMessage: z.string().min(1).max(2000),
  context: z.string().optional(),
  conversationHistory: z.array(z.object({
    role: z.enum(["customer", "agent"]),
    content: z.string(),
  })).optional(),
});

const AI_PROMPT_TEMPLATES = {
  productDescription: (data: z.infer<typeof ProductDescriptionSchema>, productName: string) => `
Sos experta en marketing digital de fitness y salud para mujeres.
Escribí una descripción de producto ${data.length === "corta" ? "breve (100-150 palabras)" : data.length === "media" ? "completa (200-300 palabras)" : "detallada (400-500 palabras)"}
en tono ${data.tone} para el siguiente producto:

Nombre: ${productName}
${data.targetAudience ? `Público objetivo: ${data.targetAudience}` : ""}
${data.benefits?.length ? `Beneficios clave: ${data.benefits.join(", ")}` : ""}

La descripción debe:
- Hablar directamente a la cliente usando "vos"
- Enfocarse en la transformación que logra, no en características técnicas
- Ser clara, concisa y convincente
- Evitar frases genéricas como "el mejor del mercado"
- Incluir llamada a la acción al final

Devolvé SOLO la descripción, sin comentarios adicionales.
`.trim(),

  socialCaption: (data: z.infer<typeof SocialCaptionSchema>) => `
Sos experta en redes sociales de fitness para mujeres.
Creá un caption para ${data.platform} sobre: ${data.topic}

Tono: ${data.tone}
${data.includeEmojis ? "Incluir emojis relevantes" : "Sin emojis"}
${data.includeHashtags ? "Incluir entre 5-10 hashtags al final (mezcla de populares y de nicho en español)" : "Sin hashtags"}
${data.cta ? `CTA específico: ${data.cta}` : "Incluir llamada a la acción"}

El caption debe:
- Empezar con un gancho impactante (no "Hola" ni "Buenos días")
- Usar lenguaje cercano, tutear a la seguidora con "vos"
- Ser auténtico y evitar frases cliché del fitness
- Adaptarse al formato y algoritmo de ${data.platform}

Devolvé SOLO el caption listo para publicar, sin comentarios adicionales.
`.trim(),

  emailSubjects: (data: z.infer<typeof EmailSubjectSchema>) => `
Generá ${data.count} asuntos de email para el tipo: ${data.type}
${data.productName ? `Producto: ${data.productName}` : ""}
${data.discount ? `Descuento: ${data.discount}%` : ""}
${data.customerName ? `Nombre de la cliente: ${data.customerName}` : ""}

Los asuntos deben:
- Tener entre 40-60 caracteres
- Generar curiosidad o urgencia
- Evitar palabras que activan spam (GRATIS, !!!,  $$$)
- Estar en español rioplatense
- Ser directos y relevantes

Devolvé los asuntos numerados, uno por línea, sin explicaciones.
`.trim(),

  whatsappResponse: (data: z.infer<typeof WhatsAppResponseSchema>, kbContext: string) => `
Sos una asistente de atención al cliente de fitness para mujeres.
Respondé en WhatsApp de forma natural, cálida y profesional.

${kbContext ? `Información del negocio:\n${kbContext}\n` : ""}
${data.context ? `Contexto adicional: ${data.context}\n` : ""}
${data.conversationHistory?.length ? `Historial de conversación:\n${data.conversationHistory.map(m => `${m.role === "customer" ? "Cliente" : "Asistente"}: ${m.content}`).join("\n")}\n` : ""}

Mensaje actual de la cliente: ${data.customerMessage}

Respuesta (máximo 3-4 oraciones, tono amigable, en español rioplatense, usando "vos"):
`.trim(),
};

export async function aiRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;
  const openrouter = new OpenRouterAdapter();

  fastify.addHook("preHandler", fastify.authenticate);

  /**
   * POST /generate/product-description
   */
  fastify.post(
    "/generate/product-description",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = ProductDescriptionSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const product = await prisma.product.findFirst({
        where: { id: body.data.productId, tenantId },
        include: { content: true },
      });
      if (!product) return reply.code(404).send({ error: "Producto no encontrado" });

      // Obtener modelo configurado para GENERATION
      const modelConfig = await prisma.aIModelConfig.findUnique({
        where: { tenantId_function: { tenantId, function: "GENERATION" } },
      });

      const model = OpenRouterAdapter.getModelForFunction("GENERATION", modelConfig?.model);
      const prompt = AI_PROMPT_TEMPLATES.productDescription(body.data, body.data.productName ?? product.name);

      const start = Date.now();
      const result = await openrouter.complete([
        { role: "user", content: prompt },
      ], { model, temperature: 0.8 });

      // Registrar en AIRequest
      await prisma.aIRequest.create({
        data: {
          tenantId,
          function: "GENERATION",
          model: result.model,
          promptTokens: result.usage.promptTokens,
          completionTokens: result.usage.completionTokens,
          totalTokens: result.usage.totalTokens,
          durationMs: result.durationMs,
          success: true,
          metadata: { productId: product.id, tone: body.data.tone },
        },
      });

      return reply.send({
        content: result.content,
        model: result.model,
        usage: result.usage,
        note: "Resultado en DRAFT — requiere revisión humana antes de publicar",
      });
    }
  );

  /**
   * POST /generate/social-caption
   */
  fastify.post(
    "/generate/social-caption",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = SocialCaptionSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const modelConfig = await prisma.aIModelConfig.findUnique({
        where: { tenantId_function: { tenantId, function: "GENERATION" } },
      });

      const model = OpenRouterAdapter.getModelForFunction("GENERATION", modelConfig?.model);
      const prompt = AI_PROMPT_TEMPLATES.socialCaption(body.data);

      const result = await openrouter.complete([
        { role: "user", content: prompt },
      ], { model, temperature: 0.9 });

      await prisma.aIRequest.create({
        data: {
          tenantId,
          function: "GENERATION",
          model: result.model,
          promptTokens: result.usage.promptTokens,
          completionTokens: result.usage.completionTokens,
          totalTokens: result.usage.totalTokens,
          durationMs: result.durationMs,
          success: true,
          metadata: { platform: body.data.platform, topic: body.data.topic },
        },
      });

      return reply.send({
        content: result.content,
        model: result.model,
        note: "Resultado en DRAFT — revisar y editar antes de programar publicación",
      });
    }
  );

  /**
   * POST /generate/email-subject
   */
  fastify.post(
    "/generate/email-subject",
    { preHandler: [requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = EmailSubjectSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;
      const modelConfig = await prisma.aIModelConfig.findUnique({
        where: { tenantId_function: { tenantId, function: "GENERATION" } },
      });

      const model = OpenRouterAdapter.getModelForFunction("GENERATION", modelConfig?.model);
      const prompt = AI_PROMPT_TEMPLATES.emailSubjects(body.data);

      const result = await openrouter.complete([
        { role: "user", content: prompt },
      ], { model, temperature: 0.85 });

      const subjects = result.content
        .split("\n")
        .map((s) => s.replace(/^\d+\.\s*/, "").trim())
        .filter(Boolean);

      return reply.send({
        subjects,
        model: result.model,
        note: "Revisar y elegir el asunto más adecuado",
      });
    }
  );

  /**
   * POST /generate/whatsapp-response
   * Para modo COPILOT: la agente ve la sugerencia y decide si enviarla.
   */
  fastify.post(
    "/generate/whatsapp-response",
    { preHandler: [requireRole("SUPPORT")] },
    async (request: FastifyRequest, reply) => {
      const body = WhatsAppResponseSchema.safeParse(request.body);
      if (!body.success) return reply.code(400).send({ error: "Datos inválidos" });

      const tenantId = request.tenantId!;

      // Obtener knowledge base para contexto
      const kb = await prisma.knowledgeBase.findFirst({
        where: { tenantId, active: true },
        include: {
          entries: {
            where: { active: true },
            orderBy: { createdAt: "desc" },
            take: 10,
          },
        },
      });

      const kbContext = kb?.entries
        .map((e) => `${e.question ? `P: ${e.question}\n` : ""}R: ${e.answer}`)
        .join("\n\n") ?? "";

      const modelConfig = await prisma.aIModelConfig.findUnique({
        where: { tenantId_function: { tenantId, function: "ATTENTION" } },
      });

      const model = OpenRouterAdapter.getModelForFunction("ATTENTION", modelConfig?.model);
      const prompt = AI_PROMPT_TEMPLATES.whatsappResponse(body.data, kbContext);

      const result = await openrouter.complete([
        { role: "user", content: prompt },
      ], { model, temperature: 0.7, maxTokens: 500 });

      await prisma.aIRequest.create({
        data: {
          tenantId,
          function: "ATTENTION",
          model: result.model,
          promptTokens: result.usage.promptTokens,
          completionTokens: result.usage.completionTokens,
          totalTokens: result.usage.totalTokens,
          durationMs: result.durationMs,
          success: true,
        },
      });

      return reply.send({
        suggestion: result.content,
        model: result.model,
        note: "SUGERENCIA — La agente decide si enviar, editar o ignorar",
      });
    }
  );

  /**
   * GET /models — configuración de modelos del tenant
   */
  fastify.get(
    "/models",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const configs = await prisma.aIModelConfig.findMany({
        where: { tenantId: request.tenantId! },
        orderBy: { function: "asc" },
      });
      return reply.send({ data: configs });
    }
  );

  /**
   * GET /history — historial de requests de IA
   */
  fastify.get(
    "/history",
    { preHandler: [requireRole("MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const requests = await prisma.aIRequest.findMany({
        where: { tenantId: request.tenantId! },
        orderBy: { createdAt: "desc" },
        take: 100,
      });

      const totalTokens = requests.reduce((acc, r) => acc + (r.totalTokens ?? 0), 0);
      return reply.send({ data: requests, stats: { totalRequests: requests.length, totalTokens } });
    }
  );
}
