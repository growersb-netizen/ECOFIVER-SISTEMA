"""
Calculador de flete desde Zárate hacia localidades de Argentina.
Retorna monto aproximado con disclaimer obligatorio.
Las tarifas por km se leen del catálogo para que sean configurables desde el panel.

Tarifas vigentes ($/km desde Zárate):
  - General (piscinas resto de modelos + módulos): $3.000
  - Piscinas grandes (Arco Romano Grande 8.10m, Playa y Abanico 9.20m): $5.000
  - Hidromasajes / jacuzzis: $2.000
  - Miniportante: tarifa histórica separada (ver catálogo), sin reconfirmar
"""

MODELOS_FLETE_ALTO = {"arco romano grande", "playa y abanico"}

# Tabla de distancias aproximadas (km) desde Zárate
# Fuente: estimaciones por ruta nacional/provincial
DISTANCIAS_DESDE_ZARATE: dict[str, int] = {
    # GBA / AMBA
    "zarate": 0,
    "campana": 15,
    "lima": 25,
    "san pedro": 45,
    "baradero": 70,
    "ramallo": 100,
    "san nicolas": 130,
    "capital federal": 110,
    "buenos aires": 110,
    "caba": 110,
    "tigre": 75,
    "san isidro": 85,
    "vicente lopez": 90,
    "olivos": 90,
    "florida": 95,
    "martinez": 88,
    "pilar": 55,
    "escobar": 40,
    "lujan": 105,
    "mercedes": 130,
    "san andres de giles": 80,
    "exaltacion de la cruz": 50,
    "moron": 120,
    "quilmes": 130,
    "lanus": 120,
    "avellaneda": 118,
    "lomas de zamora": 125,
    "san justo": 115,
    "merlo": 125,
    "moreno": 115,
    "la matanza": 115,
    "florencio varela": 135,
    "berazategui": 132,
    "jose c. paz": 80,
    "malvinas argentinas": 75,
    "san miguel": 90,
    "hurlingham": 110,
    "ituzaingo": 112,
    "tres de febrero": 105,
    "la plata": 160,
    "berisso": 165,
    "ensenada": 163,
    # Interior Buenos Aires
    "junin": 210,
    "pergamino": 130,
    "chivilcoy": 190,
    "nueve de julio": 270,
    "pehuajo": 320,
    "trenque lauquen": 380,
    "general pico": 470,
    "santa rosa": 480,
    "bahia blanca": 580,
    "tandil": 360,
    "azul": 310,
    "olavarria": 340,
    "necochea": 430,
    "mar del plata": 380,
    "miramar": 400,
    "pinamar": 320,
    "villa gesell": 310,
    "dolores": 200,
    "chascomus": 175,
    "coronel suarez": 450,
    "tres arroyos": 470,
    # Litoral / Entre Ríos
    "gualeguaychu": 185,
    "colon entre rios": 210,
    "concordia": 330,
    "parana": 330,
    "victoria": 305,
    "rosario": 225,
    "san lorenzo": 210,
    "villa constitucion": 200,
    # Santa Fe
    "santa fe": 380,
    "rafaela": 490,
    "venado tuerto": 370,
    "casilda": 280,
    # Córdoba
    "cordoba": 680,
    "rio cuarto": 600,
    "villa maria": 580,
    "san francisco": 590,
    "villa carlos paz": 700,
    # Mendoza / Cuyo
    "mendoza": 1060,
    "san rafael": 1100,
    "san luis": 870,
    # Noreste / Chaco / Misiones
    "resistencia": 1030,
    "corrientes": 980,
    "posadas": 1140,
    "formosa": 1170,
    "iguazu": 1300,
    # Noroeste / Tucumán / Salta
    "tucuman": 1120,
    "salta": 1350,
    "jujuy": 1470,
    "santiago del estero": 980,
    "catamarca": 1180,
    # Patagonia
    "neuquen": 1070,
    "cipolletti": 1080,
    "allen": 1090,
    "general roca": 1120,
    "bahia blanca": 580,
    "viedma": 820,
    "bariloche": 1380,
    "comodoro rivadavia": 1700,
    "rio gallegos": 2490,
    "ushuaia": 3050,
}

DISCLAIMER = (
    "Logística confirma el valor exacto con vos antes de la entrega."
)


def calcular_flete(localidad: str, producto: str = "general") -> dict:
    """
    Estima flete desde Zárate a la localidad indicada.

    Args:
        localidad: nombre de la localidad (no la dirección exacta)
        producto: nombre del modelo/categoría — "miniportante" usa su tarifa
            histórica separada; "hidromasaje"/"jacuzzi" usan $2.000/km;
            "arco romano grande" / "playa y abanico" usan $5.000/km;
            cualquier otro valor (piscinas resto + módulos) usa $3.000/km

    Returns:
        dict con monto_aproximado, disclaimer y localidad.
        Si la localidad no está en la tabla, devuelve None y un mensaje
        para escalar a Bruno.
    """
    key = localidad.lower().strip()

    # Intentar match exacto o parcial
    distancia = None
    for nombre, km in DISTANCIAS_DESDE_ZARATE.items():
        if key == nombre or key in nombre or nombre in key:
            distancia = km
            break

    if distancia is None:
        return {
            "monto_aproximado": None,
            "disclaimer": DISCLAIMER,
            "localidad": localidad,
            "nota": (
                f"No tengo la distancia exacta para '{localidad}'. "
                "Derivar a Bruno para confirmación de logística."
            ),
        }

    # Leer tarifas del catálogo en cada llamada (permite cambios desde el panel sin reiniciar)
    from agents.catalogo import CATALOGO
    tarifa_general       = CATALOGO.get("flete_por_km", 3000)
    tarifa_alto          = CATALOGO.get("flete_alto_por_km", 5000)
    tarifa_hidromasajes  = CATALOGO.get("flete_hidromasajes_por_km", 2000)
    tarifa_miniportante  = CATALOGO.get("flete_miniportante_por_km", 2000)

    producto_key = producto.lower().strip()
    if "miniportante" in producto_key:
        tarifa = tarifa_miniportante
    elif "hidromasaje" in producto_key or "jacuzzi" in producto_key:
        tarifa = tarifa_hidromasajes
    elif producto_key in MODELOS_FLETE_ALTO:
        tarifa = tarifa_alto
    else:
        tarifa = tarifa_general
    monto = distancia * tarifa

    return {
        "monto_aproximado": monto,
        "distancia_km": distancia,
        "tarifa_por_km": tarifa,
        "disclaimer": DISCLAIMER,
        "localidad": localidad,
        "texto_formateado": (
            f"El flete aproximado a {localidad.title()} es de "
            f"${monto:,.0f} ({distancia} km × ${tarifa:,}/km). "
            f"{DISCLAIMER}"
        ),
    }
