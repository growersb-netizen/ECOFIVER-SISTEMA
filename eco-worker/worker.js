/**
 * Eco Agentes — Cloudflare Worker v3.0
 * Proveedor IA: OpenRouter (único proveedor oficial)
 * Endpoints:
 *   GET  /health          → status check
 *   POST /generate        → imagen via OpenRouter (gpt-5-image-mini) → { ok, image_base64, mime_type }
 *   POST /generar-copy    → texto via OpenRouter → { ok, copy }
 *   POST /api/gemini      → compat: texto via OpenRouter
 *   POST /api/imagen      → compat: imagen via OpenRouter
 */

const OPENROUTER_BASE = "https://openrouter.ai/api/v1";
const OR_TEXT_MODEL   = "google/gemini-2.0-flash-001";
const OR_IMAGE_MODEL  = "openai/gpt-4o-mini";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

// ── TEXT via OpenRouter ──────────────────────────────────────────────────────

async function orText(apiKey, prompt, model = OR_TEXT_MODEL) {
  const r = await fetch(`${OPENROUTER_BASE}/chat/completions`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://www.ecomodulosypiscinas.com.ar",
      "X-Title": "EcoFiver",
    },
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: prompt }],
      max_tokens: 1024,
      temperature: 0.8,
    }),
  });

  if (!r.ok) {
    const err = await r.text();
    throw new Error(`OpenRouter text error ${r.status}: ${err}`);
  }

  const data = await r.json();
  const text = data?.choices?.[0]?.message?.content ?? "(sin respuesta)";
  return text;
}

// ── IMAGE via OpenRouter ─────────────────────────────────────────────────────
// Usa la API de images/generations compatible con DALL-E

async function orImagen(apiKey, prompt) {
  const r = await fetch(`${OPENROUTER_BASE}/images/generations`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://www.ecomodulosypiscinas.com.ar",
      "X-Title": "EcoFiver",
    },
    body: JSON.stringify({
      model: "openai/gpt-5-image-mini",
      prompt,
      n: 1,
      size: "1024x1024",
      response_format: "b64_json",
    }),
  });

  if (!r.ok) {
    const err = await r.text();
    throw new Error(`OpenRouter imagen error ${r.status}: ${err}`);
  }

  const data = await r.json();
  const b64 = data?.data?.[0]?.b64_json;
  if (!b64) throw new Error("OpenRouter no devolvió imagen");
  return { image_base64: b64, mime_type: "image/png" };
}

// ── ROUTER ───────────────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const apiKey = env.OPENROUTER_API_KEY;

    // ── GET /health ──────────────────────────────────────────────────────────
    if (method === "GET" && path === "/health") {
      return json({ ok: true, service: "eco-agentes", version: "3.0", provider: "openrouter" });
    }

    if (!apiKey) {
      return json({ ok: false, error: "OPENROUTER_API_KEY no configurado" }, 500);
    }

    // ── POST /generate ───────────────────────────────────────────────────────
    if (method === "POST" && path === "/generate") {
      let body;
      try { body = await request.json(); } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }
      if (!body.prompt) return json({ ok: false, error: "Falta campo prompt" }, 400);

      try {
        const result = await orImagen(apiKey, body.prompt);
        return json({ ok: true, ...result });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // ── POST /generar-copy ───────────────────────────────────────────────────
    if (method === "POST" && path === "/generar-copy") {
      let body;
      try { body = await request.json(); } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }

      const tono = body.tono ?? "profesional y cercano";
      const prompt = `Sos un copywriter experto en marketing de productos para el hogar en Argentina.
Escribí copy de redes sociales para:
- Producto: ${body.producto ?? ""}
- Modelo: ${body.modelo ?? ""}
- Descripción: ${body.descripcion ?? ""}
- Tono: ${tono}

Incluí:
1. Título llamativo (max 10 palabras)
2. Descripción corta para Instagram/Facebook (2-3 oraciones, emojis)
3. 5 hashtags relevantes

Respondé solo con el copy, sin introducción.`;

      try {
        const copy = await orText(apiKey, prompt);
        return json({ ok: true, copy });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // ── POST /api/gemini  (compatibilidad) ───────────────────────────────────
    if (method === "POST" && path === "/api/gemini") {
      let body;
      try { body = await request.json(); } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }
      const prompt = body.prompt ?? body.message ?? "";
      if (!prompt) return json({ ok: false, error: "Falta campo prompt" }, 400);

      try {
        const text = await orText(apiKey, prompt);
        return json({ ok: true, text, response: text });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // ── POST /api/imagen  (compatibilidad) ───────────────────────────────────
    if (method === "POST" && path === "/api/imagen") {
      let body;
      try { body = await request.json(); } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }
      if (!body.prompt) return json({ ok: false, error: "Falta campo prompt" }, 400);

      try {
        const result = await orImagen(apiKey, body.prompt);
        return json({ ok: true, ...result });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // 404
    return json({ ok: false, error: `Ruta no encontrada: ${method} ${path}` }, 404);
  },
};
