import type { Metadata } from "next";
export const metadata: Metadata = { title: "Cola" };

const STATUS_COLORS: Record<string, string> = {
  queued: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  published: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  retrying: "bg-orange-100 text-orange-800",
};

export default function ColaPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cola</h1>
          <p className="text-muted-foreground">Trabajos pendientes de publicación</p>
        </div>
        <div className="flex gap-2">
          <button className="border px-3 py-1.5 rounded-md text-sm hover:bg-accent">
            Reintentar errores
          </button>
          <button className="border px-3 py-1.5 rounded-md text-sm hover:bg-accent">
            Pausar cola
          </button>
        </div>
      </div>

      {/* Filtros de estado */}
      <div className="flex gap-2 flex-wrap">
        {["Todos", "En cola", "Procesando", "Fallidos", "Reintentando"].map((f) => (
          <button key={f} className="px-3 py-1 text-sm border rounded-full hover:bg-accent">
            {f}
          </button>
        ))}
      </div>

      <div className="bg-card border rounded-lg p-8 text-center text-muted-foreground">
        <p className="text-sm">No hay trabajos en la cola.</p>
      </div>
    </div>
  );
}
