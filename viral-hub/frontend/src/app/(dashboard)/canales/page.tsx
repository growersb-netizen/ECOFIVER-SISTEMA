import type { Metadata } from "next";

export const metadata: Metadata = { title: "Canales" };

const PLATFORMS = [
  { id: "instagram", name: "Instagram", color: "bg-pink-500", description: "Reels y contenido" },
  { id: "tiktok", name: "TikTok", color: "bg-black", description: "Videos cortos" },
  { id: "youtube", name: "YouTube", color: "bg-red-500", description: "YouTube Shorts" },
  { id: "facebook", name: "Facebook", color: "bg-blue-600", description: "Páginas y videos" },
];

export default function CanalesPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Canales</h1>
          <p className="text-muted-foreground">Conectá y administrá tus cuentas sociales</p>
        </div>
        <button className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-primary/90">
          + Agregar canal
        </button>
      </div>

      {/* Canales conectados */}
      <div className="bg-card border rounded-lg">
        <div className="p-4 border-b">
          <h2 className="font-semibold">Canales conectados</h2>
        </div>
        <div className="p-8 text-center text-muted-foreground">
          <p className="text-sm">No hay canales conectados aún.</p>
          <p className="text-xs mt-1">Conectá tu primera cuenta usando el botón de arriba.</p>
        </div>
      </div>

      {/* Plataformas disponibles */}
      <div>
        <h2 className="font-semibold mb-3">Plataformas disponibles</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {PLATFORMS.map((p) => (
            <button
              key={p.id}
              className="bg-card border rounded-lg p-4 text-left hover:border-primary transition-colors"
            >
              <div className={`w-8 h-8 rounded-full ${p.color} mb-2`} />
              <p className="font-medium text-sm">{p.name}</p>
              <p className="text-xs text-muted-foreground">{p.description}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
