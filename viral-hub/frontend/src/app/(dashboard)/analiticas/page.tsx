"use client";

import { useEffect, useState } from "react";
import { TrendingUp, Eye, ThumbsUp, Share2, MessageSquare, RefreshCw } from "lucide-react";
import { api, type Publication } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";

function MetricCard({
  label,
  value,
  icon: Icon,
  color = "",
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <div className="bg-card border rounded-xl p-4 space-y-2">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className={`h-4 w-4 ${color}`} />
        {label}
      </div>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function AnaliticasPage() {
  const { workspace } = useAuthStore();
  const [publications, setPublications] = useState<Publication[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    if (!workspace) return;
    setLoading(true);
    api.publications
      .list(workspace.id, { status: "published", limit: 100 })
      .then((r) => setPublications(r.publications))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspace]);

  // Aggregate metrics from all publication jobs' snapshots
  const totals = publications.reduce(
    (acc, p) => ({
      views: acc.views + (p.total_views ?? 0),
      likes: acc.likes + (p.total_likes ?? 0),
      shares: acc.shares + (p.total_shares ?? 0),
      comments: acc.comments + (p.total_comments ?? 0),
      published: acc.published + p.jobs_published,
    }),
    { views: 0, likes: 0, shares: 0, comments: 0, published: 0 }
  );

  const engagementRate =
    totals.views > 0
      ? ((totals.likes + totals.shares + totals.comments) / totals.views * 100).toFixed(2) + "%"
      : "—";

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analíticas</h1>
          <p className="text-muted-foreground">
            Métricas agregadas de tus publicaciones
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-24 bg-muted rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <MetricCard label="Publicaciones" value={totals.published} icon={TrendingUp} color="text-blue-600" />
            <MetricCard label="Visualizaciones" value={formatNum(totals.views)} icon={Eye} />
            <MetricCard label="Me gusta" value={formatNum(totals.likes)} icon={ThumbsUp} color="text-red-500" />
            <MetricCard label="Compartidos" value={formatNum(totals.shares)} icon={Share2} color="text-green-600" />
            <MetricCard label="Comentarios" value={formatNum(totals.comments)} icon={MessageSquare} color="text-purple-600" />
            <MetricCard label="Engagement" value={engagementRate} icon={TrendingUp} color="text-orange-500" />
          </div>

          {publications.length === 0 ? (
            <div className="bg-card border rounded-xl p-8 text-center text-muted-foreground">
              <TrendingUp className="h-8 w-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">Aún no hay datos. Publicá contenido para ver métricas aquí.</p>
            </div>
          ) : (
            <div className="bg-card border rounded-xl overflow-hidden">
              <div className="p-4 border-b font-semibold text-sm">
                Rendimiento por publicación
              </div>
              <div className="divide-y">
                {publications.slice(0, 20).map((p) => {
                  const pViews = p.total_views ?? 0;
                  const pEng =
                    pViews > 0
                      ? (((p.total_likes ?? 0) + (p.total_shares ?? 0) + (p.total_comments ?? 0)) / pViews * 100).toFixed(1)
                      : "—";
                  return (
                    <div key={p.id} className="p-4 flex items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">Pub #{p.id}</p>
                        <p className="text-xs text-muted-foreground truncate">
                          {p.caption?.slice(0, 60) ?? "(sin descripción)"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {p.jobs_published} canales · {pViews > 0 ? formatNum(pViews) + " vistas" : "sin datos de vistas"}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-sm font-semibold">{pEng}%</p>
                        <p className="text-xs text-muted-foreground">engagement</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      <p className="text-xs text-muted-foreground">
        💡 Las métricas se actualizan automáticamente cada hora mediante el worker de métricas (<code>worker_metrics</code>).
        Activá el colector ejecutando el stack de Celery con <code>CELERY_BEAT=1</code>.
      </p>
    </div>
  );
}
