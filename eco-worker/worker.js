/**
 * Eco Agentes — Cloudflare Worker v2.0
 * Endpoints:
 *   GET  /health          → status check
 *   POST /generate        → Gemini Imagen 3 → { ok, image_base64, mime_type }
 *   POST /generar-copy    → Gemini Flash texto → { ok, copy }
 *   POST /api/gemini      → compat: texto via Gemini Flash
 *   POST /api/imagen      → compat: imagen via Gemini Imagen 3
 */

const GEMINI_TEXT_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent";
const GEMINI_IMAGEN_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict";

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

// ── TEXT via Gemini Flash ────────────────────────────────────────────────────

async function geminiText(apiKey, prompt) {
  const body = {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.8, maxOutputTokens: 1024 },
  };

  const r = await fetch(`${GEMINI_TEXT_URL}?key=${apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!r.ok) {
    const err = await r.text();
    throw new Error(`Gemini text error ${r.status}: ${err}`);
  }

  const data = await r.json();
  const text =
    data?.candidates?.[0]?.content?.parts?.[0]?.text ?? "(sin respuesta)";
  return text;
}

// ── IMAGE via Gemini Imagen 3 ────────────────────────────────────────────────

async function geminiImagen(apiKey, prompt, width = 1080, height = 1080) {
  // Aspect ratio: 1:1 → "1:1", 9:16 → "9:16"
  let aspectRatio = "1:1";
  if (height > width) aspectRatio = "9:16";
  else if (width > height) aspectRatio = "16:9";

  const body = {
    instances: [{ prompt }],
    parameters: {
      sampleCount: 1,
      aspectRatio,
      language: "es",
    },
  };

  const r = await fetch(`${GEMINI_IMAGEN_URL}?key=${apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!r.ok) {
    const err = await r.text();
    throw new Error(`Gemini Imagen error ${r.status}: ${err}`);
  }

  const data = await r.json();
  const b64 = data?.predictions?.[0]?.bytesBase64Encoded;
  const mime = data?.predictions?.[0]?.mimeType ?? "image/png";

  if (!b64) throw new Error("Imagen 3 no devolvió imagen");
  return { image_base64: b64, mime_type: mime };
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

    const apiKey = env.GEMINI_API_KEY || env.GEMINI_KEY;  // soporta ambos nombres de secret

    // ── GET /health ──────────────────────────────────────────────────────────
    if (method === "GET" && path === "/health") {
      return json({ ok: true, service: "eco-agentes", version: "2.0" });
    }

    // ── POST /generate ───────────────────────────────────────────────────────
    // Body: { prompt, width?, height?, language? }
    // Returns: { ok, image_base64, mime_type }
    if (method === "POST" && path === "/generate") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }

      if (!body.prompt) return json({ ok: false, error: "Falta campo prompt" }, 400);
      if (!apiKey) return json({ ok: false, error: "GEMINI_API_KEY no configurado" }, 500);

      try {
        const result = await geminiImagen(
          apiKey,
          body.prompt,
          body.width ?? 1080,
          body.height ?? 1080
        );
        return json({ ok: true, ...result });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // ── POST /generar-copy ───────────────────────────────────────────────────
    // Body: { producto, modelo?, descripcion?, tono? }
    // Returns: { ok, copy }
    if (method === "POST" && path === "/generar-copy") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }

      if (!apiKey) return json({ ok: false, error: "GEMINI_API_KEY no configurado" }, 500);

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
        const copy = await geminiText(apiKey, prompt);
        return json({ ok: true, copy });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // ── POST /api/gemini  (compatibilidad) ───────────────────────────────────
    // Body: { prompt } o { message }
    if (method === "POST" && path === "/api/gemini") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }

      const prompt = body.prompt ?? body.message ?? "";
      if (!prompt) return json({ ok: false, error: "Falta campo prompt" }, 400);
      if (!apiKey) return json({ ok: false, error: "GEMINI_API_KEY no configurado" }, 500);

      try {
        const text = await geminiText(apiKey, prompt);
        return json({ ok: true, text, response: text });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // ── POST /api/imagen  (compatibilidad) ───────────────────────────────────
    if (method === "POST" && path === "/api/imagen") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: "JSON inválido" }, 400);
      }

      if (!body.prompt) return json({ ok: false, error: "Falta campo prompt" }, 400);
      if (!apiKey) return json({ ok: false, error: "GEMINI_API_KEY no configurado" }, 500);

      try {
        const result = await geminiImagen(apiKey, body.prompt);
        return json({ ok: true, ...result });
      } catch (e) {
        return json({ ok: false, error: e.message }, 502);
      }
    }

    // 404
    return json({ ok: false, error: `Ruta no encontrada: ${method} ${path}` }, 404);
  },
};
