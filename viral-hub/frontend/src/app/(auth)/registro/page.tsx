import type { Metadata } from "next";

export const metadata: Metadata = { title: "Crear cuenta" };

export default function RegistroPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md space-y-8 p-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight">Viral Hub</h1>
          <p className="mt-2 text-muted-foreground">Creá tu cuenta y empezá a distribuir</p>
        </div>

        <div className="bg-card border rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold">Crear cuenta</h2>
          <p className="text-sm text-muted-foreground">
            Formulario de registro — pendiente de implementar
          </p>
          <a href="/login" className="block text-sm text-primary hover:underline">
            ¿Ya tenés cuenta? Iniciá sesión
          </a>
        </div>
      </div>
    </div>
  );
}
