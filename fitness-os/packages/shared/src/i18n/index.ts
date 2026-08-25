/**
 * Fase 14 — i18n helpers.
 * Formato de fechas, monedas y números para Argentina y LatAm.
 */

export { messages } from "./messages/es-AR.js";
export type { Messages } from "./messages/es-AR.js";

export type Locale = "es-AR" | "es-MX" | "es-CL" | "pt-BR";

export const SUPPORTED_LOCALES: Locale[] = ["es-AR", "es-MX", "es-CL", "pt-BR"];
export const DEFAULT_LOCALE: Locale = "es-AR";

// ── Currency formatting ────────────────────────────────────────────

const CURRENCY_BY_LOCALE: Record<Locale, string> = {
  "es-AR": "ARS",
  "es-MX": "MXN",
  "es-CL": "CLP",
  "pt-BR": "BRL",
};

export function formatCurrency(amount: number | string, currency = "ARS", locale: Locale = "es-AR"): string {
  const n = typeof amount === "string" ? parseFloat(amount) : amount;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
}

export function getLocaleCurrency(locale: Locale = DEFAULT_LOCALE): string {
  return CURRENCY_BY_LOCALE[locale] ?? "ARS";
}

// ── Date formatting ────────────────────────────────────────────────

export function formatDate(date: Date | string, locale: Locale = DEFAULT_LOCALE, options?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
    ...options,
  }).format(d);
}

export function formatRelativeDate(date: Date | string, locale: Locale = DEFAULT_LOCALE): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const diff = Date.now() - d.getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  if (days > 7) return formatDate(d, locale);
  if (days > 0) return rtf.format(-days, "day");
  if (hours > 0) return rtf.format(-hours, "hour");
  if (minutes > 0) return rtf.format(-minutes, "minute");
  return rtf.format(-seconds, "second");
}

// ── Number formatting ──────────────────────────────────────────────

export function formatNumber(n: number, locale: Locale = DEFAULT_LOCALE): string {
  return new Intl.NumberFormat(locale, { useGrouping: true }).format(n);
}

export function formatCompact(n: number, locale: Locale = DEFAULT_LOCALE): string {
  return new Intl.NumberFormat(locale, { notation: "compact", compactDisplay: "short" }).format(n);
}
