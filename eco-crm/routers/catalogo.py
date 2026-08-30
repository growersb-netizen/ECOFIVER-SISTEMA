"""
Catálogo de productos ampliable dinámicamente.
Modelos de piscinas y módulos habitacionales.
"""
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Usuario, PrecioHistorial
from routers.auth import require_auth, require_roles, get_user_roles, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")

FOTOS_DIR = Path("data/catalogo_fotos")  # dentro del volumen persistente (/app/data) — no ephemeral
FOTOS_DIR.mkdir(parents=True, exist_ok=True)
_EXTENSIONES_FOTO_VALIDAS = {".jpg", ".jpeg", ".png", ".webp"}
_MEDIA_TYPE_FOTO = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _write_auth(x_api_key: Optional[str], current_user: Optional[Usuario]):
    """Escritura de catálogo: sesión con rol de gestión, o X-API-Key (integraciones)."""
    if x_api_key and x_api_key == API_KEY:
        return
    if current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")):
        return
    raise HTTPException(403, "Sin permisos")

CATALOGO_FILE = Path("data/catalogo.json")
CATALOGO_FILE.parent.mkdir(parents=True, exist_ok=True)

# Medidas extraídas de la lista de precios oficial (Eco_Piscinas_Lista_Horizontal-3.pdf)
# litros = largo × ancho × prof_promedio × 1000
_MEDIDAS_PDF = {
    "Minideck":                          {"largo_m": 3.00, "ancho_m": 2.00, "profundidad_min_m": 0.70, "profundidad_max_m": 0.70, "litros": 4200},
    "Minideck Chico":                    {"largo_m": 3.00, "ancho_m": 2.00, "profundidad_min_m": 0.70, "profundidad_max_m": 0.70, "litros": 4200},
    "Minideck Grande":                   {"largo_m": 3.00, "ancho_m": 2.00, "profundidad_min_m": 0.70, "profundidad_max_m": 0.70, "litros": 4200},
    "Miniportante":                      {"largo_m": 2.50, "ancho_m": 2.10, "profundidad_min_m": 0.70, "profundidad_max_m": 0.70, "litros": 3675},
    "Autoportante":                      {"largo_m": 4.10, "ancho_m": 2.10, "profundidad_min_m": 0.70, "profundidad_max_m": 0.70, "litros": 6027},
    "Arco Romano Chico Recto":           {"largo_m": 4.60, "ancho_m": 2.47, "profundidad_min_m": 1.20, "profundidad_max_m": 1.20, "litros": 13625},
    "Arco Romano Chico C/Desnivel":      {"largo_m": 4.60, "ancho_m": 2.35, "profundidad_min_m": 1.10, "profundidad_max_m": 1.30, "litros": 12972},
    "Arco Romano Chico Curvo":           {"largo_m": 4.60, "ancho_m": 2.35, "profundidad_min_m": 1.10, "profundidad_max_m": 1.30, "litros": 12972},
    "Arco Romano Mediano Recto":         {"largo_m": 6.40, "ancho_m": 2.94, "profundidad_min_m": 1.40, "profundidad_max_m": 1.40, "litros": 26342},
    "Arco Romano Mediano C/Desnivel":    {"largo_m": 7.00, "ancho_m": 3.35, "profundidad_min_m": 1.25, "profundidad_max_m": 1.70, "litros": 34617},
    "Arco Romano Mediano Curvo":         {"largo_m": 7.00, "ancho_m": 3.35, "profundidad_min_m": 1.25, "profundidad_max_m": 1.70, "litros": 34617},
    "Arco Romano Grande":                {"largo_m": 8.10, "ancho_m": 3.35, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 41373},
    "Arco Romano Grande Recto":          {"largo_m": 8.10, "ancho_m": 3.35, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 41373},
    "Arco Romano Grande Curvo":          {"largo_m": 8.10, "ancho_m": 3.35, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 41373},
    "Playa Humeda":                      {"largo_m": 5.20, "ancho_m": 2.45, "profundidad_min_m": 1.10, "profundidad_max_m": 1.30, "litros": 15288},
    "Playa y Abanico":                   {"largo_m": 9.20, "ancho_m": 3.80, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 53254},
    "Playa y Abanico Chica":             {"largo_m": 9.20, "ancho_m": 3.80, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 53254},
    "Playa y Abanico Mediana":           {"largo_m": 9.20, "ancho_m": 3.80, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 53254},
    "Playa y Abanico Grande":            {"largo_m": 9.20, "ancho_m": 3.80, "profundidad_min_m": 1.25, "profundidad_max_m": 1.80, "litros": 53254},
    "Minimalista Chica":                 {"largo_m": 3.97, "ancho_m": 2.46, "profundidad_min_m": 1.20, "profundidad_max_m": 1.20, "litros": 11712},
    "Minimalista Mediana":               {"largo_m": 5.50, "ancho_m": 2.90, "profundidad_min_m": 1.50, "profundidad_max_m": 1.50, "litros": 23925},
    "Minimalista Grande":                {"largo_m": 6.40, "ancho_m": 3.00, "profundidad_min_m": 1.40, "profundidad_max_m": 1.40, "litros": 26880},
    "Recta C/Mini Escalera":             {"largo_m": 4.63, "ancho_m": 2.48, "profundidad_min_m": 1.25, "profundidad_max_m": 1.25, "litros": 14353},
    "Playa Humeda Chica C/Escalera":     {"largo_m": 4.10, "ancho_m": 2.40, "profundidad_min_m": 1.20, "profundidad_max_m": 1.20, "litros": 11808},
    "Semi Playa Humeda C/Escalera":      {"largo_m": 6.70, "ancho_m": 2.95, "profundidad_min_m": 1.50, "profundidad_max_m": 1.50, "litros": 29663},
}

