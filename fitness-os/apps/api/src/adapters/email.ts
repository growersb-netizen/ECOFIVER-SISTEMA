/**
 * Adapter de email — usa Resend (gratis hasta 3000 emails/mes).
 * Si RESEND_API_KEY no está configurada, logea en consola y no falla.
 *
 * Docs: https://resend.com/docs/api-reference/emails/send-email
 */

interface SendEmailOptions {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

interface ResendResponse {
  id?: string;
  message?: string;
}

const RESEND_API_KEY = process.env["RESEND_API_KEY"];
const FROM_EMAIL = process.env["FROM_EMAIL"] ?? "Fitness Business OS <noreply@fitnessbusiness.com>";
const STORE_NAME = process.env["NEXT_PUBLIC_STORE_NAME"] ?? process.env["STORE_NAME"] ?? "Fitness Business OS";

export async function sendEmail(opts: SendEmailOptions): Promise<{ ok: boolean; id?: string; error?: string }> {
  if (!RESEND_API_KEY) {
    console.warn(`[email] RESEND_API_KEY no configurada — email NO enviado a ${opts.to}: "${opts.subject}"`);
    return { ok: false, error: "RESEND_API_KEY no configurada" };
  }

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM_EMAIL,
        to: opts.to,
        subject: opts.subject,
        html: opts.html,
        text: opts.text,
      }),
    });

    const data = await res.json() as ResendResponse;

    if (!res.ok) {
      console.error(`[email] Error enviando a ${opts.to}:`, data.message);
      return { ok: false, error: data.message };
    }

    console.log(`[email] ✓ Enviado a ${opts.to} (id: ${data.id})`);
    return { ok: true, id: data.id };
  } catch (err) {
    console.error(`[email] Error de red:`, err);
    return { ok: false, error: String(err) };
  }
}

// ── Templates ──────────────────────────────────────────────────────

export interface DeliveryEmailData {
  customerName: string;
  customerEmail: string;
  orderId: string;
  storeName?: string;
  supportEmail?: string;
  webUrl?: string;
  items: Array<{
    productName: string;
    downloadUrl: string;
    expiresAt: Date;
  }>;
}

/**
 * Email de entrega post-compra.
 * Se envía cuando el fulfillment completa correctamente.
 */
export function buildDeliveryEmail(data: DeliveryEmailData): { subject: string; html: string; text: string } {
  const storeName = data.storeName ?? STORE_NAME;
  const supportEmail = data.supportEmail ?? process.env["SUPPORT_EMAIL"] ?? "soporte@fitnessbusiness.com";
  const webUrl = data.webUrl ?? process.env["APP_WEB_URL"] ?? "https://fitness-os-web.vercel.app";
  const misComprasUrl = `${webUrl}/mis-compras`;

  const formatDate = (d: Date) =>
    d.toLocaleDateString("es-AR", { day: "2-digit", month: "long", year: "numeric" });

  const itemsHtml = data.items
    .map(
      (item) => `
      <div style="background:#0D0F1A;border:1px solid #1A1F35;border-radius:12px;padding:20px;margin-bottom:16px;">
        <p style="margin:0 0 4px;color:#6B7494;font-size:12px;text-transform:uppercase;letter-spacing:0.1em;font-family:sans-serif;">PRODUCTO</p>
        <p style="margin:0 0 16px;color:#E8EDFF;font-size:16px;font-weight:700;font-family:sans-serif;">${item.productName}</p>
        <a href="${item.downloadUrl}"
          style="display:inline-block;padding:12px 24px;background:linear-gradient(135deg,#DE3163,#B82050);color:#fff;text-decoration:none;border-radius:8px;font-weight:800;font-size:15px;font-family:sans-serif;">
          ⬇ Descargar ahora
        </a>
        <p style="margin:12px 0 0;color:#4A5070;font-size:12px;font-family:sans-serif;">
          Link válido hasta el ${formatDate(item.expiresAt)}
        </p>
      </div>`
    )
    .join("");

  const subject = `⚡ Tu compra está lista — ${data.items.map((i) => i.productName).join(", ")}`;

  const html = `
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#07080F;font-family:sans-serif;">
  <div style="max-width:560px;margin:0 auto;padding:40px 20px;">

    <!-- Header -->
    <div style="text-align:center;margin-bottom:32px;">
      <p style="margin:0 0 4px;color:#DE3163;font-size:12px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;">
        ✦ COMPRA CONFIRMADA ✦
      </p>
      <h1 style="margin:0;color:#E8EDFF;font-size:32px;font-weight:800;letter-spacing:0.02em;">${storeName}</h1>
    </div>

    <!-- Success card -->
    <div style="background:#0D0F1A;border:1px solid #1A1F35;border-radius:16px;padding:28px;margin-bottom:24px;text-align:center;">
      <div style="width:64px;height:64px;border-radius:50%;background:rgba(222,49,99,0.15);border:2px solid #DE3163;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;">
        <span style="font-size:28px;">⚡</span>
      </div>
      <h2 style="margin:0 0 8px;color:#E8EDFF;font-size:22px;font-weight:700;">¡Hola, ${data.customerName}!</h2>
      <p style="margin:0;color:#A0AAC8;font-size:15px;line-height:1.6;">
        Tu pago fue confirmado. Tus productos digitales están listos para descargar.
      </p>
    </div>

    <!-- Downloads -->
    <h3 style="margin:0 0 16px;color:#6B7494;font-size:12px;text-transform:uppercase;letter-spacing:0.1em;">TUS DESCARGAS</h3>
    ${itemsHtml}

    <!-- Mis compras CTA -->
    <div style="background:rgba(0,255,135,0.05);border:1px solid rgba(0,255,135,0.15);border-radius:12px;padding:20px;margin-bottom:24px;text-align:center;">
      <p style="margin:0 0 12px;color:#A0AAC8;font-size:14px;line-height:1.5;">
        También podés acceder a todas tus compras desde el portal:
      </p>
      <a href="${misComprasUrl}" style="display:inline-block;padding:10px 20px;background:#0D0F1A;border:1px solid rgba(0,255,135,0.3);color:#00FF87;text-decoration:none;border-radius:8px;font-weight:700;font-size:14px;">
        Ver mis compras →
      </a>
    </div>

    <!-- Order info -->
    <div style="border-top:1px solid #1A1F35;padding-top:20px;text-align:center;">
      <p style="margin:0 0 4px;color:#3A3F55;font-size:12px;">N° DE ORDEN</p>
      <p style="margin:0 0 16px;color:#4A5070;font-size:13px;font-family:monospace;">${data.orderId}</p>
      <p style="margin:0;color:#3A3F55;font-size:12px;line-height:1.6;">
        ¿Problemas con tu descarga?<br>
        Escribinos a <a href="mailto:${supportEmail}" style="color:#DE3163;">${supportEmail}</a>
      </p>
    </div>

    <!-- Footer -->
    <p style="text-align:center;color:#2A2F45;font-size:11px;margin-top:32px;">
      ${storeName} · Los links de descarga son válidos por 72 horas.
    </p>
  </div>
</body>
</html>`;

  const text = [
    `¡Hola, ${data.customerName}!`,
    `Tu compra fue confirmada. Tus productos están listos para descargar.`,
    ``,
    ...data.items.map((i) => `• ${i.productName}\n  ${i.downloadUrl}\n  Válido hasta: ${formatDate(i.expiresAt)}`),
    ``,
    `También podés ver tus compras en: ${misComprasUrl}`,
    ``,
    `Orden: ${data.orderId}`,
    `Soporte: ${supportEmail}`,
  ].join("\n");

  return { subject, html, text };
}
