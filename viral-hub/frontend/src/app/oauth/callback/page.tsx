"use client";

/**
 * Página de callback OAuth.
 *
 * Flujo:
 *  1. El usuario autorizó la app en la plataforma (Meta / TikTok / Google).
 *  2. La plataforma redirigió a esta URL con ?code=XXX&state=platform:workspace_id
 *  3. Esta página extrae los parámetros, llama al backend y completa la conexión.
 *  4. Redirige al usuario a /canales con éxito o error.
 *
 * Nota: es una ruta pública (no requiere auth en middleware) porque el navegador
 * llega acá desde la plataforma social y puede no tener cookies frescas.
 * El token se recupera de localStorage + cookie antes de la llamada.
 */

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { Suspense } from "react";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// redirect_uri debe coincidir exactamente con el registrado en la app del provider
const CALLBACK_URL = typeof window !== "undefined"
  ? `${window.location.origin}/oauth/callback`
  : `${API_URL.replace("-production.up.railway.app", "-jet.vercel.app")}/oauth/callback`;

function CallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("Conectando tu cuenta…");
  const [channelName, setChannelName] = useState("");

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");   // "platform:workspace_id"
    const error = params.get("error");   // si el usuario canceló

    if (error) {
      setStatus("error");
      setMessage("Cancelaste la conexión. Podés intentarlo de nuevo desde Canales.");
      setTimeout(() => router.push("/canales"), 3000);
      return;
    }

    if (!code || !state) {
      setStatus("error");
      setMessage("Parámetros inválidos en el callback.");
      setTimeout(() => router.push("/canales"), 3000);
      return;
    }

    // Decodificar state: "platform:workspace_id"
    const [platform, workspaceIdStr] = state.split(":");
    const workspaceId = parseInt(workspaceIdStr ?? "", 10);

    if (!platform || isNaN(workspaceId)) {
      setStatus("error");
      setMessage("Estado del callback inválido.");
      setTimeout(() => router.push("/canales"), 3000);
      return;
    }

    // Restaurar token desde localStorage (puede haberse perdido con la navegación)
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (token) {
      document.cookie = `access_token=${token}; path=/; max-age=3600`;
    }

    const redirectUri = `${window.location.origin}/oauth/callback`;

    setMessage(`Conectando tu cuenta de ${platform}…`);

    api.channels
      .oauthCallback(workspaceId, platform, code, redirectUri)
      .then(({ channel }) => {
        setChannelName(channel.alias || channel.remote_username || "tu cuenta");
        setStatus("success");
        setMessage(`¡Listo! Tu cuenta fue conectada exitosamente.`);
        setTimeout(() => router.push("/canales"), 2500);
      })
      .catch((err: Error) => {
        setStatus("error");
        setMessage(err.message || "No se pudo conectar la cuenta.");
        setTimeout(() => router.push("/canales"), 4000);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="max-w-sm w-full text-center space-y-6">
        {status === "loading" && (
          <>
            <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
            <div>
              <h2 className="text-xl font-semibold">Conectando…</h2>
              <p className="text-muted-foreground text-sm mt-1">{message}</p>
            </div>
          </>
        )}

        {status === "success" && (
          <>
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto" />
            <div>
              <h2 className="text-xl font-semibold text-green-700 dark:text-green-400">
                ¡Conectado!
              </h2>
              <p className="text-muted-foreground text-sm mt-1">
                {channelName ? `@${channelName}` : "Tu cuenta"} está lista para publicar.
              </p>
              <p className="text-xs text-muted-foreground mt-3">Redirigiendo a Canales…</p>
            </div>
          </>
        )}

        {status === "error" && (
          <>
            <XCircle className="h-12 w-12 text-destructive mx-auto" />
            <div>
              <h2 className="text-xl font-semibold">No se pudo conectar</h2>
              <p className="text-muted-foreground text-sm mt-1">{message}</p>
              <p className="text-xs text-muted-foreground mt-3">Volviendo a Canales…</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-10 w-10 animate-spin text-primary" />
      </div>
    }>
      <CallbackInner />
    </Suspense>
  );
}
