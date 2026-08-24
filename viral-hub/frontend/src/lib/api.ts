/**
 * Cliente centralizado de la API de Viral Hub.
 * Todas las llamadas HTTP al backend FastAPI pasan por acá.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Tipos ───────────────────────────────────────────────────────────────────

export interface Channel {
  id: number;
  platform: string;
  alias: string;
  remote_username?: string;
  avatar_url?: string;
  status: "connected" | "requires_reconnect" | "revoked" | "error";
  capabilities: string[];
  connected_at: string;
}

export interface Group {
  id: number;
  name: string;
  description?: string;
  channels: Channel[];
  channel_count: number;
}

export interface MediaAsset {
  id: number;
  filename: string;
  file_type: string;
  duration_seconds?: number;
  size_bytes: number;
  thumbnail_url?: string;
  public_url: string;
  created_at: string;
}

export interface Publication {
  id: number;
  caption: string;
  status: "draft" | "queued" | "processing" | "published" | "failed" | "partial";
  scheduled_at?: string;
  published_at?: string;
  created_at: string;
  media_asset?: MediaAsset;
  jobs: PublicationJob[];
}

export interface PublicationJob {
  id: number;
  publication_id: number;
  channel_id: number;
  channel?: Channel;
  status: "pending" | "running" | "success" | "failed" | "retry";
  attempt_count: number;
  error_message?: string;
  remote_post_id?: string;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  total_channels: number;
  total_publications: number;
  publications_this_week: number;
  success_rate: number;
  recent_publications: Publication[];
}

export interface StorageStatus {
  configured: boolean;
  provider?: string;
  bucket?: string;
  endpoint?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `Error ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ─── API ─────────────────────────────────────────────────────────────────────

export const api = {
  // ── Auth ──────────────────────────────────────────────────────────────────

  auth: {
    me: () => request<{ id: number; email: string; full_name: string }>("/api/v1/auth/me"),
  },

  // ── Workspace ─────────────────────────────────────────────────────────────

  workspaces: {
    list: () => request<{ workspaces: Array<{ id: number; name: string; slug: string; plan: string }> }>("/api/v1/workspaces"),
    get: (id: number) => request<{ id: number; name: string; slug: string; plan: string; member_count: number }>(`/api/v1/workspaces/${id}`),
    update: (id: number, data: Partial<{ name: string; slug: string }>) =>
      request(`/api/v1/workspaces/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  },

  // ── Channels ──────────────────────────────────────────────────────────────

  channels: {
    list: (workspaceId: number) =>
      request<{ channels: Channel[] }>(`/api/v1/workspaces/${workspaceId}/channels`),

    getOAuthUrl: (workspaceId: number, platform: string) =>
      request<{ auth_url: string; platform: string; redirect_uri: string }>(
        `/api/v1/workspaces/${workspaceId}/channels/oauth/${platform}/initiate`
      ),

    oauthCallback: (workspaceId: number, platform: string, code: string, redirectUri: string) =>
      request<{ channel: Channel; message: string }>(
        `/api/v1/workspaces/${workspaceId}/channels/oauth/${platform}/callback`,
        {
          method: "POST",
          body: JSON.stringify({ code, redirect_uri: redirectUri }),
        }
      ),

    update: (workspaceId: number, channelId: number, data: { alias: string }) =>
      request<Channel>(`/api/v1/workspaces/${workspaceId}/channels/${channelId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    disconnect: (workspaceId: number, channelId: number) =>
      request(`/api/v1/workspaces/${workspaceId}/channels/${channelId}`, {
        method: "DELETE",
      }),
  },

  // ── Groups ────────────────────────────────────────────────────────────────

  groups: {
    list: (workspaceId: number) =>
      request<{ groups: Group[] }>(`/api/v1/workspaces/${workspaceId}/groups`),

    create: (workspaceId: number, data: { name: string; description?: string }) =>
      request<Group>(`/api/v1/workspaces/${workspaceId}/groups`, {
        method: "POST",
        body: JSON.stringify(data),
      }),

    update: (workspaceId: number, groupId: number, data: { name?: string; description?: string }) =>
      request<Group>(`/api/v1/workspaces/${workspaceId}/groups/${groupId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    delete: (workspaceId: number, groupId: number) =>
      request(`/api/v1/workspaces/${workspaceId}/groups/${groupId}`, { method: "DELETE" }),

    addChannel: (workspaceId: number, groupId: number, channelId: number) =>
      request(`/api/v1/workspaces/${workspaceId}/groups/${groupId}/channels`, {
        method: "POST",
        body: JSON.stringify({ channel_id: channelId }),
      }),

    removeChannel: (workspaceId: number, groupId: number, channelId: number) =>
      request(
        `/api/v1/workspaces/${workspaceId}/groups/${groupId}/channels/${channelId}`,
        { method: "DELETE" }
      ),
  },

  // ── Media ─────────────────────────────────────────────────────────────────

  media: {
    getStorageStatus: () =>
      request<StorageStatus>("/api/v1/storage-status"),

    list: (workspaceId: number) =>
      request<{ assets: MediaAsset[] }>(`/api/v1/workspaces/${workspaceId}/media`),

    getUploadUrl: (workspaceId: number, filename: string, contentType: string, sizeBytes: number) =>
      request<{ upload_url: string; public_url: string; asset_id: number }>(
        `/api/v1/workspaces/${workspaceId}/media/upload-url`,
        {
          method: "POST",
          body: JSON.stringify({ filename, content_type: contentType, size_bytes: sizeBytes }),
        }
      ),

    confirmUpload: (workspaceId: number, assetId: number) =>
      request<MediaAsset>(`/api/v1/workspaces/${workspaceId}/media/${assetId}/confirm`, {
        method: "POST",
      }),

    delete: (workspaceId: number, assetId: number) =>
      request(`/api/v1/workspaces/${workspaceId}/media/${assetId}`, { method: "DELETE" }),
  },

  // ── Publications ──────────────────────────────────────────────────────────

  publications: {
    create: (
      workspaceId: number,
      data: {
        caption: string;
        media_asset_id?: number;
        channel_ids?: number[];
        group_ids?: number[];
        scheduled_at?: string;
      }
    ) =>
      request<Publication>(`/api/v1/workspaces/${workspaceId}/publications`, {
        method: "POST",
        body: JSON.stringify(data),
      }),

    list: (workspaceId: number, params?: { status?: string; limit?: number; offset?: number }) => {
      const qs = params
        ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()
        : "";
      return request<{ publications: Publication[]; total: number }>(
        `/api/v1/workspaces/${workspaceId}/publications${qs}`
      );
    },

    getJobs: (workspaceId: number, publicationId: number) =>
      request<{ jobs: PublicationJob[] }>(
        `/api/v1/workspaces/${workspaceId}/publications/${publicationId}/jobs`
      ),

    retryJob: (workspaceId: number, jobId: number) =>
      request(`/api/v1/workspaces/${workspaceId}/publications/jobs/${jobId}/retry`, {
        method: "POST",
      }),
  },

  // ── Dashboard ─────────────────────────────────────────────────────────────

  dashboard: {
    stats: (workspaceId: number) =>
      request<DashboardStats>(`/api/v1/workspaces/${workspaceId}/dashboard`),
  },
};
