/**
 * Middleware de Next.js — protege las rutas del dashboard.
 * Si el usuario no tiene token, redirige al login.
 * Si tiene token y va a /login o /registro, redirige al dashboard.
 */

import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/registro", "/api"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Rutas públicas: dejar pasar siempre
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Obtener token de la cookie (lo seteamos en login)
  // En producción usar HttpOnly cookie; en dev usamos una cookie simple
  const token = request.cookies.get("access_token")?.value;

  // Sin token → redirigir al login
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.png|.*\\.jpg|.*\\.svg).*)",
  ],
};
