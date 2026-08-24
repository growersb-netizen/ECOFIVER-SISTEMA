"use client";

/**
 * Store Zustand para autenticación.
 * Persiste el token en localStorage y lo sincroniza con cookies (para el middleware de Next.js).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Tipos ───────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
}

export interface Workspace {
  id: number;
  name: string;
  slug: string;
  plan: string;
}

interface AuthState {
  user: AuthUser | null;
  workspace: Workspace | null;
  accessToken: string | null;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  setToken: (token: string) => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function fetchWithAuth(url: string, options: RequestInit = {}, token?: string | null) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Error desconocido");
  }
  return res.json();
}

// ─── Store ───────────────────────────────────────────────────────────────────

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      workspace: null,
      accessToken: null,
      isLoading: false,
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          // 1. Obtener token
          const tokenRes = await fetchWithAuth(`${API_URL}/api/v1/auth/login`, {
            method: "POST",
            body: JSON.stringify({ email, password }),
          });
          const token: string = tokenRes.access_token;

          // 2. Guardar en localStorage para el callback OAuth
          if (typeof window !== "undefined") {
            localStorage.setItem("access_token", token);
            document.cookie = `access_token=${token}; path=/; max-age=3600`;
          }

          // 3. Obtener perfil + primer workspace
          const [meRes, wsRes] = await Promise.all([
            fetchWithAuth(`${API_URL}/api/v1/auth/me`, {}, token),
            fetchWithAuth(`${API_URL}/api/v1/workspaces`, {}, token),
          ]);

          const user: AuthUser = meRes;
          const workspace: Workspace = wsRes.workspaces?.[0] ?? wsRes;

          set({ user, workspace, accessToken: token, isLoading: false, error: null });
        } catch (err: unknown) {
          const message = (err as Error).message ?? "Error al iniciar sesión";
          set({ isLoading: false, error: message });
          throw err;
        }
      },

      logout: () => {
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
          document.cookie = "access_token=; path=/; max-age=0";
        }
        set({ user: null, workspace: null, accessToken: null, error: null });
      },

      clearError: () => set({ error: null }),

      setToken: (token) => {
        if (typeof window !== "undefined") {
          localStorage.setItem("access_token", token);
          document.cookie = `access_token=${token}; path=/; max-age=3600`;
        }
        set({ accessToken: token });
      },
    }),
    {
      name: "viral-hub-auth",
      partialize: (state) => ({
        user: state.user,
        workspace: state.workspace,
        accessToken: state.accessToken,
      }),
    }
  )
);
