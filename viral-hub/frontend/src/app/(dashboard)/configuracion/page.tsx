import type { Metadata } from "next";
export const metadata: Metadata = { title: "Configuración" };
export default function ConfiguracionPage() {
  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">Configuración</h1>
        <p className="text-muted-foreground">Workspace, plan y usuario</p>
      </div>

      {["Workspace", "Plan y suscripción", "Equipo", "Notificaciones", "Perfil"].map((section) => (
        <div key={section} className="bg-card border rounded-lg p-4">
          <h2 className="font-semibold mb-2">{section}</h2>
          <p className="text-sm text-muted-foreground">Pendiente de implementar</p>
        </div>
      ))}
    </div>
  );
}
