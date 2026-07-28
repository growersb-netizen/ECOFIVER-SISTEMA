"""
Simulador de cuotas para productos EcoFiver.

Reglas de ingreso:
  Módulos:  ingreso = 2   cuotas del plan elegido
  Piscinas: ingreso = 1.5 cuotas del plan elegido

Derivación matemática:
  ingreso = factor × cuota
  cuota   = (precio - ingreso) / n
  → ingreso = factor × precio / (n + factor)
  → cuota   = precio / (n + factor)
"""


def _catalogo():
    """Importa el catálogo en cada uso para reflejar cambios del panel sin reiniciar."""
    from agents.catalogo import CATALOGO
    return CATALOGO


def _calcular_plan(precio: float, n_cuotas: int, factor: float) -> dict:
    """
    Calcula ingreso y cuota mensual dado el precio, número de cuotas y factor.

    Returns:
        dict con ingreso, cuota_mensual, monto_financiar
    """
    ingreso        = factor * precio / (n_cuotas + factor)
    cuota_mensual  = precio / (n_cuotas + factor)   # equivalente a (precio - ingreso) / n
    monto_financiar = precio - ingreso
    return {
        "n_cuotas":      n_cuotas,
        "factor":        factor,
        "ingreso":       round(ingreso),
        "cuota_mensual": round(cuota_mensual),
        "monto_financiar": round(monto_financiar),
    }


import re as _re

# Señal que emiten los agentes: [SIMULAR:tipo:precio] o [SIMULAR:tipo:precio:12,24,36]
_SIMULAR_RE = _re.compile(r"\[SIMULAR:([^\]]+)\]", _re.IGNORECASE)


def procesar_simulaciones(texto: str) -> str:
    """
    Reemplaza cada señal [SIMULAR:tipo:precio[:planes]] por el cálculo REAL de cuotas.
    Permite que el agente dé números exactos sin inventar. Si la señal está mal formada,
    la elimina silenciosamente.
    """
    def _rep(m):
        partes = [p.strip() for p in m.group(1).split(":")]
        try:
            tipo = partes[0].lower()
            tipo = "modulo" if "mod" in tipo else "piscina"
            precio = float(_re.sub(r"[^\d.]", "", partes[1]))
            planes = None
            if len(partes) >= 3 and partes[2]:
                planes = [p.strip() for p in partes[2].split(",") if p.strip()]
            if precio <= 0:
                return ""
            return "\n\n" + simular_cuotas(precio, tipo, planes) + "\n"
        except Exception:
            return ""
    return _SIMULAR_RE.sub(_rep, texto).strip()


def simular_cuotas(
    precio: float,
    tipo: str = "piscina",            # "piscina" | "modulo"
    planes_a_mostrar: list[str] | None = None,
) -> str:
    """
    Genera texto formateado con las opciones de financiación.

    Args:
        precio: precio base del producto en pesos
        tipo: "piscina" o "modulo" — define el factor de ingreso
        planes_a_mostrar: lista de claves, ej. ["12","24","36"].
                          Si es None muestra 12/24/36/60.

    Returns:
        String listo para enviar al cliente (WhatsApp o web).
    """
    catalogo = _catalogo()
    planes   = catalogo["planes_financiacion"]
    factor   = catalogo["factor_ingreso_modulos"] if tipo == "modulo" else catalogo["factor_ingreso_piscinas"]

    if planes_a_mostrar is None:
        planes_a_mostrar = ["12", "24", "36", "60"]

    lineas = [f"💰 Opciones de financiación para ${precio:,.0f}:\n"]

    for key in planes_a_mostrar:
        if key not in planes:
            continue
        n = planes[key]["cuotas"]
        r = _calcular_plan(precio, n, factor)
        lineas.append(
            f"  • {n} cuotas: "
            f"Ingreso ${r['ingreso']:,.0f} + "
            f"${r['cuota_mensual']:,.0f}/mes"
        )

    lineas.append("\n📋 Financiación directa — sin banco, sin scoring externo.")
    lineas.append("✅ Precio final cerrado. Sin sorpresas.")

    return "\n".join(lineas)


def simular_cuota_unica(
    precio: float,
    plan: str,
    tipo: str = "piscina",
) -> dict:
    """
    Calcula un solo plan. Útil para cálculos internos de los agentes.

    Args:
        precio: precio base en pesos
        plan: clave del plan, ej. "24"
        tipo: "piscina" o "modulo"

    Returns:
        dict con n_cuotas, ingreso, cuota_mensual, monto_financiar
    """
    catalogo = _catalogo()
    planes   = catalogo["planes_financiacion"]
    if plan not in planes:
        return {}
    factor = catalogo["factor_ingreso_modulos"] if tipo == "modulo" else catalogo["factor_ingreso_piscinas"]
    n = planes[plan]["cuotas"]
    return _calcular_plan(precio, n, factor)


