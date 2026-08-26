/**
 * Fase 08 — Adapter de MercadoLibre.
 */

export interface MLItem {
  id: string;
  title: string;
  permalink: string;
  status: string;
  price: number;
  currency_id: string;
}

export interface MLOrder {
  id: string;
  status: string;
  date_created: string;
  total_amount: number;
  currency_id: string;
  buyer: { id: number; email: string; nickname: string };
  order_items: Array<{
    item: { id: string; title: string };
    quantity: number;
    unit_price: number;
  }>;
}

export interface MLTokens {
  access_token: string;
  refresh_token: string;
  user_id: number;
  expires_in: number;
}

export class MercadoLibreAdapter {
  private readonly accessToken: string;
  private readonly baseUrl = "https://api.mercadolibre.com";

  constructor(accessToken?: string) {
    this.accessToken = accessToken ?? process.env["MERCADOLIBRE_ACCESS_TOKEN"] ?? "";
    if (!this.accessToken) {
      console.warn("⚠️  MercadoLibre no configurado");
    }
  }

  async exchangeCode(code: string): Promise<MLTokens | null> {
    const clientId = process.env["MERCADOLIBRE_CLIENT_ID"] ?? "";
    const clientSecret = process.env["MERCADOLIBRE_CLIENT_SECRET"] ?? "";
    const redirectUri = `${process.env["API_URL"] ?? ""}/api/v1/ml/auth/callback`;

    if (!clientId || !clientSecret) return null;

    const response = await fetch("https://api.mercadolibre.com/oauth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: clientId,
        client_secret: clientSecret,
        code,
        redirect_uri: redirectUri,
      }),
    });

    if (!response.ok) return null;
    return response.json() as Promise<MLTokens>;
  }

  async createItem(itemData: {
    title: string;
    category_id: string;
    price: number;
    currency_id: string;
    available_quantity: number;
    buying_mode: string;
    condition: string;
    listing_type_id: string;
    description: { plain_text: string };
  }): Promise<MLItem> {
    const response = await fetch(`${this.baseUrl}/items`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(itemData),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ML createItem error: ${response.status} — ${error}`);
    }

    return response.json() as Promise<MLItem>;
  }

  async getOrder(orderId: string): Promise<MLOrder | null> {
    if (!this.accessToken) return null;

    const response = await fetch(`${this.baseUrl}/orders/${orderId}`, {
      headers: { "Authorization": `Bearer ${this.accessToken}` },
    });

    if (!response.ok) return null;
    return response.json() as Promise<MLOrder>;
  }

  async updatePrice(itemId: string, price: number): Promise<boolean> {
    const response = await fetch(`${this.baseUrl}/items/${itemId}`, {
      method: "PUT",
      headers: {
        "Authorization": `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ price }),
    });
    return response.ok;
  }

  async pauseItem(itemId: string): Promise<boolean> {
    const response = await fetch(`${this.baseUrl}/items/${itemId}`, {
      method: "PUT",
      headers: {
        "Authorization": `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status: "paused" }),
    });
    return response.ok;
  }
}