DEFAULT_CATALOGO = {
    "piscinas": {
        "modelos": [
            "Arco Romano Chico Recto", "Arco Romano Chico Curvo",
            "Arco Romano Mediano Recto", "Arco Romano Mediano Curvo",
            "Arco Romano Grande Recto", "Arco Romano Grande Curvo",
            "Minimalista Chica", "Minimalista Mediana", "Minimalista Grande",
            "Playa y Abanico Chica", "Playa y Abanico Mediana", "Playa y Abanico Grande",
            "Miniportante", "Autoportante", "Minideck Chico", "Minideck Grande"
        ],
        "colores": ["Blanco", "Beige", "Verde agua", "Celeste", "Azul"],
        "precios": {},          # precio CONTADO (el que se cotiza al cliente)
        "precios_lista": {},    # precio LISTA (base para financiación/cuotas)
        "fotos": {},            # modelo -> [urls] (para armar publicaciones de ML automáticamente)
        "cuotas_max": 36,       # plazo más largo ofrecido — usado para publicar en ML al valor de la cuota
        "medidas": {},          # modelo -> {largo_m, ancho_m, profundidad_min_m, profundidad_max_m, litros}
                                 # litros se calcula solo al guardar — lo pide ML como atributo obligatorio
    },
    "modulos": {
        # Viviendas modulares: se venden financiadas, por m². No confundir con
        # "modulos_deposito" (calidad inferior, de contado, para depósito).
        "superficies_m2": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72],
        "tecnologia": (
            "Sistema constructivo Wood Frame: estructura de madera, revestimiento exterior en "
            "placas cementicias y terminación interior en Durlock. Llave en mano, con terminaciones incluidas."
        ),
        "modelos_custom": [],
        # precio CONTADO (lo que se cobra al cliente de contado)
        "precios": {
            # ── Módulos habitacionales 6 / 12 / 18 m² ─────────────────────────
            "Módulo ECO 6m²":   2990000,
            "Módulo FULL 6m²":  3690000,
            "Módulo ECO 12m²":  4990000,
            "Módulo FULL 12m²": 5990000,
            "Módulo ECO 18m²":  7490000,
            "Módulo FULL 18m²": 8990000,
            # ── Viviendas modulares (24 m²+) a $690.000/m² ────────────────────
            "Módulo 24m²":  16560000,
            "Módulo 30m²":  20700000,
            "Módulo 36m²":  24840000,
            "Módulo 42m²":  28980000,
            "Módulo 45m²":  31050000,
            "Módulo 48m²":  33120000,
            "Módulo 54m²":  37260000,
            "Módulo 60m²":  41400000,
            "Módulo 66m²":  45540000,
            "Módulo 72m²":  49680000,
        },
        # precio LISTA — precio ML (contado × 1.058, redondeado a $10.000)
        "precios_lista": {
            # ── Módulos habitacionales ─────────────────────────────────────────
            "Módulo ECO 6m²":   3160000,
            "Módulo FULL 6m²":  3900000,
            "Módulo ECO 12m²":  5280000,
            "Módulo FULL 12m²": 6340000,
            "Módulo ECO 18m²":  7920000,
            "Módulo FULL 18m²": 9510000,
            # ── Viviendas modulares ────────────────────────────────────────────
            "Módulo 24m²":  17520000,
            "Módulo 30m²":  21900000,
            "Módulo 36m²":  26280000,
            "Módulo 42m²":  30660000,
            "Módulo 45m²":  32850000,
            "Módulo 48m²":  35040000,
            "Módulo 54m²":  39420000,
            "Módulo 60m²":  43800000,
            "Módulo 66m²":  48180000,
            "Módulo 72m²":  52560000,
        },
        "fotos": {},            # superficie (str) o modelo_custom -> [urls]
        "cuotas_max": 60,       # plazo más largo ofrecido — usado para publicar en ML al valor de la cuota
    },
    "combos": {},  # nombre -> {"precio_lista":..., "precio_contado":..., "descripcion":..., "fotos": [...]}
    "hidromasajes": {
        # Línea propia EcoFiver: acrílico sanitario + PRFV, estructura autoportante incluida.
        # Se venden DE CONTADO o tarjeta. Sin financiación propia en cuotas.
        "material": "Acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado en Fibra de Vidrio)",
        "estructura": "Autoportante metálica reforzada (incluida en todos los modelos)",
        "instalacion": "Sin obra de albañilería. Conexión a agua fría/caliente existente, desagüe y electricidad.",
        "colores": ["Blanco", "Beige", "Negro", "Gris"],
        "colores_nota": "Sin cargo adicional por color. Indicar al momento de la compra.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "envio": "Disponible a domicilio, cotizar según zona.",
        "pago": "Contado, tarjeta de crédito o débito. Sin financiación propia en cuotas.",
        "garantia": "Garantía estructural incluida.",
        "modelos": {
            "Spa Quadra": {
                "descripcion_corta": "Rectangular compacto. Ideal para baños y espacios reducidos.",
                "formato": "Rectangular",
                "medidas": {"largo_m": 1.68, "ancho_m": 1.17, "profundidad_m": 0.45},
                "jets": 4,
                "motor_hp": "1/2 o 3/4",
                "pulsadores": 1,
                "reguladores_aire": 1,
                "precio_contado": 1220000,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.69x1.17x0.40-HIDRO.jpeg"],
            },
            "Spa Recta": {
                "descripcion_corta": "Rectangular doble. Diseño confort para dos personas.",
                "formato": "Rectangular",
                "medidas": {"largo_m": 1.65, "ancho_m": 1.40, "profundidad_m": 0.45},
                "jets": 6,
                "motor_hp": "3/4",
                "pulsadores": 1,
                "reguladores_aire": 2,
                "precio_contado": 1520000,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.65x1.40x0.45-HIDRO.jpeg"],
            },
            "Spa Orbis": {
                "descripcion_corta": "Circular panorámico. Para baños de lujo, terrazas o ambiente SPA.",
                "formato": "Circular",
                "medidas": {"largo_m": 1.76, "ancho_m": 1.76, "profundidad_m": 0.40},
                "jets": "6 a 8",
                "motor_hp": "3/4",
                "pulsadores": 1,
                "reguladores_aire": 2,
                "precio_contado": 1620000,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.76x1.76x0.40-HIDRO.jpeg"],
            },
            "Spa Delta": {
                "descripcion_corta": "Mini spa esquinero XL. Mayor profundidad de la línea.",
                "formato": "Esquinero XL / Mini Spa",
                "medidas": {"largo_m": 1.97, "ancho_m": 1.42, "profundidad_m": 0.52},
                "jets": 8,
                "motor_hp": "1",
                "pulsadores": 1,
                "reguladores_aire": 2,
                "precio_contado": 1890000,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.97x1.42x0.52-HIDRO.jpeg"],
            },
        },
        "equipamiento_comun": [
            "Jets dirigibles con vista cromo (cantidad según modelo)",
            "Motor (potencia según modelo)",
            "1 pulsador neumático de encendido",
            "Reguladores de flujo de aire (cantidad según modelo)",
            "Sistema de succión: filtro de pelos + sopapa + desborde conectados",
            "Estructura autoportante metálica reforzada",
        ],
        "opcionales": {
            "Kit Blower de Aire": {
                "descripcion": "Motor blower independiente + 12 inyectores de aire distribuidos en el piso. Genera efecto burbujas independiente del sistema de jets.",
                "precio_contado": None,
            },
            "Kit Cromoterapia LED": {
                "descripcion": "Spot LED multicolor sumergible con secuencias de iluminación programables.",
                "precio_contado": None,
            },
            "Kit Grifería y Cascada": {
                "descripcion": "Juego de grifería integrada sobreborde: pico cisne o cascada ovalada. Acabado cromo o negro mate.",
                "precio_contado": None,
            },
            "Sistema de Desinfección": {
                "descripcion": "Ozonizador para tratamiento de agua + sensor electrónico de nivel para protección del motor contra encendido en seco.",
                "precio_contado": None,
            },
            "Revestimiento Exterior WPC": {
                "descripcion": "Faldones/paneles exteriores símil madera, resistentes a la intemperie. Para instalación sobre deck o espacios al aire libre.",
                "precio_contado": None,
            },
        },
    },
    "modulos_deposito": {
        # Línea de módulos de calidad inferior a las viviendas modulares, para uso
        # como depósito. Se venden DE CONTADO (no financiado). Tamaños fijos x línea.
        "descripcion_base": (
            "Sin acabado final ni terminación de piso (piso colocado sin revestimiento). "
            "Incluye aberturas, pintura completa blanca e instalación eléctrica interna para luz."
        ),
        "descripcion_premium": (
            "Doble aislante con malla, terminación en placas de PRFV, incluye piso. "
            "Incluye aberturas, pintura completa blanca e instalación eléctrica interna para luz."
        ),
        "tamanos": {
            "6":  {"BASE": {"precio_contado": 2990000, "fotos": []}, "PREMIUM": {"precio_contado": 3690000, "fotos": []}},
            "12": {"BASE": {"precio_contado": 4990000, "fotos": []}, "PREMIUM": {"precio_contado": 5990000, "fotos": []}},
            "18": {"BASE": {"precio_contado": 7490000, "fotos": []}, "PREMIUM": {"precio_contado": 8990000, "fotos": []}},
            "24": {"BASE": {"precio_contado": None, "fotos": []}, "PREMIUM": {"precio_contado": None, "fotos": []}},
        },
    },
    # ── Bañeras de acrílico ───────────────────────────────────────────────────
    "baneras": {
        "material": "Acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado en Fibra de Vidrio)",
        "instalacion": "Instalación directa sobre el piso. Conexión a agua fría/caliente y desagüe. Sin obra de albañilería.",
        "colores": ["Blanco", "Beige", "Negro", "Gris"],
        "pago": "Contado, tarjeta de crédito o débito. Sin financiación propia en cuotas.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "envio": "Disponible a domicilio, cotizar según zona.",
        "garantia": "Garantía estructural incluida.",
        "modelos": {
            "Lumina": {
                "descripcion_corta": "Bañera rectangular estándar. 1,90 m. Ideal para baños amplios.",
                "formato": "Rectangular",
                "medidas": {"largo_m": 1.90, "ancho_m": 0.90, "profundidad_m": 0.50},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/lumina.jpg"],
            },
            "Sensa": {
                "descripcion_corta": "Angular doble asiento. Formato para dos personas.",
                "formato": "Angular doble",
                "medidas": {"largo_m": 1.70, "ancho_m": 1.18, "profundidad_m": 0.45},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/sensa.jpg"],
            },
            "Vento": {
                "descripcion_corta": "Bañera compacta. Ideal para baños de espacio reducido.",
                "formato": "Compacta rectangular",
                "medidas": {"largo_m": 1.40, "ancho_m": 0.77, "profundidad_m": 0.49},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/vento.jpg"],
            },
            "Aqua": {
                "descripcion_corta": "Doble asiento XL. Para baños de lujo o suites.",
                "formato": "Doble asiento XL",
                "medidas": {"largo_m": 1.65, "ancho_m": 1.40, "profundidad_m": 0.50},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/aquaaa.jpg"],
            },
            "Curve": {
                "descripcion_corta": "Bañera esquinera cuadrada. Aprovecha el rincón del baño.",
                "formato": "Esquinera cuadrada",
                "medidas": {"largo_m": 1.40, "ancho_m": 1.40, "profundidad_m": 0.55},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/curve.jpg"],
            },
            "Pure": {
                "descripcion_corta": "Bañera clásica rectangular de alta profundidad.",
                "formato": "Rectangular clásica",
                "medidas": {"largo_m": 1.84, "ancho_m": 0.96, "profundidad_m": 0.45},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/pure.jpg"],
            },
            "Vita": {
                "descripcion_corta": "Bañera rectangular estándar versátil. 1,80 m.",
                "formato": "Rectangular estándar",
                "medidas": {"largo_m": 1.80, "ancho_m": 0.90, "profundidad_m": 0.50},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/vita.jpg"],
            },
        },
    },
    # ── Receptáculos de ducha ─────────────────────────────────────────────────
    "receptaculos": {
        "material": "Acrílico sanitario de alta resistencia reforzado con PRFV, superficie antideslizante",
        "instalacion": "Instalación directa sobre el piso. Conexión a desagüe estándar. Sin obra.",
        "colores": ["Blanco", "Beige", "Negro", "Gris"],
        "pago": "Contado, tarjeta de crédito o débito. Sin financiación propia en cuotas.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "modelos": {
            "Clásico": {
                "descripcion_corta": "Receptáculo cuadrado estándar 110x110. El más popular.",
                "formato": "Cuadrado",
                "medidas": {"largo_m": 1.10, "ancho_m": 1.10, "profundidad_m": 0.10},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.10x1.10x0.10-RECEP.jpeg"],
            },
            "Esquinero": {
                "descripcion_corta": "Receptáculo esquinero 99x75 cm. Aprovecha los rincones.",
                "formato": "Esquinero rectangular",
                "medidas": {"largo_m": 0.99, "ancho_m": 0.75, "profundidad_m": 0.10},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/99X75-RECEP.jpeg"],
            },
            "Pequeño": {
                "descripcion_corta": "Receptáculo compacto 90x90 cm. Para espacios reducidos.",
                "formato": "Cuadrado compacto",
                "medidas": {"largo_m": 0.90, "ancho_m": 0.90, "profundidad_m": 0.09},
                "precio_contado": None,
                "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/90x90x0.90-RECEP.jpeg"],
            },
        },
    },
    # ── Accesorios y equipos para piscinas ───────────────────────────────────
    "accesorios_piscinas": {
        "nota": "Accesorios compatibles con todas las líneas de piscinas EcoFiver.",
        "pago": "Contado, tarjeta de crédito o débito.",
        "productos": {
            "Iluminación LED Sumergible": {
                "descripcion": "Luz LED sumergible para piscinas. Multicolor o blanco cálido/frío. Resistente al agua. Fácil instalación.",
                "precio_contado": None,
                "fotos": [],
            },
            "Bomba Filtradora": {
                "descripcion": "Equipo de filtración para piscinas. Distintas potencias según el volumen de la pileta. Consultar modelo.",
                "precio_contado": None,
                "fotos": [],
            },
            "Filtro de Arena": {
                "descripcion": "Filtro de arena para piscinas. Elimina impurezas y mantiene el agua limpia. Compatible con bombas estándar.",
                "precio_contado": None,
                "fotos": [],
            },
            "Escalera de Piscina": {
                "descripcion": "Escalera de acero inoxidable para piscinas. Distintos modelos (2 y 3 peldaños). Fácil instalación.",
                "precio_contado": None,
                "fotos": [],
            },
            "Cobertor de Invierno": {
                "descripcion": "Cobertor para proteger la piscina fuera de temporada. A medida según dimensiones.",
                "precio_contado": None,
                "fotos": [],
            },
        },
    },
    # ── Baños químicos ────────────────────────────────────────────────────────
    "banios_quimicos": {
        "material": "Estructura de polipropileno de alta densidad",
        "usos": "Obras de construcción, eventos, festivales, camping, ferias, zonas rurales sin saneamiento.",
        "pago": "Contado o tarjeta. Disponible también en alquiler (consultar).",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "modelos": {
            "Estándar": {
                "descripcion_corta": "Baño químico portátil individual. Inodoro, urinario y porta papel.",
                "precio_contado": None,
                "precio_alquiler_dia": None,
                "fotos": [],
            },
            "Con Lavamanos": {
                "descripcion_corta": "Baño químico con lavamanos integrado. Mayor confort e higiene.",
                "precio_contado": None,
                "precio_alquiler_dia": None,
                "fotos": [],
            },
            "Discapacitados": {
                "descripcion_corta": "Baño químico accesible. Dimensiones para silla de ruedas, con barras de apoyo.",
                "precio_contado": None,
                "precio_alquiler_dia": None,
                "fotos": [],
            },
        },
    },
    # ── Garitas de seguridad ──────────────────────────────────────────────────
    "garitas_seguridad": {
        "material": "PRFV (Poliéster Reforzado en Fibra de Vidrio) color blanco. Resistente a la intemperie.",
        "usos": "Control de acceso a edificios, countries, barrios cerrados, plantas industriales, peajes.",
        "pago": "Contado o tarjeta.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "envio": "Disponible a domicilio, cotizar según zona.",
        "modelos": {
            "Estándar 1.15x1.15": {
                "descripcion_corta": (
                    "Cabina de seguridad prefabricada PRFV color blanca. 1,15 x 1,15 x 2,26 m de alto. "
                    "Mesa interna con cajón. Instalación eléctrica completa con llave de punto, toma con neutro, "
                    "artefacto LED y llave termomagnética. Puerta con cerradura doble paleta. "
                    "4 lados vidriados: 3 vidrios fijos sellados con adhesivo automotriz y 1 ventana guillotina con marco de aluminio. "
                    "Piso de multilaminado fenólico 19 mm."
                ),
                "medidas": {"largo_m": 1.15, "ancho_m": 1.15, "alto_m": 2.26},
                "equipamiento": [
                    "Mesa interna con cajón",
                    "Instalación eléctrica completa (llave de punto + toma con neutro)",
                    "Artefacto de iluminación metálico con luz LED",
                    "Llave termomagnética",
                    "Puerta con cerradura doble paleta",
                    "3 vidrios fijos sellados con adhesivo automotriz + marco externo",
                    "1 ventana guillotina con marco de aluminio",
                    "Piso multilaminado fenólico 19 mm",
                ],
                "precio_contado": 1990000,
                "precio_lista":   2106000,   # × 1.058 redondeado a $1.000
                "fotos": [],
            },
            "Con Baño": {
                "descripcion_corta": "Garita con baño interior integrado. Mayor autonomía para el guardia.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
            "Doble": {
                "descripcion_corta": "Garita para dos puestos de control. Doble acceso.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
        },
    },
    # ── Cuchas para perros ────────────────────────────────────────────────────
    "cuchas_perros": {
        "material": "Madera tratada para exterior (pino impregnado o melamina). Techo desmontable.",
        "usos": "Para perros de todos los tamaños. Uso en exteriores e interiores.",
        "pago": "Contado o tarjeta.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "modelos": {
            "Chica": {
                "descripcion_corta": "Para razas pequeñas (hasta 5 kg). Tejkel, Chihuahua, etc.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
            "Mediana": {
                "descripcion_corta": "Para razas medianas (hasta 15 kg). Beagle, Caniche grande, etc.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
            "Grande": {
                "descripcion_corta": "Para razas grandes (hasta 35 kg). Labrador, Golden, etc.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
            "Extra Grande": {
                "descripcion_corta": "Para razas extra grandes (más de 35 kg). Gran Danés, Ovejero, etc.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
        },
    },
    # ── Reposeras de fibra ────────────────────────────────────────────────────
    "reposeras": {
        "material": "Fibra de vidrio con gel coat UV. Resistente a la intemperie y al agua.",
        "usos": "Piletas, playas, jardines, terrazas, spa.",
        "colores": ["Blanco", "Beige"],
        "pago": "Contado o tarjeta.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "nota_precio": "Precio por unidad $150.000 — par de 2 unidades $250.000 (descuento comprando el par).",
        "modelos": {
            "Reposera Individual": {
                "descripcion_corta": "Reposera reclinable de fibra de vidrio. Regulable en varios ángulos. Resistente a la intemperie.",
                "medidas": {"largo_m": None, "ancho_m": None},
                "precio_contado": 150000,
                "fotos": [],
            },
            "Par de Reposeras": {
                "descripcion_corta": "Par de 2 reposeras reclinables de fibra de vidrio. Precio especial comprando las 2 juntas.",
                "medidas": {"largo_m": None, "ancho_m": None},
                "precio_contado": 250000,
                "unidades": 2,
                "fotos": [],
            },
        },
    },
    # ── Depósitos de jardín ───────────────────────────────────────────────────
    "depositos_jardin": {
        "material": "Chapa galvanizada / PRFV según modelo.",
        "usos": "Guardado de herramientas, equipos de jardín, bicicletas, etc.",
        "pago": "Contado o tarjeta.",
        "puntos_entrega": ["San Telmo (CABA)", "Zárate (Buenos Aires)"],
        "modelos": {
            "Pequeño": {
                "descripcion_corta": "Depósito compacto para herramientas y equipos pequeños.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
            "Mediano": {
                "descripcion_corta": "Depósito mediano. Capacidad para bicicletas y equipos de jardín.",
                "medidas": {"largo_m": None, "ancho_m": None, "alto_m": None},
                "precio_contado": None,
                "fotos": [],
            },
        },
    },
}


def load_catalogo() -> dict:
    if CATALOGO_FILE.exists():
        try:
            cat = json.loads(CATALOGO_FILE.read_text(encoding="utf-8"))
            # Migración: completar claves nuevas si el archivo es de un esquema viejo
            cambiado = False
            for seccion in ("piscinas", "modulos"):
                cat.setdefault(seccion, {})
                for campo, default in DEFAULT_CATALOGO[seccion].items():
                    if campo not in cat[seccion]:
                        cat[seccion][campo] = default if not isinstance(default, (list, dict)) else type(default)()
                        cambiado = True
            if "combos" not in cat:
                cat["combos"] = {}
                cambiado = True
            if "hidromasajes" not in cat:
                cat["hidromasajes"] = json.loads(json.dumps(DEFAULT_CATALOGO["hidromasajes"]))
                cambiado = True
            else:
                # Agregar modelos nuevos que falten sin pisar los existentes
                for modelo, datos in DEFAULT_CATALOGO["hidromasajes"]["modelos"].items():
                    if modelo not in cat["hidromasajes"].get("modelos", {}):
                        cat["hidromasajes"].setdefault("modelos", {})[modelo] = datos
                        cambiado = True
                # Agregar campos raíz nuevos
                for campo, val in DEFAULT_CATALOGO["hidromasajes"].items():
                    if campo not in cat["hidromasajes"]:
                        cat["hidromasajes"][campo] = val
                        cambiado = True
            if "modulos_deposito" not in cat:
                cat["modulos_deposito"] = json.loads(json.dumps(DEFAULT_CATALOGO["modulos_deposito"]))
                cambiado = True
            # Migración: nuevas líneas de productos
            for seccion_nueva in ("baneras", "receptaculos", "accesorios_piscinas",
                                  "banios_quimicos", "garitas_seguridad", "cuchas_perros",
                                  "reposeras", "depositos_jardin"):
                if seccion_nueva not in cat:
                    cat[seccion_nueva] = json.loads(json.dumps(DEFAULT_CATALOGO[seccion_nueva]))
                    cambiado = True
                else:
                    # Agregar modelos nuevos que falten sin pisar los existentes
                    modelos_default = DEFAULT_CATALOGO[seccion_nueva].get("modelos") or \
                                      DEFAULT_CATALOGO[seccion_nueva].get("productos", {})
                    modelos_cat = cat[seccion_nueva].get("modelos") or \
                                  cat[seccion_nueva].get("productos", {})
                    for nombre, datos in modelos_default.items():
                        if nombre not in modelos_cat:
                            modelos_cat[nombre] = datos
                            cambiado = True
            # Actualizar fotos de hidromasajes si el modelo tiene fotos vacías
            # Fusionar precios de módulos nuevos (ECO/FULL + viviendas faltantes)
            for campo_precio in ("precios", "precios_lista"):
                defaults_p = DEFAULT_CATALOGO["modulos"].get(campo_precio, {})
                current_p  = cat["modulos"].setdefault(campo_precio, {})
                for pk, pv in defaults_p.items():
                    if pk not in current_p:
                        current_p[pk] = pv
                        cambiado = True
            if "hidromasajes" in cat:
                for modelo, datos in DEFAULT_CATALOGO["hidromasajes"]["modelos"].items():
                    m = cat["hidromasajes"].get("modelos", {}).get(modelo)
                    if m is not None and not m.get("fotos") and datos.get("fotos"):
                        m["fotos"] = datos["fotos"]
                        cambiado = True
            # Actualizar precios y fotos de las nuevas líneas cuando DEFAULT tiene
            # un valor real y el catálogo guardado todavía tiene None
            for seccion in ("baneras", "receptaculos", "reposeras", "cuchas_perros",
                            "garitas_seguridad", "banios_quimicos", "depositos_jardin"):
                if seccion not in cat:
                    continue
                default_sec = DEFAULT_CATALOGO.get(seccion, {})
                modelos_default = default_sec.get("modelos") or default_sec.get("productos", {})
                modelos_cat = cat[seccion].get("modelos") or cat[seccion].get("productos", {})
                for nombre, datos in modelos_default.items():
                    m = modelos_cat.get(nombre)
                    if m is None:
                        continue
                    # Precio: actualizar si el default tiene valor y el guardado es None
                    if m.get("precio_contado") is None and datos.get("precio_contado") is not None:
                        m["precio_contado"] = datos["precio_contado"]
                        cambiado = True
                    # Fotos: actualizar si el default tiene fotos y el guardado está vacío
                    if not m.get("fotos") and datos.get("fotos"):
                        m["fotos"] = datos["fotos"]
                        cambiado = True
                    # Campos nuevos: unidades, nota, etc.
                    for campo in ("unidades", "descripcion_corta"):
                        if campo not in m and campo in datos:
                            m[campo] = datos[campo]
                            cambiado = True
                # Campos raíz nuevos (nota_precio, etc.)
                for campo, val in default_sec.items():
                    if campo not in ("modelos", "productos") and campo not in cat[seccion]:
                        cat[seccion][campo] = val
                        cambiado = True
            # Seed medidas desde lista de precios oficial si el dict está vacío
            if not cat["piscinas"].get("medidas"):
                cat["piscinas"]["medidas"] = dict(_MEDIDAS_PDF)
                cambiado = True
            else:
                # Agregar modelos nuevos que falten (sin pisar los ya configurados)
                for k, v in _MEDIDAS_PDF.items():
                    if k not in cat["piscinas"]["medidas"]:
                        cat["piscinas"]["medidas"][k] = v
                        cambiado = True
            if cambiado:
                save_catalogo(cat)
            return cat
        except Exception:
            pass
    cat = json.loads(json.dumps(DEFAULT_CATALOGO))
    cat["piscinas"]["medidas"] = dict(_MEDIDAS_PDF)
    save_catalogo(cat)
    return cat


def save_catalogo(data: dict):
    CATALOGO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_modelos_piscina() -> List[str]:
    return load_catalogo()["piscinas"]["modelos"]


def get_all_modelos_modulo() -> List[str]:
    cat = load_catalogo()
    sup = cat["modulos"]["superficies_m2"]
    custom = cat["modulos"].get("modelos_custom", [])
    standard = [f"Módulo {m}m²" for m in sup]
    return standard + custom


# ─── HTML PAGE ────────────────────────────────────────────────────────────────

@router.get("/catalogo-admin", response_class=HTMLResponse)
async def catalogo_admin_page(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    from routers.auth import get_user_roles
    roles = get_user_roles(user)
    if "ADMIN" not in roles:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/", 302)
    cat = load_catalogo()
    return templates.TemplateResponse("catalogo_admin.html", {
        "request": request,
        "user": user,
        "roles": roles,
        "catalogo": cat,
    })


# ─── API ──────────────────────────────────────────────────────────────────────

@router.get("/api/catalogo")
async def get_catalogo(current_user: Usuario = Depends(require_auth)):
    cat = load_catalogo()
    # Superficies separadas: módulos habitacionales (6-18 m²) vs viviendas modulares (24+ m²)
    sup_all = cat["modulos"]["superficies_m2"]
    sup_habitacionales = [m for m in sup_all if m <= 18]
    sup_viviendas      = [m for m in sup_all if m > 18]
    return {
        "piscinas": {
            "modelos": cat["piscinas"]["modelos"],
            "colores": cat["piscinas"]["colores"],
            "precios": cat["piscinas"].get("precios", {}),
            "precios_lista": cat["piscinas"].get("precios_lista", {}),
            "fotos": cat["piscinas"].get("fotos", {}),
            "cuotas_max": cat["piscinas"].get("cuotas_max", 36),
            "medidas": cat["piscinas"].get("medidas", {}),
        },
        "modulos": {
            "superficies_m2":          sup_all,
            "superficies_habitacionales": sup_habitacionales,  # 6-18 m² — NO son viviendas
            "superficies_viviendas":      sup_viviendas,       # 24+ m² — sí son viviendas
            "tecnologia": cat["modulos"]["tecnologia"],
            "modelos_custom": cat["modulos"].get("modelos_custom", []),
            "precios": cat["modulos"].get("precios", {}),
            "precios_lista": cat["modulos"].get("precios_lista", {}),
            "fotos": cat["modulos"].get("fotos", {}),
            "cuotas_max": cat["modulos"].get("cuotas_max", 60),
        },
        "combos": cat.get("combos", {}),
        "modulos_deposito": cat.get("modulos_deposito", DEFAULT_CATALOGO["modulos_deposito"]),
        # ── Líneas de productos adicionales ─────────────────────────────────────
        "hidromasajes":      cat.get("hidromasajes", {}),
        "baneras":           cat.get("baneras", {}),
        "receptaculos":      cat.get("receptaculos", {}),
        "accesorios_piscinas": cat.get("accesorios_piscinas", {}),
        "banios_quimicos":   cat.get("banios_quimicos", {}),
        "garitas_seguridad": cat.get("garitas_seguridad", {}),
        "cuchas_perros":     cat.get("cuchas_perros", {}),
        "reposeras":         cat.get("reposeras", {}),
        "depositos_jardin":  cat.get("depositos_jardin", {}),
    }


@router.get("/api/catalogo/publico")
async def get_catalogo_publico():
    """Catálogo público sin autenticación — usado por web, agentes IA, simulador."""
    cat = load_catalogo()
    sup_all = cat["modulos"]["superficies_m2"]
    return {
        "piscinas": {
            "modelos": cat["piscinas"]["modelos"],
            "colores": cat["piscinas"]["colores"],
            "precios": cat["piscinas"].get("precios", {}),
            "precios_lista": cat["piscinas"].get("precios_lista", {}),
        },
        "modulos": {
            "superficies_m2":             sup_all,
            "superficies_habitacionales": [m for m in sup_all if m <= 18],
            "superficies_viviendas":      [m for m in sup_all if m > 18],
            "tecnologia": cat["modulos"]["tecnologia"],
            "modelos_custom": cat["modulos"].get("modelos_custom", []),
            "precios": cat["modulos"].get("precios", {}),
            "precios_lista": cat["modulos"].get("precios_lista", {}),
        },
        "combos": cat.get("combos", {}),
        "hidromasajes":    {k: {"precio_contado": v.get("precio_contado"), "medidas": v.get("medidas")}
                           for k, v in cat.get("hidromasajes", {}).get("modelos", {}).items()},
        "baneras":         {k: {"medidas": v.get("medidas")}
                           for k, v in cat.get("baneras", {}).get("modelos", {}).items()},
        "receptaculos":    {k: {"medidas": v.get("medidas")}
                           for k, v in cat.get("receptaculos", {}).get("modelos", {}).items()},
    }


# ─── FOTOS (para autocompletar publicaciones de MercadoLibre) ────────────────

@router.post("/api/catalogo/fotos/upload")
async def upload_foto_catalogo(
    request: Request,
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Sube una imagen al volumen persistente y devuelve su URL pública (para MercadoLibre y el catálogo)."""
    _write_auth(x_api_key, current_user)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _EXTENSIONES_FOTO_VALIDAS:
        raise HTTPException(400, f"Formato no soportado. Usar: {', '.join(sorted(_EXTENSIONES_FOTO_VALIDAS))}")
    contenido = await file.read()
    if len(contenido) > 8 * 1024 * 1024:
        raise HTTPException(400, "La imagen no puede superar 8MB")
    nombre = f"{uuid.uuid4().hex}{ext}"
    (FOTOS_DIR / nombre).write_bytes(contenido)

    from routers.contratos import _abs_url
    return {"ok": True, "filename": nombre, "url": _abs_url(request, f"/api/catalogo/fotos/{nombre}")}


@router.get("/api/catalogo/fotos/{filename}")
async def get_foto_catalogo(filename: str):
    """
    Público y SIN auth a propósito: MercadoLibre necesita poder buscar la
    imagen directamente desde sus servidores al crear la publicación.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Nombre de archivo inválido")
    path = FOTOS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Imagen no encontrada")
    media_type = _MEDIA_TYPE_FOTO.get(path.suffix.lower().lstrip("."), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type)


@router.put("/api/catalogo/fotos")
async def set_fotos_catalogo(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Asocia una lista de URLs de foto a una clave del catálogo.
    Body: { "tipo": "piscinas"|"modulos"|"combos"|"modulos_deposito",
            "clave": "<modelo o tamaño_LINEA>", "fotos": ["url1", "url2", ...] }
    Reemplaza la lista completa (no agrega incremental). Además, sincroniza las
    fotos nuevas en TODAS las publicaciones de MercadoLibre activas que estén
    vinculadas a ese modelo (así renovar fotos no exige entrar publicación por
    publicación) — best-effort, no bloquea el guardado si ML falla.
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    tipo = data.get("tipo", "")
    clave = data.get("clave", "")
    fotos = data.get("fotos", [])
    _TIPOS_LEGACY = {"piscinas", "modulos", "combos", "modulos_deposito"}
    if not tipo or not clave:
        raise HTTPException(400, "tipo/clave requeridos")
    if not isinstance(fotos, list):
        raise HTTPException(400, "fotos debe ser una lista de URLs")

    cat = load_catalogo()
    if tipo == "combos":
        if clave not in cat.get("combos", {}):
            raise HTTPException(404, "Combo no encontrado")
        cat["combos"][clave]["fotos"] = fotos
    elif tipo == "modulos_deposito":
        try:
            tamano, linea = clave.split("_", 1)
        except ValueError:
            raise HTTPException(400, "clave debe tener formato '<tamano>_<BASE|PREMIUM>'")
        tamanos = cat.setdefault("modulos_deposito", {}).setdefault("tamanos", {})
        if tamano not in tamanos or linea not in tamanos[tamano]:
            raise HTTPException(404, "Tamaño/línea no encontrados")
        tamanos[tamano][linea]["fotos"] = fotos
    elif tipo in _TIPOS_LEGACY:
        # piscinas / modulos: fotos en cat[tipo]["fotos"][clave]
        cat[tipo].setdefault("fotos", {})
        cat[tipo]["fotos"][clave] = fotos
    else:
        # Categoría genérica (hidromasajes, baneras, receptaculos, etc.):
        # las fotos se guardan en el propio producto → cat[tipo][key][clave]["fotos"]
        if tipo not in cat:
            raise HTTPException(404, f"Categoría '{tipo}' no encontrada")
        key = _items_key(cat[tipo])
        items = cat[tipo].get(key, {})
        if clave not in items:
            raise HTTPException(404, f"Producto '{clave}' no encontrado en '{tipo}'")
        items[clave]["fotos"] = fotos

    save_catalogo(cat)

    sincronizadas = 0
    try:
        from routers.mercadolibre import _sincronizar_fotos_publicaciones
        sincronizadas = await _sincronizar_fotos_publicaciones(db, tipo, clave, fotos)
    except Exception as e:
        return {"ok": True, "tipo": tipo, "clave": clave, "fotos": fotos,
                "sincronizadas": 0, "sync_error": str(e)[:200]}

    return {"ok": True, "tipo": tipo, "clave": clave, "fotos": fotos, "sincronizadas": sincronizadas}


# ─── MEDIDAS DE PISCINAS (para calcular litros — atributo obligatorio en ML) ──

@router.put("/api/catalogo/piscinas/medidas")
async def set_medidas_piscina(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Body: { "modelo": "...", "largo_m": 6, "ancho_m": 3, "profundidad_min_m": 1.2, "profundidad_max_m": 1.5 }
    Calcula y guarda los litros aproximados (largo x ancho x profundidad promedio x 1000),
    para no tener que buscarlos a mano cada vez que se publica en MercadoLibre.
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    modelo = (data.get("modelo") or "").strip()
    if not modelo:
        raise HTTPException(400, "modelo requerido")

    largo = float(data.get("largo_m") or 0)
    ancho = float(data.get("ancho_m") or 0)
    prof_min = float(data.get("profundidad_min_m") or 0)
    prof_max = float(data.get("profundidad_max_m") or 0)
    prof_prom = (prof_min + prof_max) / 2 if (prof_min or prof_max) else 0
    litros = round(largo * ancho * prof_prom * 1000) if (largo and ancho and prof_prom) else None

    cat = load_catalogo()
    cat["piscinas"].setdefault("medidas", {})
    cat["piscinas"]["medidas"][modelo] = {
        "largo_m": largo, "ancho_m": ancho,
        "profundidad_min_m": prof_min, "profundidad_max_m": prof_max,
        "litros": litros,
    }
    save_catalogo(cat)
    return {"ok": True, "modelo": modelo, "medidas": cat["piscinas"]["medidas"][modelo]}


@router.put("/api/catalogo/piscinas/medidas/bulk")
async def set_medidas_bulk(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Body: { "modelos": [ {"modelo": "...", "largo_m": 6, ...}, ... ] }
    Carga masiva de medidas. Calcula litros para cada modelo y guarda todo en una sola escritura.
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    items = data.get("modelos") or []
    if not items:
        raise HTTPException(400, "modelos requerido (lista)")

    cat = load_catalogo()
    cat["piscinas"].setdefault("medidas", {})
    guardados = {}
    for item in items:
        modelo = (item.get("modelo") or "").strip()
        if not modelo:
            continue
        largo = float(item.get("largo_m") or 0)
        ancho = float(item.get("ancho_m") or 0)
        prof_min = float(item.get("profundidad_min_m") or 0)
        prof_max = float(item.get("profundidad_max_m") or 0)
        prof_prom = (prof_min + prof_max) / 2 if (prof_min or prof_max) else 0
        litros = round(largo * ancho * prof_prom * 1000) if (largo and ancho and prof_prom) else None
        cat["piscinas"]["medidas"][modelo] = {
            "largo_m": largo, "ancho_m": ancho,
            "profundidad_min_m": prof_min, "profundidad_max_m": prof_max,
            "litros": litros,
        }
        guardados[modelo] = cat["piscinas"]["medidas"][modelo]

    save_catalogo(cat)
    return {"ok": True, "guardados": len(guardados), "medidas": guardados}


# ─── MÓDULOS DE DEPÓSITO (línea de contado, calidad inferior) ────────────────

@router.get("/api/catalogo/modulos-deposito")
async def get_modulos_deposito(current_user: Usuario = Depends(require_auth)):
    cat = load_catalogo()
    return cat.get("modulos_deposito", DEFAULT_CATALOGO["modulos_deposito"])


@router.put("/api/catalogo/modulos-deposito/precio")
async def set_precio_modulo_deposito(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Body: { "tamano": "6"|"12"|"18"|"24", "linea": "BASE"|"PREMIUM", "precio_contado": 2990000 }"""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    tamano = str(data.get("tamano", ""))
    linea = data.get("linea", "")
    precio = data.get("precio_contado")
    if linea not in ("BASE", "PREMIUM") or precio is None:
        raise HTTPException(400, "linea debe ser BASE o PREMIUM, precio_contado requerido")

    cat = load_catalogo()
    tamanos = cat.setdefault("modulos_deposito", {}).setdefault("tamanos", {})
    if tamano not in tamanos:
        tamanos[tamano] = {"BASE": {"precio_contado": None, "fotos": []}, "PREMIUM": {"precio_contado": None, "fotos": []}}
    valor_anterior = tamanos[tamano][linea].get("precio_contado")
    nuevo_valor = float(precio)
    if valor_anterior != nuevo_valor and current_user:
        db.add(PrecioHistorial(
            clave=f"modulos_deposito.{tamano}.{linea}",
            valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
            valor_nuevo=nuevo_valor,
            cambiado_por_id=current_user.id,
        ))
        db.commit()
    tamanos[tamano][linea]["precio_contado"] = nuevo_valor
    save_catalogo(cat)
    return {"ok": True, "tamanos": tamanos}


@router.get("/api/catalogo/modelos")
async def get_modelos(
    tipo: Optional[str] = None,
    current_user: Usuario = Depends(require_auth)
):
    if tipo == "PISCINA":
        return {"modelos": get_all_modelos_piscina()}
    elif tipo == "MODULO":
        return {"modelos": get_all_modelos_modulo()}
    else:
        return {
            "piscinas": get_all_modelos_piscina(),
            "modulos": get_all_modelos_modulo(),
        }


# ─── PISCINAS ─────────────────────────────────────────────────────────────────

@router.post("/api/catalogo/piscinas/modelos")
async def add_modelo_piscina(
    request: Request,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    nombre = data.get("nombre", "").strip()
    if not nombre:
        raise HTTPException(400, "Nombre requerido")

    cat = load_catalogo()
    if nombre in cat["piscinas"]["modelos"]:
        raise HTTPException(400, "El modelo ya existe")
    cat["piscinas"]["modelos"].append(nombre)
    save_catalogo(cat)
    return {"ok": True, "modelos": cat["piscinas"]["modelos"]}


@router.put("/api/catalogo/piscinas/modelos")
async def set_modelos_piscinas(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Reemplaza la lista completa de modelos de piscinas. Body: { modelos: [...] }"""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    modelos = data.get("modelos")
    if not isinstance(modelos, list) or not modelos:
        raise HTTPException(400, "modelos debe ser una lista no vacía")
    cat = load_catalogo()
    cat["piscinas"]["modelos"] = modelos
    save_catalogo(cat)
    return {"ok": True, "modelos": modelos}


@router.delete("/api/catalogo/piscinas/modelos/{nombre}")
async def delete_modelo_piscina(
    nombre: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if nombre not in cat["piscinas"]["modelos"]:
        raise HTTPException(404, "Modelo no encontrado")
    cat["piscinas"]["modelos"].remove(nombre)
    save_catalogo(cat)
    return {"ok": True}


@router.post("/api/catalogo/piscinas/colores")
async def add_color_piscina(
    request: Request,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    color = data.get("color", "").strip()
    if not color:
        raise HTTPException(400, "Color requerido")
    cat = load_catalogo()
    if color in cat["piscinas"]["colores"]:
        raise HTTPException(400, "El color ya existe")
    cat["piscinas"]["colores"].append(color)
    save_catalogo(cat)
    return {"ok": True, "colores": cat["piscinas"]["colores"]}


@router.delete("/api/catalogo/piscinas/colores/{color}")
async def delete_color_piscina(
    color: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if color not in cat["piscinas"]["colores"]:
        raise HTTPException(404, "Color no encontrado")
    cat["piscinas"]["colores"].remove(color)
    save_catalogo(cat)
    return {"ok": True}


@router.put("/api/catalogo/piscinas/precios")
async def update_precios_piscinas(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    cat = load_catalogo()
    precios_actuales = cat["piscinas"].get("precios", {})
    for clave, nuevo_valor in data.items():
        valor_anterior = precios_actuales.get(clave)
        if valor_anterior != nuevo_valor:
            db.add(PrecioHistorial(
                clave=f"piscinas.{clave}",
                valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
                valor_nuevo=float(nuevo_valor),
                cambiado_por_id=current_user.id,
            ))
    cat["piscinas"]["precios"].update(data)
    save_catalogo(cat)
    db.commit()
    return {"ok": True}


# ─── MÓDULOS ──────────────────────────────────────────────────────────────────

@router.put("/api/catalogo/modulos/tecnologia")
async def set_tecnologia_modulos(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Body: { texto }. Descripción del sistema constructivo, se usa como contexto en las publicaciones de ML."""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    texto = (data.get("texto") or "").strip()
    if not texto:
        raise HTTPException(400, "texto requerido")
    cat = load_catalogo()
    cat["modulos"]["tecnologia"] = texto
    save_catalogo(cat)
    return {"ok": True, "tecnologia": texto}


@router.post("/api/catalogo/modulos/superficies")
async def add_superficie(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    _write_auth(x_api_key, current_user)
    data = await request.json()
    m2 = data.get("m2")
    if m2 is None:
        raise HTTPException(400, "m2 requerido")
    try:
        m2 = int(m2)
    except Exception:
        raise HTTPException(400, "m2 debe ser un número")
    cat = load_catalogo()
    if m2 in cat["modulos"]["superficies_m2"]:
        raise HTTPException(400, "La superficie ya existe")
    cat["modulos"]["superficies_m2"].append(m2)
    cat["modulos"]["superficies_m2"].sort()
    save_catalogo(cat)
    return {"ok": True, "superficies": cat["modulos"]["superficies_m2"]}


@router.delete("/api/catalogo/modulos/superficies/{m2}")
async def delete_superficie(
    m2: int,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if m2 not in cat["modulos"]["superficies_m2"]:
        raise HTTPException(404, "Superficie no encontrada")
    cat["modulos"]["superficies_m2"].remove(m2)
    save_catalogo(cat)
    return {"ok": True}


@router.post("/api/catalogo/modulos/modelos-custom")
async def add_modelo_modulo_custom(
    request: Request,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    nombre = data.get("nombre", "").strip()
    if not nombre:
        raise HTTPException(400, "Nombre requerido")
    cat = load_catalogo()
    if nombre in cat["modulos"].get("modelos_custom", []):
        raise HTTPException(400, "El modelo ya existe")
    if "modelos_custom" not in cat["modulos"]:
        cat["modulos"]["modelos_custom"] = []
    cat["modulos"]["modelos_custom"].append(nombre)
    save_catalogo(cat)
    return {"ok": True, "modelos_custom": cat["modulos"]["modelos_custom"]}


@router.delete("/api/catalogo/modulos/modelos-custom/{nombre}")
async def delete_modelo_modulo_custom(
    nombre: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    custom = cat["modulos"].get("modelos_custom", [])
    if nombre not in custom:
        raise HTTPException(404, "Modelo no encontrado")
    custom.remove(nombre)
    cat["modulos"]["modelos_custom"] = custom
    save_catalogo(cat)
    return {"ok": True}


@router.put("/api/catalogo/modulos/precios")
async def update_precios_modulos(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    cat = load_catalogo()
    precios_actuales = cat["modulos"].get("precios", {})
    for clave, nuevo_valor in data.items():
        valor_anterior = precios_actuales.get(clave)
        if valor_anterior != nuevo_valor:
            db.add(PrecioHistorial(
                clave=f"modulos.{clave}",
                valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
                valor_nuevo=float(nuevo_valor),
                cambiado_por_id=current_user.id,
            ))
    cat["modulos"]["precios"].update(data)
    save_catalogo(cat)
    db.commit()
    return {"ok": True}


# ─── PRECIOS UNIFICADO + HISTORIAL ───────────────────────────────────────────

@router.put("/api/catalogo/precios")
async def update_precios_unificado(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Body: { "tipo": "piscinas"|"modulos",
            "campo": "precios"|"precios_lista"|"precios_sin_instalacion"|"precios_sin_instalacion_sin_equipo" (opcional, default "precios"),
            "precios": { "clave": valor, ... } }
    "precios" = precio CONTADO CON instalación (el que se cotiza al cliente por defecto).
    "precios_lista" = precio LISTA (base para financiación/cuotas — no confundir).
    "precios_sin_instalacion" = precio CONTADO en formato casco con equipo de filtrado,
    sin instalación — para ventas fuera del área de cobertura de instalación directa.
    "precios_sin_instalacion_sin_equipo" = precio CONTADO en formato casco solo, sin
    instalación y sin equipo de filtrado.
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    tipo = data.get("tipo", "").lower()
    campo = data.get("campo", "precios")
    if tipo not in ("piscinas", "modulos"):
        raise HTTPException(400, "tipo debe ser 'piscinas' o 'modulos'")
    campos_validos = ("precios", "precios_lista", "precios_sin_instalacion", "precios_sin_instalacion_sin_equipo")
    if campo not in campos_validos:
        raise HTTPException(400, f"campo debe ser uno de: {', '.join(campos_validos)}")
    nuevos_precios = data.get("precios", {})
    cat = load_catalogo()
    cat[tipo].setdefault(campo, {})
    precios_actuales = cat[tipo].get(campo, {})
    for clave, nuevo_valor in nuevos_precios.items():
        valor_anterior = precios_actuales.get(clave)
        if valor_anterior != nuevo_valor:
            db.add(PrecioHistorial(
                clave=f"{tipo}.{campo}.{clave}",
                valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
                valor_nuevo=float(nuevo_valor),
                cambiado_por_id=current_user.id if current_user else None,
            ))
    cat[tipo][campo].update(nuevos_precios)
    save_catalogo(cat)
    db.commit()
    return {"ok": True, "tipo": tipo, "campo": campo, "precios_actualizados": len(nuevos_precios)}


# ─── COMBOS ───────────────────────────────────────────────────────────────────

@router.put("/api/catalogo/combos/{nombre}")
async def upsert_combo(
    nombre: str,
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Body: { precio_lista, precio_contado, descripcion, plazos_max }"""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    cat = load_catalogo()
    cat.setdefault("combos", {})
    fotos_existentes = cat["combos"].get(nombre, {}).get("fotos", [])
    cat["combos"][nombre] = {
        "precio_lista": float(data.get("precio_lista") or 0),
        "precio_contado": float(data["precio_contado"]) if data.get("precio_contado") else None,
        "descripcion": data.get("descripcion", ""),
        "plazos_max": int(data.get("plazos_max") or 60),
        "fotos": fotos_existentes,  # se administran vía PUT /api/catalogo/fotos, no acá
    }
    save_catalogo(cat)
    return {"ok": True, "combos": cat["combos"]}


@router.delete("/api/catalogo/combos/{nombre}")
async def delete_combo(
    nombre: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if nombre not in cat.get("combos", {}):
        raise HTTPException(404, "Combo no encontrado")
    del cat["combos"][nombre]
    save_catalogo(cat)
    return {"ok": True}


@router.get("/api/catalogo/combos")
async def list_combos(current_user: Usuario = Depends(require_auth)):
    return load_catalogo().get("combos", {})


@router.get("/api/catalogo/historial-precios")
async def get_historial_precios(
    tipo: Optional[str] = None,
    clave: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(PrecioHistorial)
    if tipo:
        q = q.filter(PrecioHistorial.clave.like(f"{tipo}.%"))
    if clave:
        q = q.filter(PrecioHistorial.clave == clave)
    historial = q.order_by(PrecioHistorial.created_at.desc()).limit(limit).all()
    return [{
        "id": h.id,
        "clave": h.clave,
        "valor_anterior": float(h.valor_anterior) if h.valor_anterior is not None else None,
        "valor_nuevo": float(h.valor_nuevo) if h.valor_nuevo is not None else None,
        "cambiado_por": h.cambiado_por.nombre if h.cambiado_por else "",
        "created_at": h.created_at.isoformat() if h.created_at else "",
    } for h in historial]


# ─── API — HIDROMASAJES ───────────────────────────────────────────────────────

@router.get("/api/catalogo/hidromasajes")
async def get_hidromasajes(current_user: Usuario = Depends(require_auth)):
    """Devuelve la sección hidromasajes del catálogo."""
    cat = load_catalogo()
    return cat.get("hidromasajes", {})


@router.put("/api/catalogo/hidromasajes/precio")
async def set_precio_hidromasaje(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Actualiza el precio contado de un modelo de hidromasaje.
    Body: { modelo, precio_contado }
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    modelo = (data.get("modelo") or "").strip()
    precio = data.get("precio_contado")

    cat = load_catalogo()
    modelos = cat.get("hidromasajes", {}).get("modelos", {})
    if modelo not in modelos:
        raise HTTPException(404, f"Modelo '{modelo}' no encontrado en hidromasajes")

    precio_anterior = modelos[modelo].get("precio_contado")
    modelos[modelo]["precio_contado"] = float(precio) if precio is not None else None
    save_catalogo(cat)

    # Historial de precios
    if precio_anterior != modelos[modelo]["precio_contado"]:
        from database.models import PrecioHistorial
        h = PrecioHistorial(
            clave=f"hidromasajes.{modelo}.precio_contado",
            valor_anterior=precio_anterior,
            valor_nuevo=modelos[modelo]["precio_contado"],
            cambiado_por_id=current_user.id if current_user else None,
        )
        db.add(h)
        db.commit()

    return {"ok": True, "modelo": modelo, "precio_contado": modelos[modelo]["precio_contado"]}


@router.put("/api/catalogo/hidromasajes/opcional/precio")
async def set_precio_opcional_hidromasaje(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Actualiza el precio de un opcional/accesorio de hidromasaje.
    Body: { nombre, precio_contado }
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    nombre = (data.get("nombre") or "").strip()
    precio = data.get("precio_contado")

    cat = load_catalogo()
    opcionales = cat.get("hidromasajes", {}).get("opcionales", {})
    if nombre not in opcionales:
        raise HTTPException(404, f"Opcional '{nombre}' no encontrado")

    opcionales[nombre]["precio_contado"] = float(precio) if precio is not None else None
    save_catalogo(cat)
    return {"ok": True, "nombre": nombre, "precio_contado": opcionales[nombre]["precio_contado"]}


@router.put("/api/catalogo/hidromasajes/fotos")
async def set_fotos_hidromasaje(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Actualiza las fotos de un modelo de hidromasaje.
    Body: { modelo, fotos: [url1, url2, ...] }
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    modelo = (data.get("modelo") or "").strip()
    fotos = data.get("fotos", [])

    cat = load_catalogo()
    modelos = cat.get("hidromasajes", {}).get("modelos", {})
    if modelo not in modelos:
        raise HTTPException(404, f"Modelo '{modelo}' no encontrado")

    modelos[modelo]["fotos"] = [str(f) for f in fotos if f]
    save_catalogo(cat)
    return {"ok": True, "modelo": modelo, "fotos": modelos[modelo]["fotos"]}


# ═══════════════════════════════════════════════════════════════════════════════
# Gestión genérica de categorías de productos (no-legacy)
# Categorías legacy tienen su propia UI específica: piscinas, módulos, etc.
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORIAS_LEGACY = {"piscinas", "modulos", "modulos_deposito", "combos"}


def _items_key(cat_data: dict) -> str:
    """Clave del dict que contiene los ítems (modelos o productos) de la sección."""
    return "modelos" if "modelos" in cat_data else "productos"


def _get_items(cat_data: dict) -> dict:
    """Dict de ítems de la sección."""
    return cat_data.get("modelos") or cat_data.get("productos") or {}


@router.get("/api/catalogo/categorias")
async def listar_categorias_genericas():
    """Lista todas las categorías no-legacy con sus productos y precios."""
    cat = load_catalogo()
    resultado = {}
    for nombre, datos in cat.items():
        if nombre in CATEGORIAS_LEGACY or not isinstance(datos, dict):
            continue
        key = _items_key(datos)
        items = datos.get(key) or {}
        resultado[nombre] = {
            "titulo": datos.get("titulo") or nombre.replace("_", " ").title(),
            "key": key,
            "productos": {
                k: {
                    "descripcion": v.get("descripcion_corta") or v.get("descripcion") or "",
                    "precio_contado": v.get("precio_contado"),
                    "fotos": v.get("fotos") or [],
                }
                for k, v in items.items()
                if isinstance(v, dict)
            },
        }
    return resultado


@router.post("/api/catalogo/categorias")
async def crear_categoria_generica(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Crea una nueva categoría de productos en el catálogo."""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    titulo = (data.get("titulo") or "").strip()
    nombre = (data.get("nombre") or titulo).strip().lower().replace(" ", "_")
    nota = (data.get("nota") or "").strip()
    if not nombre:
        raise HTTPException(400, "Falta el nombre de la categoría")
    if not titulo:
        titulo = nombre.replace("_", " ").title()
    cat = load_catalogo()
    if nombre in cat:
        raise HTTPException(409, f"La categoría '{nombre}' ya existe")
    cat[nombre] = {
        "titulo": titulo,
        "nota": nota,
        "pago": "Contado o tarjeta.",
        "modelos": {},
    }
    save_catalogo(cat)
    return {"ok": True, "nombre": nombre, "titulo": titulo}


@router.delete("/api/catalogo/categorias/{cat_nombre}")
async def eliminar_categoria_generica(
    cat_nombre: str,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Elimina una categoría no-legacy del catálogo."""
    _write_auth(x_api_key, current_user)
    if cat_nombre in CATEGORIAS_LEGACY:
        raise HTTPException(400, f"'{cat_nombre}' es una categoría del sistema y no se puede eliminar")
    cat = load_catalogo()
    if cat_nombre not in cat:
        raise HTTPException(404, f"Categoría '{cat_nombre}' no encontrada")
    del cat[cat_nombre]
    save_catalogo(cat)
    return {"ok": True}


@router.post("/api/catalogo/categorias/{cat_nombre}/productos")
async def agregar_producto_generico(
    cat_nombre: str,
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Agrega un producto / modelo a una categoría existente."""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    nombre_prod = (data.get("nombre") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()
    precio_raw = data.get("precio_contado")
    if not nombre_prod:
        raise HTTPException(400, "Falta el nombre del producto")
    cat = load_catalogo()
    if cat_nombre not in cat:
        raise HTTPException(404, f"Categoría '{cat_nombre}' no encontrada")
    key = _items_key(cat[cat_nombre])
    if key not in cat[cat_nombre]:
        cat[cat_nombre][key] = {}
    if nombre_prod in cat[cat_nombre][key]:
        raise HTTPException(409, f"El producto '{nombre_prod}' ya existe en '{cat_nombre}'")
    cat[cat_nombre][key][nombre_prod] = {
        "descripcion_corta": descripcion,
        "precio_contado": float(precio_raw) if precio_raw is not None and str(precio_raw).strip() != "" else None,
        "fotos": [],
    }
    save_catalogo(cat)
    return {"ok": True, "nombre": nombre_prod}


@router.put("/api/catalogo/categorias/{cat_nombre}/productos/{prod_nombre}/precio")
async def actualizar_precio_generico(
    cat_nombre: str,
    prod_nombre: str,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Actualiza el precio de contado de un producto genérico. Registra historial."""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    precio_raw = data.get("precio_contado")
    cat = load_catalogo()
    if cat_nombre not in cat:
        raise HTTPException(404, f"Categoría '{cat_nombre}' no encontrada")
    items = _get_items(cat[cat_nombre])
    if prod_nombre not in items:
        raise HTTPException(404, f"Producto '{prod_nombre}' no encontrado en '{cat_nombre}'")
    precio_nuevo = float(precio_raw) if precio_raw is not None and str(precio_raw).strip() != "" else None
    precio_anterior = items[prod_nombre].get("precio_contado")
    items[prod_nombre]["precio_contado"] = precio_nuevo
    save_catalogo(cat)
    if precio_nuevo is not None and precio_nuevo != precio_anterior:
        try:
            db.add(PrecioHistorial(
                clave=f"{cat_nombre}.{prod_nombre}",
                valor_anterior=float(precio_anterior) if precio_anterior is not None else None,
                valor_nuevo=precio_nuevo,
                cambiado_por_id=current_user.id if current_user else None,
            ))
            db.commit()
        except Exception:
            db.rollback()
    return {"ok": True, "precio_contado": precio_nuevo}


@router.delete("/api/catalogo/categorias/{cat_nombre}/productos/{prod_nombre}")
async def eliminar_producto_generico(
    cat_nombre: str,
    prod_nombre: str,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Elimina un producto de una categoría."""
    _write_auth(x_api_key, current_user)
    cat = load_catalogo()
    if cat_nombre not in cat:
        raise HTTPException(404, f"Categoría '{cat_nombre}' no encontrada")
    key = _items_key(cat[cat_nombre])
    items = cat[cat_nombre].get(key, {})
    if prod_nombre not in items:
        raise HTTPException(404, f"Producto '{prod_nombre}' no encontrado en '{cat_nombre}'")
    del items[prod_nombre]
    save_catalogo(cat)
    return {"ok": True}
