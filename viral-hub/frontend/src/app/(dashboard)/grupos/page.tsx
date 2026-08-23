import type { Metadata } from "next";
export const metadata: Metadata = { title: "Grupos" };
export default function GruposPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Grupos</h1>
          <p className="text-muted-foreground">Organizá canales para publicar en bloque</p>
        </div>
        <button className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-primary/90">
          + Nuevo grupo
        </button>
      </div>
      <div className="bg-card border rounded-lg p-8 text-center text-muted-foreground">
        <p className="text-sm">No hay grupos aún. El grupo "Todas" se crea automáticamente cuando conectás canales.</p>
      </div>
    </div>
  );
}
