"use client";

import { useEffect, useState } from "react";
import { RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { api, type Publication, type PublicationJob } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const STATUS_BADGE: Record<string, { label: string; variant: "success" | "destructive" | "warning" | "secondary" | "outline" }> = {
  published: { label: "Publicado", variant: "success" },
  queued: { label: "En cola", variant: "secondary" },
  processing: { label: "Procesando", variant: "secondary" },
  failed: { label: "Error", variant: "destructive" },
  retrying: { label: "Reintentando", variant: "warning" },
  scheduled: { label: "Programado", variant: "outline" },
  draft: { label: "Borrador", variant: "secondary" },
  cancelled: { label: "Cancelado", variant: "secondary" },
};

function PublicationRow({ pub }: { pub: Publication }) {
  const [open, setOpen] = useState(false);
  const [jobs, setJobs] = useState<PublicationJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const { workspace } = useAuthStore();

  const badge = STATUS_BADGE[pub.status] ?? { label: pub.status, variant: "outline" as const };
  const pct = pub.total_jobs > 0 ? Math.round((pub.jobs_published / pub.total_jobs) * 100) : 0;

  const toggleOpen = async () => {
    setOpen(!open);
    if (!open && jobs.length === 0 && workspace) {
      setLoadingJobs(true);
      try {
        const { jobs: j } = await api.publications.getJobs(workspace.id, pub.id);
        setJobs(j);
      } finally {
        setLoadingJobs(false);
      }
    }
  };

  return (
    <div className="border-b last:border-b-0">
      <button
        className="w-full p-4 flex items-center gap-3 text-left hover:bg-muted/30 transition-colors"
        onClick={toggleOpen}
      >
        {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">
            Publicación #{pub.id}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {pub.total_jobs} canales · {pub.jobs_published} publicados · {pub.jobs_failed} fallidos
            {pub.scheduled_at ? ` · Programado: ${new Date(pub.scheduled_at).toLocaleString("es-AR")}` : ""}
          </p>
          {pub.caption && (
            <p className="text-xs text-muted-foreground truncate mt-0.5 max-w-md">
              {pub.caption.slice(0, 100)}{pub.caption.length > 100 ? "…" : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs font-semibold">{pct}%</span>
          <Badge variant={badge.variant}>{badge.label}</Badge>
        </div>
      </button>

      {open && (
        <div className="bg-muted/30 px-4 pb-4">
          {loadingJobs ? (
            <p className="text-xs text-muted-foreground py-2">Cargando…</p>
          ) : jobs.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">Sin trabajos</p>
          ) : (
            <div className="space-y-1 pt-2">
              {jobs.map((j) => {
                const jb = STATUS_BADGE[j.status] ?? { label: j.status, variant: "outline" as const };
                return (
                  <div key={j.id} className="flex items-center gap-2 text-xs">
                    <span className="capitalize text-muted-foreground w-20 shrink-0">{j.platform}</span>
                    <Badge variant={jb.variant} className="text-xs py-0">{jb.label}</Badge>
                    {j.remote_id && <span className="text-muted-foreground">ID: {j.remote_id}</span>}
                    {j.error_message && (
                      <span className="text-destructive truncate max-w-xs">{j.error_message}</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function HistorialPage() {
  const { workspace } = useAuthStore();
  const [publications, setPublications] = useState<Publication[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const LIMIT = 20;

  const load = (offset = 0) => {
    if (!workspace) return;
    setLoading(true);
    api.publications
      .list(workspace.id, { limit: LIMIT, offset })
      .then((r) => {
        if (offset === 0) setPublications(r.publications);
        else setPublications((prev) => [...prev, ...r.publications]);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspace]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Historial</h1>
          <p className="text-muted-foreground">Todas tus publicaciones pasadas</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => load()} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      <div className="bg-card border rounded-xl overflow-hidden">
        {loading && publications.length === 0 ? (
          <div className="p-8 text-center">
            <div className="h-4 bg-muted rounded animate-pulse mb-2" />
            <div className="h-4 bg-muted rounded animate-pulse w-3/4" />
          </div>
        ) : publications.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <p className="text-sm">No hay publicaciones aún.</p>
          </div>
        ) : (
          <div>
            {publications.map((p) => <PublicationRow key={p.id} pub={p} />)}
            <div className="p-3 text-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setPage((p) => p + 1);
                  load(page * LIMIT + LIMIT);
                }}
                disabled={loading}
              >
                {loading ? "Cargando…" : "Cargar más"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
