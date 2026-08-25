// ── Constantes del sistema ───────────────────────────────────────

export const CURRENCIES = ["ARS", "UYU", "USD", "MXN", "CLP", "COP", "PEN", "EUR"] as const;

export const CHANNELS = [
  "WHATSAPP",
  "INSTAGRAM",
  "FACEBOOK",
  "TIKTOK",
  "YOUTUBE",
  "EMAIL",
  "WEB",
  "MERCADOLIBRE",
] as const;

export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;

// IA — NO ANTHROPIC
export const AI_PROVIDER = "openrouter" as const;
export const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1";

// Default models por función (configurable desde dashboard)
export const DEFAULT_AI_MODELS = {
  GENERATION: "openai/gpt-4o-mini",
  ATTENTION: "openai/gpt-4o-mini",
  REASONING: "openai/o3-mini",
  ECONOMIC: "openai/gpt-4o-mini",
} as const;

// Storage
export const SIGNED_URL_TTL_SECONDS = 900; // 15 minutos — archivos premium
export const MAX_FILE_SIZE_MB = 500;

// Fulfillment
export const MAX_DELIVERY_RETRIES = 3;
export const DELIVERY_RETRY_DELAY_MS = 5000;

// Audit
export const AUDIT_ACTIONS = {
  CREATE: "CREATE",
  UPDATE: "UPDATE",
  DELETE: "DELETE",
  PUBLISH: "PUBLISH",
  UNPUBLISH: "UNPUBLISH",
  PRICE_CHANGE: "PRICE_CHANGE",
  DELIVERY: "DELIVERY",
  REDELIVERY: "REDELIVERY",
  AI_GENERATE: "AI_GENERATE",
  AUTOPILOT_CHANGE: "AUTOPILOT_CHANGE",
  PERMISSION_CHANGE: "PERMISSION_CHANGE",
  LOGIN: "LOGIN",
  LOGOUT: "LOGOUT",
} as const;