def simular_combo(
    precio_modulo: float,
    precio_piscina: float,
    plan: str = "24",
) -> str:
    """
    Simula cuotas para un combo módulo + piscina con 25% de descuento.
    El combo SOLO está disponible en financiación.
    El ingreso usa el factor de módulos (2 cuotas) por ser combo.
    """
    catalogo     = _catalogo()
    descuento_pct = catalogo["combo_descuento_pct"]
    precio_total  = precio_modulo + precio_piscina
    precio_con_descuento = precio_total * (1 - descuento_pct / 100)

    r = simular_cuota_unica(precio_con_descuento, plan, tipo="modulo")
    if not r:
        return "Plan no disponible."

    return (
        f"🏠🏊 COMBO Módulo + Piscina\n"
        f"  Precio lista: ${precio_total:,.0f}\n"
        f"  Descuento {descuento_pct}%: -${precio_total - precio_con_descuento:,.0f}\n"
        f"  Precio combo: ${precio_con_descuento:,.0f}\n\n"
        f"  Plan {r['n_cuotas']} cuotas:\n"
        f"  Ingreso ${r['ingreso']:,.0f} + ${r['cuota_mensual']:,.0f}/mes\n\n"
        f"  ⚠️ Descuento disponible SOLO en financiación.\n"
        f"  📋 Financiación directa — sin banco."
    )


def _buscar_precio_modelo(tipo: str, modelo: str) -> float | None:
    """Busca el precio de lista real: piscina por nombre de modelo, módulo por m2 financiado."""
    catalogo = _catalogo()
    if not modelo:
        return None
    if tipo == "modulo":
        m = _re.search(r"(\d+)", modelo)
        if not m:
            return None
        m2 = int(m.group(1))
        if m2 not in catalogo["modulos_m2"]:
            return None
        return m2 * catalogo["modulos_precio_m2_financiado"]

    modelo_norm = modelo.strip().lower()
    for p in catalogo["piscinas"]:
        if p["modelo"].strip().lower() == modelo_norm:
            return p["precio"]
    # match parcial si no hay coincidencia exacta (ej. "Playa Abanico" vs "Playa y Abanico")
    for p in catalogo["piscinas"]:
        nombre = p["modelo"].strip().lower()
        if modelo_norm in nombre or nombre in modelo_norm:
            return p["precio"]
    return None


def resolver_financiacion(
    tipo: str = "piscina",
    modelo: str | None = None,
    precio: float | None = None,
    entrada: float | None = None,
    cuota: float | None = None,
    n_cuotas: float | None = None,
) -> dict:
    """
    Resuelve los valores de financiación que falten a partir de los que se
    conocen, usando la relación real (NUNCA a mano, siempre esta cuenta):
        precio = cuota * (n_cuotas + factor)
        entrada = factor * cuota
    Con precio (o modelo, para buscarlo en catálogo) + UNO de {entrada, cuota,
    n_cuotas} alcanza para derivar todo el resto — es álgebra simple, no hace
    falta que el agente calcule nada de memoria.

    Devuelve {"ok": True, "precio", "entrada", "cuota", "n_cuotas", "factor"}
    o {"ok": False, "error": "..."} si no hay suficiente información.
    """
    catalogo = _catalogo()
    tipo = "modulo" if "mod" in (tipo or "").lower() else "piscina"
    factor = catalogo["factor_ingreso_modulos"] if tipo == "modulo" else catalogo["factor_ingreso_piscinas"]

    if precio is None and modelo:
        precio = _buscar_precio_modelo(tipo, modelo)

    if precio is None:
        return {
            "ok": False,
            "error": "No se pudo determinar el precio de lista: falta 'precio' explícito o un 'modelo' que exista en el catálogo.",
        }

    if cuota is None and entrada is not None and entrada > 0:
        cuota = entrada / factor
    if entrada is None and cuota is not None:
        entrada = factor * cuota

    if n_cuotas is None:
        if not cuota:
            return {
                "ok": False,
                "error": "Falta la entrada, la cuota o la cantidad de cuotas — con el precio solo no alcanza para calcular el resto.",
            }
        n_cuotas = round((precio / cuota) - factor)
    else:
        n_cuotas = round(n_cuotas)

    if n_cuotas <= 0:
        return {"ok": False, "error": "La cantidad de cuotas calculada da 0 o negativa — revisá los datos (el ingreso no puede ser mayor o igual al precio de lista)."}

    if cuota is None:
        cuota = precio / (n_cuotas + factor)
        entrada = factor * cuota

    return {
        "ok": True,
        "precio": round(precio),
        "entrada": round(entrada),
        "cuota": round(cuota),
        "n_cuotas": int(n_cuotas),
        "factor": factor,
    }


def simular_todos_los_planes(precio: float, tipo: str = "piscina") -> list[dict]:
    """
    Devuelve todos los planes calculados como lista de dicts.
    Útil para el dashboard y los paneles de control.
    """
    catalogo = _catalogo()
    planes   = catalogo["planes_financiacion"]
    factor   = catalogo["factor_ingreso_modulos"] if tipo == "modulo" else catalogo["factor_ingreso_piscinas"]
    resultado = []
    for key, plan in planes.items():
        n = plan["cuotas"]
        r = _calcular_plan(precio, n, factor)
        r["key"] = key
        resultado.append(r)
    return resultado
