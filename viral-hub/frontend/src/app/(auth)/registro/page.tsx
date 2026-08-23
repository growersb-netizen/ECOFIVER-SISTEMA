"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Zap, Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function RegistroPage() {
  const router = useRouter();
  const { register, isLoading, error, clearError } = useAuthStore();

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    workspace_name: "",
  });
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    clearError();
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password.length < 8) {
      return;
    }
    try {
      await register(form);
      document.cookie = `access_token=${localStorage.getItem("access_token")}; path=/; max-age=3600`;
      router.push("/dashboard");
    } catch {}
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="flex items-center justify-center gap-2">
            <div className="bg-primary rounded-lg p-2">
              <Zap className="h-6 w-6 text-primary-foreground" />
            </div>
            <span className="text-2xl font-bold">Viral Hub</span>
          </div>
          <p className="text-muted-foreground text-sm">Creá tu cuenta y empezá a distribuir</p>
        </div>

        {/* Formulario */}
        <div className="bg-card border rounded-xl p-6 shadow-sm space-y-4">
          <h2 className="text-xl font-semibold text-center">Crear cuenta</h2>

          {error && (
            <div className="bg-destructive/10 text-destructive text-sm rounded-md p-3 border border-destructive/20">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="full_name">Nombre completo</Label>
              <Input
                id="full_name"
                name="full_name"
                placeholder="Tu nombre"
                value={form.full_name}
                onChange={handleChange}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                placeholder="tu@email.com"
                value={form.email}
                onChange={handleChange}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Contraseña</Label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Mínimo 8 caracteres"
                  value={form.password}
                  onChange={handleChange}
                  required
                  minLength={8}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="workspace_name">Nombre de tu workspace</Label>
              <Input
                id="workspace_name"
                name="workspace_name"
                placeholder="Ej: Mi Canal de Clips"
                value={form.workspace_name}
                onChange={handleChange}
                required
              />
              <p className="text-xs text-muted-foreground">
                Podés cambiarlo después en Configuración
              </p>
            </div>

            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creando cuenta...
                </>
              ) : (
                "Crear cuenta"
              )}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            ¿Ya tenés cuenta?{" "}
            <Link href="/login" className="text-primary hover:underline font-medium">
              Iniciá sesión
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
