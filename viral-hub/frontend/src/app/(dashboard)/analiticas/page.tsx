import type { Metadata } from "next";
export const metadata: Metadata = { title: "Analíticas" };
export default function AnaliticasPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analíticas</h1>
        <p className="text-muted-foreground">Métricas de tus publicaciones</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {["Vistas totales", "Likes", "Comentarios", "Compartidos"].map((m) => (
          <div key={m} className="bg-card border rounded-lg p-4">
            <p className="text-sm text-muted-foreground">{m}</p>
            <p className="text-2xl font-bold mt-1">—</p>
          </div>
        ))}
      </div>
      <div className="bg-card border rounded-lg p-8 text-center text-muted-foreground">
        <p className="text-sm">Las métricas se mostrarán cuando tengas publicaciones exitosas.</p>
        <p className="text-xs mt-1">Los datos se sincronizan automáticamente desde cada plataforma.</p>
      </div>
    </div>
  );
}
