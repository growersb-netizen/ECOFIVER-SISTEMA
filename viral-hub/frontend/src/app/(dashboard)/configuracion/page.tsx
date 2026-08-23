"use client";

import { useState } from "react";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

export default function ConfiguracionPage() {
  const { user, workspace, logout } = useAuthStore();
  const [msg, setMsg] = useState("");

  const handleUpdateWorkspace = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const name = (e.currentTarget.elements.namedItem("name") as HTMLInputElement).value;
    if (!workspace) return;
    await api.workspaces.update(workspace.id, name);
    setMsg("✅ Workspace actualizado");
  };

  return (
    <div className="p-6 max-w-xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Configuración</h1>
        <p className="text-muted-foreground">Administrá tu cuenta y workspace</p>
      </div>

      {/* Info de usuario */}
      <div className="bg-card border rounded-xl p-5 space-y-3">
        <h2 className="font-semibold text-sm">Tu cuenta</h2>
        <div className="text-sm space-y-1">
          <p><span className="text-muted-foreground">Nombre:</span> {user?.full_name ?? "—"}</p>
          <p><span className="text-muted-foreground">Email:</span> {user?.email ?? "—"}</p>
          {user?.is_superadmin && (
            <p className="text-primary font-medium text-xs">✨ Superadmin</p>
          )}
        </div>
      </div>

      {/* Workspace */}
      <div className="bg-card border rounded-xl p-5 space-y-4">
        <h2 className="font-semibold text-sm">Workspace</h2>
        <form onSubmit={handleUpdateWorkspace} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="name">Nombre del workspace</Label>
            <Input id="name" name="name" defaultValue={workspace?.name ?? ""} />
          </div>
          <Button type="submit" size="sm">Guardar</Button>
        </form>
        {msg && <p className="text-sm text-muted-foreground">{msg}</p>}
        <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t">
          <p>Slug: <code className="bg-muted px-1 rounded">{workspace?.slug ?? "—"}</code></p>
          <p>Plan: <code className="bg-muted px-1 rounded">{workspace?.plan ?? "—"}</code></p>
        </div>
      </div>

      {/* Stack info */}
      <div className="bg-card border rounded-xl p-5 space-y-2 text-sm">
        <h2 className="font-semibold text-sm mb-2">Stack & Deployment</h2>
        <div className="text-muted-foreground space-y-1 text-xs">
          <p>🖥 Backend: <strong>FastAPI (Python)</strong> · Railway</p>
          <p>🗄 DB: <strong>PostgreSQL</strong> · Railway managed</p>
          <p>⚡ Queue: <strong>Celery + Redis</strong> · Railway</p>
          <p>📦 Storage: <strong>Cloudflare R2</strong></p>
          <p>🌐 Frontend: <strong>Next.js 14</strong> · Vercel</p>
          <p>🌸 Worker UI: <strong>Flower</strong> (port 5555)</p>
        </div>
      </div>

      {/* Cerrar sesión */}
      <Button
        variant="destructive"
        onClick={() => { logout(); window.location.href = "/login"; }}
      >
        Cerrar sesión
      </Button>
    </div>
  );
}
