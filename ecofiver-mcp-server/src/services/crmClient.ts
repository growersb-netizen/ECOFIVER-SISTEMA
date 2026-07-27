import axios, { AxiosError } from "axios";
import { CRM_BASE_URL, CRM_API_KEY } from "../constants.js";

export async function crmRequest<T>(
  path: string,
  method: "GET" | "POST" = "GET",
  data?: unknown
): Promise<T> {
  const response = await axios({
    method,
    url: `${CRM_BASE_URL}${path}`,
    data,
    timeout: 45000,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${CRM_API_KEY}`,
    },
    validateStatus: () => true,
  });

  if (response.status >= 200 && response.status < 300) {
    return response.data as T;
  }

  // El 409 de crear_contrato es informativo (DNI duplicado) — el caller lo maneja
  if (response.status === 409) {
    const err: any = new Error("DUPLICATE");
    err.status = 409;
    err.body = response.data;
    throw err;
  }

  const detail =
    typeof response.data === "object" && response.data !== null
      ? JSON.stringify(response.data)
      : String(response.data);
  throw new Error(`CRM respondió ${response.status}: ${detail}`);
}

export function handleApiError(error: unknown): string {
  if (error instanceof Error && (error as any).status === 409) {
    const body = (error as any).body || {};
    const numero = body?.detail?.numero_solicitud || body?.numero_solicitud || "desconocido";
    return `Error: ya existe una solicitud activa con ese DNI (${numero}). Si es correcto crear una nueva de todos modos, reintentá con forzar=true.`;
  }
  if (axios.isAxiosError(error)) {
    const e = error as AxiosError;
    if (e.code === "ECONNABORTED") {
      return "Error: la solicitud al CRM tardó demasiado (timeout). Probá de nuevo.";
    }
    if (e.response) {
      return `Error: el CRM respondió ${e.response.status} — ${JSON.stringify(e.response.data)}`;
    }
  }
  return `Error: ${error instanceof Error ? error.message : String(error)}`;
}
