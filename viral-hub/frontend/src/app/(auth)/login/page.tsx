import type { Metadata } from "next";

export const metadata: Metadata = { title: "Iniciar sesión" };

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md space-y-8 p-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight">Viral Hub</h1>
          <p className="mt-2 text-muted-foreground">
            Tu contenido. Todos tus canales. Un solo lugar.
          </p>
        </div>

        {/* TODO: implementar formulario con react-hook-form + zod */}
        <div className="bg-card border rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold">Iniciar sesión</h2>
          <p className="text-sm text-muted-foreground">
            Formulario de login — pendiente de implementar con componentes shadcn/ui
          </p>
          <a
            href="/registro"
            className="block text-sm text-primary hover:underline"
          >
            ¿No tenés cuenta? Registrate
          </a>
        </div>
      </div>
    </div>
  );
}
