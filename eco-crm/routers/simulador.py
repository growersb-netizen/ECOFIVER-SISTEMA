"""
Simulador de cuotas unificado — EcoFiver.
Fórmula propia: cuota = precio_lista / (n + factor)
  factor = 2  para módulos habitacionales, piscinas y combos
  (el "precio" recibido por este endpoint debe ser el precio de LISTA,
  no el de contado — el financiado siempre se calcula sobre la lista)

Endpoint público: GET /api/simulador/cuotas
Endpoint autenticado: GET /api/simulador/tabla (tabla completa)
"""
import math
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

router = APIRouter()

FACTOR_MODULOS = 2.0
FACTOR_PISCINAS = 2.0

PLAZOS_DEFAULT = [6, 12, 18, 24, 36, 48]


def calcular_cuota(precio: float, n: int, factor: float) -> float:
    """Cuota mensual según la fórmula de EcoFiver."""
    return precio / (n + factor)


def tabla_cuotas(precio: float, tipo: str) -> list[dict]:
    """Devuelve tabla de cuotas para todos los plazos."""
    factor = FACTOR_MODULOS if tipo.upper() == "MODULO" else FACTOR_PISCINAS
    rows = []
    for n in PLAZOS_DEFAULT:
        cuota = calcular_cuota(precio, n, factor)
        ingreso_inicial = factor * cuota
        rows.append({
            "cuotas": n,
            "cuota_mensual": round(cuota),
            "ingreso_inicial": round(ingreso_inicial),
            "total": round(ingreso_inicial + cuota * n),
        })
    return rows


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.get("/api/simulador/cuotas")
async def simular_cuotas(
    tipo: str = "MODULO",
    precio: float = 0,
    cuotas: Optional[int] = None,
):
    """
    Simulación de cuotas — acceso público (usado por web y agentes IA).

    Params:
      tipo:   MODULO | PISCINA | COMBO
      precio: precio de LISTA (ARS) — el monto que se financia
      cuotas: número específico de cuotas (opcional; si no se pasa, devuelve tabla completa)
    """
    if precio <= 0:
        raise HTTPException(400, "El precio debe ser mayor a 0")

    tipo_norm = tipo.upper()
    if tipo_norm not in ("MODULO", "PISCINA", "COMBO"):
        tipo_norm = "MODULO"

    # Módulos, piscinas y combos usan el mismo factor de ingreso (2 cuotas).
    factor = FACTOR_MODULOS if tipo_norm == "MODULO" else FACTOR_PISCINAS

    if cuotas:
        cuota = calcular_cuota(precio, cuotas, factor)
        ingreso_inicial = factor * cuota
        return {
            "tipo": tipo_norm,
            "precio_contado": precio,
            "cuotas": cuotas,
            "factor": factor,
            "cuota_mensual": round(cuota),
            "ingreso_inicial": round(ingreso_inicial),
            "total": round(ingreso_inicial + cuota * cuotas),
        }
    else:
        return {
            "tipo": tipo_norm,
            "precio_contado": precio,
            "factor": factor,
            "tabla": tabla_cuotas(precio, tipo_norm),
        }


@router.get("/api/simulador/tabla-completa")
async def tabla_completa(
    tipo: str = "MODULO",
    precio: float = 0,
):
    """Tabla completa de cuotas para todos los plazos. Público."""
    if precio <= 0:
        raise HTTPException(400, "El precio debe ser mayor a 0")
    tipo_norm = tipo.upper() if tipo.upper() in ("MODULO", "PISCINA", "COMBO") else "MODULO"
    return {
        "tipo": tipo_norm,
        "precio_contado": precio,
        "plazos": tabla_cuotas(precio, tipo_norm),
    }
