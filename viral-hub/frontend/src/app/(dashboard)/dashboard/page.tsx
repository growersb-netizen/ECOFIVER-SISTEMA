import type { Metadata } from "next";

export const metadata: Metadata = { title: "Dashboard" };

// Stats card component
function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-card border rounded-lg p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Resumen operativo</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Canales conectados" value="—" sub="Conectá tu primer canal" />
        <StatCard label="Publicaciones hoy" value="0" />
        <StatCard label="En cola" value="0" />
        <StatCard label="Errores" value="0" />
      </div>

      {/* Últimas publicaciones */}
      <div className="bg-card border rounded-lg">
        <div className="p-4 border-b">
          <h2 className="font-semibold">Últimas publicaciones</h2>
        </div>
        <div className="p-8 text-center text-muted-foreground">
          <p className="text-sm">Aún no hay publicaciones.</p>
          <a href="/publicar" className="text-sm text-primary hover:underline mt-2 block">
            Crear tu primera publicación →
          </a>
        </div>
      </div>
    </div>
  );
}
