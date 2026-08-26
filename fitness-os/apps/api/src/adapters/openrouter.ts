/**
 * Fase 05 — Adapter de OpenRouter (único gateway de IA).
 *
 * REGLA CRÍTICA: Este es el ÚNICO archivo que llama a una API de IA.
 * La API key de Anthropic NUNCA se usa en producción.
 * OpenRouter expone todos los modelos (Claude, GPT, Gemini, etc.) con una sola key.
 */

export type AIFunction = "GENERATION" | "ATTENTION" | "REASONING" | "ECONOMIC";

export interface AIMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface AIRequestOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
}

export interface AIResponse {
  content: string;
  model: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  durationMs: number;
}

// Modelos por defecto por función (vía OpenRouter)
const DEFAULT_MODELS: Record<AIFunction, string> = {
  GENERATION: "openai/gpt-4o-mini",
  ATTENTION: "openai/gpt-4o-mini",
  REASONING: "openai/o3-mini",
  ECONOMIC: "openai/gpt-4o-mini",
};

export class OpenRouterAdapter {
  private readonly apiKey: string;
  private readonly baseUrl = "https://openrouter.ai/api/v1";
  private readonly siteUrl: string;
  private readonly siteName: string;

  constructor() {
    this.apiKey = process.env["OPENROUTER_API_KEY"] ?? "";
    this.siteUrl = process.env["APP_WEB_URL"] ?? "https://fitness-os.vercel.app";
    this.siteName = "Fitness Business OS";

    if (!this.apiKey) {
      console.warn("⚠️  OPENROUTER_API_KEY no configurada — IA en modo mock");
    }
  }

  /**
   * Llama a un modelo vía OpenRouter.
   */
  async complete(
    messages: AIMessage[],
    options: AIRequestOptions = {}
  ): Promise<AIResponse> {
    const model = options.model ?? DEFAULT_MODELS.GENERATION;

    if (!this.apiKey) {
      // Modo desarrollo sin credentials: respuesta mock
      return {
        content: `[MOCK IA] Modelo: ${model} | Mensajes: ${messages.length}`,
        model,
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        durationMs: 0,
      };
    }

    const start = Date.now();

    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
        "HTTP-Referer": this.siteUrl,
        "X-Title": this.siteName,
      },
      body: JSON.stringify({
        model,
        messages,
        temperature: options.temperature ?? 0.7,
        max_tokens: options.maxTokens ?? 4096,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`OpenRouter error: ${response.status} — ${error}`);
    }

    const data = await response.json() as {
      choices: Array<{ message: { content: string } }>;
      model: string;
      usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
    };

    return {
      content: data.choices[0]?.message.content ?? "",
      model: data.model,
      usage: {
        promptTokens: data.usage.prompt_tokens,
        completionTokens: data.usage.completion_tokens,
        totalTokens: data.usage.total_tokens,
      },
      durationMs: Date.now() - start,
    };
  }

  /**
   * Obtiene el modelo configurado para una función de IA del tenant.
   * Prioridad: configuración en DB > default del sistema.
   */
  static getModelForFunction(aiFunction: AIFunction, dbModel?: string | null): string {
    return dbModel ?? DEFAULT_MODELS[aiFunction];
  }
}
