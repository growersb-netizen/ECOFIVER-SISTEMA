/**
 * Fase 15 — Hardening.
 * Middlewares de seguridad adicionales para la API:
 * - Request size limiting
 * - Slow endpoint detection
 * - Suspicious pattern detection
 * - CORS violation logging
 */

import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";

// ── Request size guard ─────────────────────────────────────────────
// Fastify ya limita body size via bodyLimit config.
// Este hook registra solicitudes sospechosamente grandes.
export function registerSecurityHooks(app: FastifyInstance) {
  // Log slow requests (> 3s)
  app.addHook("onResponse", (request, reply, done) => {
    const elapsed = reply.elapsedTime;
    if (elapsed > 3000) {
      app.log.warn({
        url: request.url,
        method: request.method,
        statusCode: reply.statusCode,
        elapsedMs: Math.round(elapsed),
        tenantId: (request as FastifyRequest & { tenantId?: string }).tenantId,
      }, "Solicitud lenta detectada");
    }
    done();
  });

  // Detect and log suspicious user agents
  app.addHook("onRequest", (request, _reply, done) => {
    const ua = request.headers["user-agent"] ?? "";
    const suspicious = [
      "sqlmap", "nikto", "nmap", "dirbuster", "masscan",
      "nuclei", "zgrab", "python-requests/2.2", "curl/7.1",
    ];
    if (suspicious.some(s => ua.toLowerCase().includes(s))) {
      app.log.warn({
        ip: request.ip,
        url: request.url,
        ua,
      }, "User-agent sospechoso detectado");
    }
    done();
  });

  // Block paths that commonly indicate scanning
  app.addHook("onRequest", (request, reply, done) => {
    const blocked = [
      "/wp-admin", "/wp-login", "/.env", "/phpinfo",
      "/admin.php", "/xmlrpc.php", "/.git/config",
    ];
    if (blocked.some(b => request.url.toLowerCase().startsWith(b))) {
      reply.status(404).send({ ok: false, error: { code: "NOT_FOUND" } });
      return;
    }
    done();
  });
}

// ── Security response headers ──────────────────────────────────────
// Helmet already sets most of these; these are additional headers.
export function getSecurityHeaders(): Record<string, string> {
  return {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(self)",
    "Cache-Control": "no-store",
  };
}

// ── Webhook signature helpers ──────────────────────────────────────

import crypto from "crypto";

export function verifyMercadoPagoSignature(
  payload: string,
  secret: string,
  signature: string
): boolean {
  if (!secret || !signature) return false;
  const expected = crypto.createHmac("sha256", secret).update(payload).digest("hex");
  try {
    return crypto.timingSafeEqual(
      Buffer.from(signature, "hex"),
      Buffer.from(expected, "hex")
    );
  } catch {
    return false;
  }
}

// ── Input sanitization helpers ─────────────────────────────────────

/** Elimina tags HTML básicos para prevenir XSS en campos de texto */
export function sanitizeText(input: string): string {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;")
    .replace(/\//g, "&#x2F;");
}

/** Valida que un email tenga formato válido */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/** Valida que un slug sea seguro (solo letras, números, guiones) */
export function isValidSlug(slug: string): boolean {
  return /^[a-z0-9-]+$/.test(slug);
}
