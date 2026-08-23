"use client";

import { useEffect, useState } from "react";
import { RefreshCw, RotateCcw, AlertCircle, CheckCircle, Clock, Loader2 } from "lucide-react";
import { api, type PublicationJob } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const JOB_STATUS = {
  queued: { label: "En cola", icon: Clock, variant: "secondary" as const },
  processing: { label: "Procesando", icon: Loader2, variant: "secondary" as const },
  published: { label: "Publicado", icon: CheckCircle, variant: "success" as const },
  failed: { label: "Error", icon: AlertCircle, variant: "destructive" as const },
  retrying: { label: "Reintentando", icon: RefreshCw, variant: "warning" as const },
  scheduled: { label: "Programado", icon: Clock, variant: "outline" as const },
  needs_reconnect: { label: "Reconectar", icon: AlertCircle, variant: "warning" as const },
  cancelled: { label: "Cancelado", icon: AlertCircle, variant: "secondary" as const },
};

function JobRow({ job, onRetry }: { job: PublicationJob; onRetry: () => void }) {
  const cfg = JOB_STATUS[job.status as keyof typeof JOB_STATUS] ?? JOB_STATUS.failed;
  const Icon = cfg.icon;
  const canRetry = job.status === "failed" || job.status === "needs_reconnect";

  return (
    <div className="p-4 flex items-center gap-3">
      <div className="shrink-0">
        <Icon className={`h-4 w-4 ${job.status === "processing" ? "animate-spin" : ""}`} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium capitalize">{job.platform}</p>
        <p className="text-xs text-muted-foreground truncate">
          Job #{job.id} · Pub #{job.publication_id}
          {job.remote_id ? ` · ID remoto: ${job.remote_id}` : ""}
        </p>
        {job.error_message && (
          <p className="text-xs text-destructive mt-0.5 truncate">{job.error_message}</p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Badge variant={cfg.variant}>
          <Icon className="h-3 w-3 mr-1" />
          {cfg.label}
        </Badge>
        {canRetry && (
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={onRetry}>
            <RotateCcw className="h-3 w-3 mr-1" />
            Reintentar
          </Button>
        )}
      </div>
    </div>
  );
}

export default function ColaPage() {
  const { workspace } = useAuthStore();
  const [jobs, setJobs] = useState<PublicationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "active" | "failed">("all");

  const load = () => {
    if (!workspace) return;
    setLoading(true);
    api.publications
      .list(workspace.id, { limit: 100 })
      .then(async (pubs) => {
        // Get jobs for each publication
        const allJobs: PublicationJob[] = [];
        for (const pub of pubs.publications.slice(0, 20)) {
          try {
            const { jobs } = await api.publications.getJobs(workspace.id, pub.id);
            allJobs.push(...jobs);
          } catch {}
        }
        setJobs(allJobs);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspace]);

  const handleRetry = async (jobId: number) => {
    if (!workspace) return;
    await api.publications.retryJob(workspace.id, jobId);
    setJobs((prev) =>
      prev.map((j) => (j.id === jobId ? { ...j, status: "queued" } : j))
    );
  };

  const filtered = jobs.filter((j) => {
    if (filter === "active") return ["queued", "processing", "retrying", "scheduled"].includes(j.status);
    if (filter === "failed") return ["failed", "needs_reconnect"].includes(j.status);
    return true;
  });

  const byStatus = (s: string) => jobs.filter((j) => j.status === s).length;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cola de publicaciones</h1>
          <p className="text-muted-foreground">Estado en tiempo real de tus distribuciones</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {/* Resumen */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "En proceso", count: byStatus("queued") + byStatus("processing") + byStatus("retrying"), color: "text-blue-600" },
          { label: "Publicados", count: byStatus("published"), color: "text-green-600" },
          { label: "Con errores", count: byStatus("failed") + byStatus("needs_reconnect"), color: "text-red-600" },
        ].map((s) => (
          <div key={s.label} className="bg-card border rounded-xl p-3 text-center">
            <p className={`text-2xl font-bold ${s.color}`}>{s.count}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div className="flex gap-2">
        {(["all", "active", "failed"] as const).map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(f)}
          >
            {f === "all" ? "Todos" : f === "active" ? "Activos" : "Con errores"}
          </Button>
        ))}
      </div>

      {/* Lista de jobs */}
      <div className="bg-card border rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center">
            <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <p className="text-sm">No hay trabajos que mostrar.</p>
          </div>
        ) : (
          <div className="divide-y">
            {filtered.map((j) => (
              <JobRow key={j.id} job={j} onRetry={() => handleRetry(j.id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
