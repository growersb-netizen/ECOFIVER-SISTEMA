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


def _resolver_precio_lista(tipo_norm: str, modelo: str) -> Optional[float]:
    """
    Busca el precio de LISTA de un modelo en el catálogo (fuente única de verdad).
    Evita el error de pasar por accidente el precio de contado al simulador.
    """
    from routers.catalogo import load_catalogo
    cat = load_catalogo()
    if tipo_norm == "PISCINA":
        return cat["piscinas"].get("precios_lista", {}).get(modelo)
    if tipo_norm == "MODULO":
        return cat["modulos"].get("precios_lista", {}).get(modelo)
    if tipo_norm == "COMBO":
        combo = cat.get("combos", {}).get(modelo)
        return combo.get("precio_lista") if combo else None
    return None


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
    modelo: Optional[str] = None,
    cuotas: Optional[int] = None,
):
    """
    Simulación de cuotas — acceso público (usado por web y agentes IA).

    Params:
      tipo:   MODULO | PISCINA | COMBO
      modelo: (RECOMENDADO) nombre exacto del modelo — el precio de LISTA se
              resuelve automáticamente desde el catálogo, sin riesgo de pasar
              por error el precio de contado.
      precio: precio de LISTA (ARS) — solo si no se pasa "modelo".
      cuotas: número específico de cuotas (opcional; si no se pasa, devuelve tabla completa)
    """
    tipo_norm = tipo.upper()
    if tipo_norm not in ("MODULO", "PISCINA", "COMBO"):
        tipo_norm = "MODULO"

    precio_lista = precio
    resuelto_de_catalogo = False
    if modelo:
        encontrado = _resolver_precio_lista(tipo_norm, modelo)
        if encontrado:
            precio_lista = encontrado
            resuelto_de_catalogo = True
        elif precio <= 0:
            raise HTTPException(404, f"Modelo '{modelo}' no encontrado en el catálogo")

    if precio_lista <= 0:
        raise HTTPException(400, "El precio debe ser mayor a 0")

    # Módulos, piscinas y combos usan el mismo factor de ingreso (2 cuotas).
    factor = FACTOR_MODULOS if tipo_norm == "MODULO" else FACTOR_PISCINAS

    if cuotas:
        cuota = calcular_cuota(precio_lista, cuotas, factor)
        ingreso_inicial = factor * cuota
        return {
            "tipo": tipo_norm,
            "modelo": modelo,
            "precio_lista": precio_lista,
            "resuelto_de_catalogo": resuelto_de_catalogo,
            "cuotas": cuotas,
            "factor": factor,
            "cuota_mensual": round(cuota),
            "ingreso_inicial": round(ingreso_inicial),
            "total": round(ingreso_inicial + cuota * cuotas),
        }
    else:
        return {
            "tipo": tipo_norm,
            "modelo": modelo,
            "precio_lista": precio_lista,
            "resuelto_de_catalogo": resuelto_de_catalogo,
            "factor": factor,
            "tabla": tabla_cuotas(precio_lista, tipo_norm),
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
