/**
 * Adapter de email transaccional (Resend) para entregas digitales.
 */

export interface DeliveryEmailInput {
  to: string;
  customerName: string;
  productName: string;
  files: Array<{ name: string; url: string }>;
  orderId: string;
  tenantId: string;
}

export class ResendEmailAdapter {
  private readonly apiKey: string;
  private readonly from: string;

  constructor() {
    this.apiKey = process.env["RESEND_API_KEY"] ?? "";
    this.from = process.env["EMAIL_FROM"] ?? "noreply@fitness-os.vercel.app";

    if (!this.apiKey) {
      console.warn("⚠️  RESEND_API_KEY no configurada — emails en modo mock");
    }
  }

  async sendDeliveryEmail(input: DeliveryEmailInput): Promise<boolean> {
    if (!this.apiKey) {
      console.log(`[Email MOCK] Entrega a ${input.to}: ${input.productName}`);
      return true;
    }

    const html = this.buildDeliveryHtml(input);

    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: this.from,
        to: input.to,
        subject: `✅ Tu descarga está lista: ${input.productName}`,
        html,
      }),
    });

    return response.ok;
  }

  private buildDeliveryHtml(input: DeliveryEmailInput): string {
    const fileLinks = input.files
      .map((f) => `<li><a href="${f.url}" style="color:#00FF87;">${f.name}</a> (válido por 15 minutos)</li>`)
      .join("\n");

    return `
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="background:#07080F;color:#E8EDFF;font-family:'DM Sans',sans-serif;margin:0;padding:40px 20px;">
  <div style="max-width:520px;margin:0 auto;">
    <h1 style="font-size:2rem;color:#00FF87;margin-bottom:8px;">¡Tu compra está lista! ✅</h1>
    <p style="color:#A0AAC8;margin-bottom:32px;">Hola ${input.customerName}, gracias por tu compra.</p>

    <div style="background:#0D0F1A;border:1px solid #1E2240;border-radius:12px;padding:24px;margin-bottom:24px;">
      <h2 style="color:#E8EDFF;margin-top:0;">${input.productName}</h2>
      <ul style="padding-left:20px;color:#A0AAC8;line-height:2;">
        ${fileLinks}
      </ul>
    </div>

    <p style="color:#4A5070;font-size:0.85rem;">
      Los links de descarga son válidos por 15 minutos.
      Podés acceder a todos tus productos en cualquier momento desde tu biblioteca personal.
    </p>

    <p style="color:#4A5070;font-size:0.85rem;margin-top:32px;">
      ¿Tenés alguna duda? Respondé este email o escribinos por WhatsApp.<br>
      ¡Que disfrutes tu compra! 💪
    </p>
  </div>
</body>
</html>
    `.trim();
  }
}
