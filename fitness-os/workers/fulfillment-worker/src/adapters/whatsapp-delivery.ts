/**
 * Adapter de WhatsApp para notificaciones de entrega.
 */

export interface DeliveryWAInput {
  phone: string;
  customerName: string;
  productName: string;
  downloadUrl: string;
}

export class WhatsAppDeliveryAdapter {
  private readonly token: string;
  private readonly phoneNumberId: string;
  private readonly baseUrl = "https://graph.facebook.com/v19.0";

  constructor() {
    this.token = process.env["WHATSAPP_TOKEN"] ?? "";
    this.phoneNumberId = process.env["WHATSAPP_PHONE_ID"] ?? "";
  }

  async sendDeliveryMessage(input: DeliveryWAInput): Promise<boolean> {
    if (!this.token) {
      console.log(`[WhatsApp MOCK] Entrega a ${input.phone}: ${input.productName}`);
      return true;
    }

    const message = `¡Hola ${input.customerName}! 🎉\n\nTu compra *${input.productName}* está lista.\n\nDescargá tu producto aquí:\n${input.downloadUrl}\n\n_El link es válido por 15 minutos._\n\n¡Que lo disfrutes! 💪`;

    const response = await fetch(`${this.baseUrl}/${this.phoneNumberId}/messages`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        to: input.phone,
        type: "text",
        text: { body: message },
      }),
    });

    return response.ok;
  }
}
