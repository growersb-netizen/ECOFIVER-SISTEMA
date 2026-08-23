import type { Metadata } from "next";
export const metadata: Metadata = { title: "Historial" };
export default function HistorialPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Historial</h1>
        <p className="text-muted-foreground">Todas las publicaciones realizadas</p>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap">
        <select className="border rounded-md px-3 py-1.5 text-sm bg-background">
          <option>Todas las plataformas</option>
          <option>Instagram</option>
          <option>TikTok</option>
          <option>YouTube</option>
          <option>Facebook</option>
        </select>
        <select className="border rounded-md px-3 py-1.5 text-sm bg-background">
          <option>Todos los estados</option>
          <option>Publicados</option>
          <option>Fallidos</option>
          <option>Programados</option>
        </select>
      </div>

      <div className="bg-card border rounded-lg p-8 text-center text-muted-foreground">
        <p className="text-sm">No hay publicaciones en el historial.</p>
      </div>
    </div>
  );
}
