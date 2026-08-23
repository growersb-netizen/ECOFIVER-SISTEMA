"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Zap, Tv2, Send, AlertTriangle, ListOrdered } from "lucide-react";
import { api, type DashboardStats } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Badge } from "@/components/ui/badge";

function StatCard({
  label,
  value,
  icon: Icon,
  href,
  color = "text-foreground",
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  href?: string;
  color?: string;
}) {
  const content = (
    <div className="bg-card border rounded-xl p-4 hover:border-primary/50 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm text-muted-foreground">{label}</p>
        <Icon className={`h-4 w-4 ${color}`} />
      </div>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
    </div>
  );
  return href ? <Link href={href}>{content}</Link> : content;
}

const STATUS_BADGE: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "secondary" | "outline" }> = {
  published: { label: "✓ Publicado", variant: "success" },
  queued: { label: "En cola", variant: "secondary" },
  processing: { label: "Procesando", variant: "secondary" },
  failed: { label: "Error", variant: "destructive" },
  retrying: { label: "Reintentando", variant: "warning" },
  scheduled: { label: "Programado", variant: "outline" },
};

export default function DashboardPage() {
  const { workspace } = useAuthStore();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!workspace) return;
    api.workspaces
      .stats(workspace.id)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [workspace]);

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-48" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => <div key={i} className="h-24 bg-muted rounded-xl" />)}
          </div>
        </div>
      </div>
    );
  }

  const s = stats ?? { channels_connected: 0, published_today: 0, in_queue: 0, with_errors: 0, recent_publications: [] };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">
          {workspace?.name ?? "Cargando..."} — resumen operativo
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Canales conectados" value={s.channels_connected} icon={Tv2} href="/canales" />
        <StatCard label="Publicados hoy" value={s.published_today} icon={Send} color="text-green-600" />
        <StatCard label="En cola" value={s.in_queue} icon={ListOrdered} href="/cola" color="text-blue-600" />
        <StatCard
          label="Con errores"
          value={s.with_errors}
          icon={AlertTriangle}
          href="/cola"
          color={s.with_errors > 0 ? "text-red-600" : "text-foreground"}
        />
      </div>

      {/* CTA cuando no hay canales */}
      {s.channels_connected === 0 && (
        <div className="bg-primary/5 border border-primary/20 rounded-xl p-6 flex items-center gap-4">
          <div className="bg-primary rounded-lg p-3 shrink-0">
            <Zap className="h-6 w-6 text-primary-foreground" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold">¡Empezá conectando tus canales!</h3>
            <p className="text-sm text-muted-foreground mt-0.5">
              Conectá Instagram, TikTok, YouTube o Facebook para poder distribuir contenido.
            </p>
          </div>
          <Link
            href="/canales"
            className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-primary/90 shrink-0"
          >
            Agregar canal
          </Link>
        </div>
      )}

      {/* Últimas publicaciones */}
      <div className="bg-card border rounded-xl overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h2 className="font-semibold">Últimas publicaciones</h2>
          <Link href="/historial" className="text-xs text-primary hover:underline">
            Ver todo
          </Link>
        </div>

        {s.recent_publications.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <p className="text-sm">No hay publicaciones aún.</p>
            <Link href="/publicar" className="text-sm text-primary hover:underline mt-1 block">
              Crear primera publicación →
            </Link>
          </div>
        ) : (
          <div className="divide-y">
            {s.recent_publications.map((p) => {
              const badge = STATUS_BADGE[p.status] ?? { label: p.status, variant: "outline" as const };
              const pct = p.total_jobs > 0 ? Math.round((p.jobs_published / p.total_jobs) * 100) : 0;
              return (
                <div key={p.id} className="p-4 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">Publicación #{p.id}</p>
                    <p className="text-xs text-muted-foreground">
                      {p.total_jobs} canales · {p.jobs_published} publicados · {p.jobs_failed} fallidos
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-sm font-semibold">{pct}%</span>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
