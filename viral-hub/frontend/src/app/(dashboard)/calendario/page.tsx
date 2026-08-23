import type { Metadata } from "next";
export const metadata: Metadata = { title: "Calendario" };
export default function CalendarioPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Calendario</h1>
        <p className="text-muted-foreground">Visualizá y programá publicaciones</p>
      </div>
      <div className="bg-card border rounded-lg p-8 text-center text-muted-foreground">
        <p className="text-sm">Vista de calendario — pendiente de implementar con date-fns</p>
      </div>
    </div>
  );
}
