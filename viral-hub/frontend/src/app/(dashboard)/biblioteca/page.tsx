import type { Metadata } from "next";
export const metadata: Metadata = { title: "Biblioteca" };
export default function BibliotecaPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Biblioteca</h1>
          <p className="text-muted-foreground">Videos e imágenes listos para distribuir</p>
        </div>
        <button className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-primary/90">
          ↑ Subir archivo
        </button>
      </div>

      {/* Filtros */}
      <div className="flex gap-2">
        {["Todos", "Videos", "Imágenes", "Listos", "Borradores"].map((f) => (
          <button key={f} className="px-3 py-1 text-sm border rounded-full hover:bg-accent">
            {f}
          </button>
        ))}
      </div>

      <div className="bg-card border rounded-lg p-8 text-center text-muted-foreground">
        <p className="text-sm">No hay archivos. Subí tu primer video para empezar a distribuir.</p>
      </div>
    </div>
  );
}
