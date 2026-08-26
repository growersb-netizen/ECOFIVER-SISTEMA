/**
 * Fase 07 — Adapter de WhatsApp Business API (Meta).
 */

export interface WASendResult {
  messaging_product: string;
  contacts: Array<{ input: string; wa_id: string }>;
  messages: Array<{ id: string }>;
}

export class WhatsAppAdapter {
  private readonly token: string;
  private readonly phoneNumberId: string;
  private readonly baseUrl = "https://graph.facebook.com/v19.0";

  constructor() {
    this.token = process.env["WHATSAPP_TOKEN"] ?? "";
    this.phoneNumberId = process.env["WHATSAPP_PHONE_ID"] ?? "";

    if (!this.token || !this.phoneNumberId) {
      console.warn("⚠️  WhatsApp credentials no configuradas — mensajes en modo mock");
    }
  }

  async sendTextMessage(to: string, text: string): Promise<WASendResult> {
    if (!this.token) {
      console.log(`[WhatsApp MOCK] A ${to}: ${text}`);
      return { messaging_product: "whatsapp", contacts: [{ input: to, wa_id: to }], messages: [{ id: `mock-${Date.now()}` }] };
    }

    const response = await fetch(`${this.baseUrl}/${this.phoneNumberId}/messages`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        recipient_type: "individual",
        to,
        type: "text",
        text: { body: text, preview_url: false },
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`WhatsApp API error: ${response.status} — ${error}`);
    }

    return response.json() as Promise<WASendResult>;
  }

  async sendTemplate(
    to: string,
    templateName: string,
    languageCode: string,
    components: unknown[]
  ): Promise<WASendResult> {
    if (!this.token) {
      console.log(`[WhatsApp MOCK] Template ${templateName} a ${to}`);
      return { messaging_product: "whatsapp", contacts: [{ input: to, wa_id: to }], messages: [{ id: `mock-${Date.now()}` }] };
    }

    const response = await fetch(`${this.baseUrl}/${this.phoneNumberId}/messages`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        to,
        type: "template",
        template: { name: templateName, language: { code: languageCode }, components },
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`WhatsApp template error: ${response.status} — ${error}`);
    }

    return response.json() as Promise<WASendResult>;
  }
}
