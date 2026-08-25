/**
 * Cliente de API para el panel de administración.
 * Maneja autenticación, renovación de tokens y tipos.
 */

const API_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";

interface RequestOptions extends RequestInit {
  auth?: boolean;
}

class APIClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  setTokens(access: string, refresh: string) {
    this.accessToken = access;
    this.refreshToken = refresh;
    if (typeof window !== "undefined") {
      localStorage.setItem("fitness_access_token", access);
      localStorage.setItem("fitness_refresh_token", refresh);
    }
  }

  loadTokens() {
    if (typeof window !== "undefined") {
      this.accessToken = localStorage.getItem("fitness_access_token");
      this.refreshToken = localStorage.getItem("fitness_refresh_token");
    }
  }

  clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("fitness_access_token");
      localStorage.removeItem("fitness_refresh_token");
    }
  }

  async fetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
    this.loadTokens();
    const { auth = true, ...init } = options;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string>),
    };

    if (auth && this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    let response = await fetch(`${API_URL}${path}`, { ...init, headers });

    // Si el token expiró, intentar renovar
    if (response.status === 401 && this.refreshToken) {
      const refreshed = await this.refresh();
      if (refreshed) {
        headers["Authorization"] = `Bearer ${this.accessToken}`;
        response = await fetch(`${API_URL}${path}`, { ...init, headers });
      } else {
        this.clearTokens();
        if (typeof window !== "undefined") window.location.href = "/login";
        throw new Error("Sesión expirada");
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: "Error desconocido" }));
      throw new Error((error as { error?: string }).error ?? "Error en la solicitud");
    }

    return response.json() as Promise<T>;
  }

  private async refresh(): Promise<boolean> {
    if (!this.refreshToken) return false;
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: this.refreshToken }),
      });
      if (!response.ok) return false;
      const data = await response.json() as { accessToken: string; refreshToken: string };
      this.setTokens(data.accessToken, data.refreshToken);
      return true;
    } catch {
      return false;
    }
  }

  // ── Auth ──────────────────────────────────────────────────────
  async login(email: string, password: string, tenantSlug?: string) {
    const data = await this.fetch<{
      accessToken: string;
      refreshToken: string;
      user: { id: string; email: string; name: string; role: string; tenant: { id: string; slug: string; name: string } };
    }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, tenantSlug }),
      auth: false,
    });
    this.setTokens(data.accessToken, data.refreshToken);
    return data;
  }

  async logout() {
    const refreshToken = this.refreshToken;
    this.clearTokens();
    if (refreshToken) {
      await this.fetch("/api/v1/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refreshToken }),
      }).catch(() => {});
    }
  }

  async getMe() {
    const data = await this.fetch<{ user?: { id: string; email: string; name?: string; role: string } } | { id: string; email: string; name?: string; role: string }>("/api/v1/auth/me");
    // API may return { user: {...} } or the user object directly
    return ("user" in data && data.user) ? data.user : data as { id: string; email: string; name?: string; role: string };
  }

  // ── Products ──────────────────────────────────────────────────
  async getProducts(params?: { page?: number; pageSize?: number; status?: string; q?: string; search?: string }) {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).reduce((acc, [k, v]) => {
        if (v !== undefined && v !== "") acc[k] = String(v);
        return acc;
      }, {} as Record<string, string>)
    ).toString();
    return this.fetch<{ products?: unknown[]; data?: unknown[]; pagination?: unknown }>(`/api/v1/products?${qs}`);
  }

  async createProduct(data: unknown) {
    return this.fetch("/api/v1/products", { method: "POST", body: JSON.stringify(data) });
  }

  async publishProduct(id: string) {
    return this.fetch(`/api/v1/products/${id}/publish`, { method: "POST" });
  }

  // ── Orders ────────────────────────────────────────────────────
  async getOrders(params?: { page?: number; status?: string }) {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).reduce((acc, [k, v]) => {
        if (v !== undefined && v !== "") acc[k] = String(v);
        return acc;
      }, {} as Record<string, string>)
    ).toString();
    return this.fetch<{ orders?: unknown[]; data?: unknown[]; pagination?: unknown }>(`/api/v1/orders?${qs}`);
  }

  // ── CRM ───────────────────────────────────────────────────────
  async getLeads(params?: { page?: number; status?: string; search?: string }) {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).reduce((acc, [k, v]) => {
        if (v !== undefined && v !== "") acc[k] = String(v);
        return acc;
      }, {} as Record<string, string>)
    ).toString();
    return this.fetch<{ leads?: unknown[]; data?: unknown[] }>(`/api/v1/crm/leads?${qs}`);
  }

  async getCustomers(params?: { page?: number; search?: string }) {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).reduce((acc, [k, v]) => {
        if (v !== undefined && v !== "") acc[k] = String(v);
        return acc;
      }, {} as Record<string, string>)
    ).toString();
    return this.fetch<{ customers?: unknown[]; data?: unknown[] }>(`/api/v1/crm/customers?${qs}`);
  }

  // ── AI ────────────────────────────────────────────────────────
  async generateProductDescription(data: {
    productId: string;
    productName: string;
    tone?: string;
    length?: "short" | "medium" | "long";
  }) {
    return this.fetch<{ description?: string; content?: string; model: string; note: string }>(
      "/api/v1/ai/generate/product-description",
      { method: "POST", body: JSON.stringify(data) }
    );
  }

  async generateSocialCaption(data: {
    productId: string;
    productName: string;
    platform?: string;
    tone?: string;
  }) {
    return this.fetch<{ caption?: string; content?: string; model: string; note: string }>(
      "/api/v1/ai/generate/social-caption",
      { method: "POST", body: JSON.stringify(data) }
    );
  }
}

export const api = new APIClient();
// Also export as apiClient for convenience
export const apiClient = api;
