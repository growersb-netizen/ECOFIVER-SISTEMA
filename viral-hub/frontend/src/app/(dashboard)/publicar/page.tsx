import type { Metadata } from "next";
export const metadata: Metadata = { title: "Publicar" };

/**
 * Compositor de publicación — flujo principal del producto.
 * Flujo: seleccionar contenido → seleccionar destinos → captions → publicar/programar
 *
 * TODO: implementar con react-hook-form, componentes shadcn/ui y SWR para
 *       cargar assets y canales en tiempo real.
 */
export default function PublicarPage() {
  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Publicar</h1>
        <p className="text-muted-foreground">Distribuí tu contenido a todos tus canales</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Paso 1: Contenido */}
        <div className="bg-card border rounded-lg p-4 space-y-3">
          <h2 className="font-semibold flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">1</span>
            Contenido
          </h2>
          <div className="border-2 border-dashed rounded-lg p-8 text-center text-muted-foreground text-sm">
            Seleccioná de biblioteca o arrastrá un archivo acá
          </div>
        </div>

        {/* Paso 2: Destinos */}
        <div className="bg-card border rounded-lg p-4 space-y-3">
          <h2 className="font-semibold flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">2</span>
            Destinos
          </h2>
          <p className="text-sm text-muted-foreground">
            Seleccioná grupos o canales individuales
          </p>
          <div className="text-center py-4 text-sm text-muted-foreground">
            No hay canales conectados — <a href="/canales" className="text-primary hover:underline">agregar canales</a>
          </div>
        </div>
      </div>

      {/* Paso 3: Captions */}
      <div className="bg-card border rounded-lg p-4 space-y-3">
        <h2 className="font-semibold flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">3</span>
          Textos por plataforma
        </h2>
        <p className="text-sm text-muted-foreground">
          Podés escribir un texto general o personalizarlo por red social.
        </p>
        <div className="space-y-2">
          <textarea
            placeholder="Texto general (se aplica a todas las plataformas)"
            className="w-full border rounded-md p-3 text-sm min-h-[80px] bg-background resize-none"
          />
        </div>
      </div>

      {/* Acciones */}
      <div className="flex gap-3 pt-2">
        <button className="bg-primary text-primary-foreground px-6 py-2 rounded-md font-medium hover:bg-primary/90">
          Publicar ahora
        </button>
        <button className="border px-6 py-2 rounded-md font-medium hover:bg-accent text-sm">
          Programar
        </button>
        <button className="border px-6 py-2 rounded-md font-medium hover:bg-accent text-sm">
          Agregar a cola
        </button>
      </div>
    </div>
  );
}
