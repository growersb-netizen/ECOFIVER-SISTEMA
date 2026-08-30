"use client";
// Redirige al nuevo panel de MercadoLibre
import { useEffect } from "react";
export default function MLRedirect() {
  useEffect(() => { window.location.href = "/dashboard/mercadolibre"; }, []);
  return null;
}
