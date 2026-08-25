/**
 * Fase 03 — Adapter de Mercado Pago.
 * Implementa la interfaz PaymentProvider.
 * Abstracción: si en el futuro se cambia de gateway,
 * solo se reemplaza este archivo.
 */

export interface MPPreferenceItem {
  id: string;
  title: string;
  quantity: number;
  unit_price: number;
  currency_id: string;
}

export interface MPPreferenceInput {
  items: MPPreferenceItem[];
  payer: { email: string; name: string };
  external_reference: string;
  back_urls: { success: string; failure: string; pending: string };
  notification_url: string;
}

export interface MPPreferenceResult {
  id: string;
  init_point: string;
  sandbox_init_point: string;
}

export interface MPPayment {
  id: string;
  status: "approved" | "rejected" | "pending" | "in_process" | "cancelled";
  external_reference: string;
  transaction_amount: number;
  currency_id: string;
  payer: { email: string };
  date_approved: string | null;
  [key: string]: unknown;
}

export class MercadoPagoAdapter {
  private readonly accessToken: string;
  private readonly baseUrl = "https://api.mercadopago.com";
  private readonly isSandbox: boolean;

  constructor() {
    this.accessToken = process.env["MERCADOPAGO_ACCESS_TOKEN"] ?? "";
    this.isSandbox = process.env["NODE_ENV"] !== "production";

    if (!this.accessToken) {
      console.warn("⚠️  MERCADOPAGO_ACCESS_TOKEN no configurado — pagos deshabilitados");
    }
  }

  async createPreference(input: MPPreferenceInput): Promise<MPPreferenceResult> {
    if (!this.accessToken) {
      // Modo desarrollo sin credentials: devuelve mock
      return {
        id: `mock-${Date.now()}`,
        init_point: `http://localhost:3002/checkout/mock?ref=${input.external_reference}`,
        sandbox_init_point: `http://localhost:3002/checkout/mock?ref=${input.external_reference}`,
      };
    }

    const response = await fetch(`${this.baseUrl}/checkout/preferences`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(input),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Mercado Pago error: ${response.status} — ${error}`);
    }

    return response.json() as Promise<MPPreferenceResult>;
  }

  async getPayment(paymentId: string): Promise<MPPayment | null> {
    if (!this.accessToken) return null;

    const response = await fetch(`${this.baseUrl}/v1/payments/${paymentId}`, {
      headers: { "Authorization": `Bearer ${this.accessToken}` },
    });

    if (!response.ok) return null;
    return response.json() as Promise<MPPayment>;
  }

  async refundPayment(paymentId: string, amount?: number): Promise<boolean> {
    if (!this.accessToken) return false;

    const body = amount ? JSON.stringify({ amount }) : "{}";
    const response = await fetch(`${this.baseUrl}/v1/payments/${paymentId}/refunds`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
      },
      body,
    });

    return response.ok;
  }
}
