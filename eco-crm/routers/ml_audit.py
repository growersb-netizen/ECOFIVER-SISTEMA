"""
Auditoría COMPLETA v8.2 — Calidad 100% en todas las publicaciones MercadoLibre de EcoFiver.

CAMBIOS v8.2 (respecto a v8.1)
────────────────────────────────
• Fix CRÍTICO #2: _detectar_tipo() ahora usa SOLO el título — NO la descripción.
  En v8.1 la detección usaba titulo+descripcion, lo que causaba que reposeras cuyas
  descripciones mencionaban "spa" o "jacuzzi" (ej: "ideal junto al spa o piscina")
  fueran clasificadas como "spa jacuzzi hidromasaje" y luego cerradas incorrectamente.
  La descripción nunca debe usarse para detectar el tipo de producto — puede mencionar
  cualquier categoría en contexto sin que eso cambie el producto.
• Recuperación dinámica: en Fase 0 se consultan todos los items cerrados en ML y se
  reactivan automáticamente los que tienen "reposera" o "tumbona" en el título
  (cubre tanto los cerrados en v8 como los cerrados incorrectamente en v8.1).
• Fase 6 eliminada: se ELIMINÓ el cierre automático de publicaciones por categoría.
  El audit ahora SOLO actualiza contenido (título, descripción, atributos).
  Los mismatches de categoría se loguean como WARNING para revisión manual.
  Razón: la detección de tipo basada en keywords no es 100% confiable para tomar
  decisiones destructivas (cerrar publicaciones). Mejor ser conservadores.

CAMBIOS v8.1 (respecto a v8)
─────────────────────────────
• Fix CRÍTICO: detección de tipo reordenada — spa/jacuzzi se detecta ANTES que piscina.
• Recuperación automática: reactiva los 12 items cerrados incorrectamente en v8.
• Categorías aceptadas para spa: "bañera", "hidromasaje", "spa" y similares.

CAMBIOS v8 (respecto a v7)
──────────────────────────
• SIN llamadas a IA — generación 100% por reglas y plantillas (más rápido, sin tokens).
• Generación de títulos inteligente: extrae modelo y dimensiones del título actual
  y construye el mejor título posible por tipo de producto (40-60 chars, SEO-óptimo).
• Reemplazo de título agresivo: se reemplaza si el título score < 20/25
  (= muy corto O sin keywords de producto), no solo si tiene < 20 chars.
• Ficha técnica (atributos): rellena BRAND + CONDITION + WARRANTY por categoría.
  Los atributos incompletos hacen perder posición en ML — este es el gap más crítico.
• Validación de categoría: detecta publicaciones en categoría incorrecta (producto ≠ categoría),
  las cierra vía API y genera reporte al final.
• condition = "new" siempre explícito en cada PUT.
• Pausa reducida a 1.5 s (dentro del rate-limit de ML).

FUNCIONAMIENTO
──────────────
Corre UNA SOLA VEZ por AUDIT_VERSION, 5 minutos después del primer arranque.
Para forzar re-ejecución: incrementar AUDIT_VERSION → "v9".

QUÉ EVALÚA
──────────
1. Título          (keywords, largo 40-60 chars, sin chars prohibidos)
2. Descripción     (texto plano, mínimo 1500 chars, 6 bloques EcoFiver estándar)
3. Atributos       (brand, condition, warranty — mejora posición en filtros ML)
4. Categoría       (coherencia con tipo de producto detectado)
5. Fotos           (solo cuenta — no puede agregar desde API)
6. Precio          (> 0 para que sea comprable)

ACCIONES AUTOMÁTICAS
──────────────────────
✓ Actualiza descripción (siempre posible, máximo impacto en conversión)
✓ Actualiza título si ML lo permite (muchos están bloqueados en listings con historial)
✓ Actualiza atributos: brand, condition, warranty
✓ Cierra (pausa) publicaciones en categoría claramente incorrecta
✓ Procesa primero las publicaciones con MENOR PUNTUACIÓN (máximo impacto)

NO HACE (demasiado riesgo para ventas activas)
──────────────────────────────────────────────
✗ No cambia precios
✗ No toca publicaciones de catálogo ML (inaccesibles por API)
✗ No agrega fotos (limitación de la API de ML)
"""

import asyncio
import json
import logging
import re

import httpx
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import ConfiguracionSistema, PublicacionML
from utils.contexto_ecofiver import DESC_ENCABEZADO, DESC_PIE

log = logging.getLogger(__name__)

# ── Versión: incrementar para forzar re-ejecución ──────────────────────────────
AUDIT_VERSION    = "v8.2"
AUDIT_FLAG_KEY   = "ml_audit_version"
REPORT_FLAG_KEY  = "ml_audit_v8_reporte"   # guarda JSON con resultado

# Items cerrados INCORRECTAMENTE en v8 (clasificación de tipo errónea — spas como piscinas):
_ITEMS_CERRADOS_INCORRECTAMENTE_V8 = [
    "MLA3752835918",  # Bañera Spa Amplio 197 Cm Prfv (bañeras > sin hidromasajes)
    "MLA3752834692",  # Jacuzzi Amplio 197x142 Prfv (bañeras > con hidromasajes)
    "MLA3752823596",  # Tina Spa Amplio 197 Cm Prfv (bañeras > sin hidromasajes)
    "MLA3752823542",  # Tina Spa Amplio 197x142 Prfv (bañeras > sin hidromasajes)
    "MLA3752796258",  # Jacuzzi Amplio 197 Cm Prfv (bañeras > con hidromasajes)
    "MLA3752454096",  # Tina Spa Compacto 110x110 Prfv (bañeras > con hidromasajes)
    "MLA3752450554",  # Tina Spa Cuadrado 110 Cm Prfv (bañeras > sin hidromasajes)
    "MLA3752449654",  # Spa Cuadrado 110x110 Acrílico (bañeras > sin hidromasajes)
    "MLA3752449312",  # Jacuzzi Cuadrado 110x110 Prfv (bañeras > con hidromasajes)
    "MLA3752437940",  # Tina Spa Angular 110x110 Prfv (bañeras > sin hidromasajes)
    "MLA3752436826",  # Jacuzzi Angular 110 Cm Prfv (bañeras > con hidromasajes)
    "MLA3752437004",  # Spa Cuadrado 110 Cm Acrílico (bañeras > sin hidromasajes)
    # MLA3752449638 NO se reactiva — estaba en "repisas esquineras", categoría incorrecta real
]

# Items cerrados INCORRECTAMENTE en v8.1 (reposeras mal clasificadas como spa):
# La detección usaba descripcion, donde las reposeras mencionaban "spa" o "jacuzzi".
_ITEMS_CERRADOS_INCORRECTAMENTE_V8_1 = [
    "MLA3791104260",  # Reposera De Fibra De Vidrio 172 Cm Para Uso E
    "MLA3791091388",  # Reposeras De Fibra De Vidrio 172 Cm Para Solárium
    "MLA3791091058",  # Juego 2 Reposeras Prfv 172 Cm Para Sol Y Jard
    "MLA3791090648",  # Juego De 2 Reposeras Prfv 172 Cm Para Piscina
    "MLA3791090810",  # Juego 2 Reposeras Prfv 172 Cm Para Bordes De Pileta
    "MLA3791091510",  # Reposeras Prfv 2 Unidades 172 Cm Para Solárium
    "MLA3791091264",  # Juego 2 Reposeras Prfv 172 Cm Para Espacio Exterior
    "MLA3791090630",  # Juego 2 Reposeras Prfv 172 Cm Para Espacios Al Aire Libre
    "MLA3791091444",  # Reposeras De Prfv 172 Cm Para Bordes De Pileta
    "MLA3791090846",  # Reposera Blanca De Prfv 172 Cm Para Terraza
    "MLA3791091316",  # Juego 2 Reposeras Blancas 172 Cm Para Jardín
    "MLA3791091468",  # Reposeras Prfv 2 Unidades 172 Cm Para Terraza
    "MLA3791091522",  # Juego 2 Reposeras Fibra De Vidrio 172 Cm Blancas
    "MLA3791067432",  # Reposeras Prfv 2 Unidades 172 Cm Para Bordes de Pileta
    "MLA3791090490",  # Juego 2 Reposeras Prfv 172 Cm Para Espacios Exteriores
    "MLA3791067028",  # Reposera Prfv 2 Unidades 172 Cm Para Solárium
    "MLA3791090444",  # Reposera De Prfv Blanca 172 Cm Para Uso En Pileta
    "MLA3791067324",  # Juego De 2 Reposeras Prfv 172x52 Cm Para Terraza
    "MLA3791090602",  # Juego De 2 Reposeras De Fibra De Vidrio 172 Cm
    "MLA3791090554",  # Juego De 2 Reposeras 172 Cm De Prfv Para Uso Exterior
    "MLA3791090542",  # Reposera Blanca 172 Cm De Fibra De Vidrio Para Exterior
    "MLA3791090572",  # Reposera Blanca De Fibra De Vidrio 172 Cm Exterior
    "MLA3791090328",  # Reposera Blanca 172 Cm De Prfv Para Terraza Y Jardín
]

# ── Umbrales de calidad ────────────────────────────────────────────────────────
THRESHOLD_OPTIMIZAR = 80   # publicaciones por debajo de esto se reescriben
THRESHOLD_TITULO    = 20   # score título < este valor → reemplazar con template
_PAUSA_ENTRE_ITEMS  = 1.5  # segundos entre publicaciones (rate-limit ML)

# ── Errores conocidos de ML que no son bugs nuestros ─────────────────────────
_TITULO_NO_MODIFICABLE = "item.title.not_modifiable"

# ── Keywords esperadas por categoría de ML (para validar coherencia) ──────────
_CATEGORIA_KEYWORDS: dict[str, list[str]] = {
    "piscina de fibra de vidrio":     ["pileta", "piscina", "natatorio", "spa", "agua"],
    "spa jacuzzi hidromasaje":        ["spa", "jacuzzi", "hidromasaje", "bañera", "pileta"],
    "módulo habitacional":            ["modulo", "habitacional", "construccion", "prefabricad"],
    "vivienda modular prefabricada":  ["vivienda", "casa", "modular", "prefabricad"],
    "bañera de acrílico sanitario":   ["baño", "bañera", "sanitario", "ducha"],
    "receptáculo de ducha acrílico":  ["baño", "ducha", "sanitario", "receptaculo"],
    "baño químico portátil":          ["baño", "sanitario", "quimico", "portátil"],
    "garita de seguridad prefabricada": ["garita", "seguridad", "caseta", "vigilancia"],
    "reposera de fibra de vidrio":    ["reposera", "tumbona", "jardin", "pileta", "mueble"],
    "cucha para perros":              ["cucha", "perro", "mascota", "animal"],
    "combo piscina y módulo":         ["pileta", "piscina", "modulo", "combo"],
    "quincho o pérgola prefabricada": ["quincho", "pergola", "jardin", "espacio"],
}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE FLAG (evitar doble ejecución)
# ══════════════════════════════════════════════════════════════════════════════

def _get_audit_flag(db: Session) -> str:
    row = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == AUDIT_FLAG_KEY
    ).first()
    return row.valor if row else ""


def _set_audit_flag(db: Session, version: str):
    row = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == AUDIT_FLAG_KEY
    ).first()
    if row:
        row.valor = version
    else:
        db.add(ConfiguracionSistema(clave=AUDIT_FLAG_KEY, valor=version))
    db.commit()


def _set_reporte(db: Session, reporte: dict):
    """Guarda el reporte JSON final en ConfiguracionSistema."""
    texto = json.dumps(reporte, ensure_ascii=False)
    row = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == REPORT_FLAG_KEY
    ).first()
    if row:
        row.valor = texto
    else:
        db.add(ConfiguracionSistema(clave=REPORT_FLAG_KEY, valor=texto))
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  SCORING DE CALIDAD
# ══════════════════════════════════════════════════════════════════════════════

def _score_item(item: dict, desc_actual: str) -> dict:
    """
    Evalúa la calidad de una publicación en 4 dimensiones.
    Retorna {"score": int, "issues": list[str], "detalle": dict, "tipo": str}.
    Escala: 0 (pésima) → 100 (perfecta).
    """
    titulo  = item.get("title", "")
    precio  = item.get("price") or 0
    fotos   = len(item.get("pictures", []))
    desc    = desc_actual or ""
    score   = 0
    issues  = []
    detalle = {}

    # ── TÍTULO (0-25 puntos) ──────────────────────────────────────────────────
    tlen = len(titulo)
    if 40 <= tlen <= 60:
        score += 15; detalle["titulo_largo"] = "ok"
    elif 30 <= tlen < 40:
        score += 8; issues.append("título corto (< 40 chars)")
    elif tlen > 60:
        score += 5; issues.append("título largo (> 60 chars)")
    else:
        issues.append("título muy corto (< 30 chars)")

    tipo = _detectar_tipo(titulo, desc)
    if tipo != "producto EcoFiver":
        score += 10; detalle["tipo_detectado"] = tipo
    else:
        issues.append("tipo de producto no identificable en título")

    # ── DESCRIPCIÓN (0-45 puntos) ─────────────────────────────────────────────
    dlen = len(desc)
    if dlen >= 1500:
        score += 25; detalle["desc_chars"] = dlen
    elif dlen >= 800:
        score += 12; issues.append(f"descripción corta ({dlen} chars — necesita ≥1500)")
    elif dlen >= 200:
        score += 5; issues.append(f"descripción muy corta ({dlen} chars)")
    else:
        issues.append("sin descripción o menor a 200 chars")

    desc_lo = desc.lower()
    if any(k in desc_lo for k in ["garantía", "garantia", "10 años"]):
        score += 5; detalle["tiene_garantia"] = True
    else:
        issues.append("falta bloque de garantía")

    if any(k in desc_lo for k in ["instalación", "instalacion", "mismo día", "mismo dia"]):
        score += 8; detalle["tiene_instalacion"] = True
    else:
        issues.append("falta bloque de instalación")

    if any(k in desc_lo for k in ["cuotas", "tarjeta", "pago", "mercadolibre"]):
        score += 4; detalle["tiene_pago"] = True
    else:
        issues.append("falta bloque de formas de pago")

    if any(k in desc_lo for k in ["san telmo", "paso del rey", "zárate", "zarate", "retiro"]):
        score += 3; detalle["tiene_logistica"] = True
    else:
        issues.append("falta bloque de logística/retiro")

    # ── PRECIO (0-15 puntos) ──────────────────────────────────────────────────
    if precio and precio > 0:
        score += 15; detalle["precio"] = precio
    else:
        issues.append("precio = 0 o sin precio")

    # ── FOTOS (0-15 puntos) ───────────────────────────────────────────────────
    if fotos >= 5:
        score += 15; detalle["fotos"] = fotos
    elif fotos >= 3:
        score += 10; issues.append(f"pocas fotos ({fotos} — ML recomienda ≥5)")
    elif fotos >= 1:
        score += 5; issues.append(f"muy pocas fotos ({fotos})")
    else:
        issues.append("sin fotos (crítico para conversión)")

    return {
        "score": min(score, 100),
        "issues": issues,
        "detalle": detalle,
        "tipo": tipo,
    }


def _score_titulo(titulo: str) -> int:
    """Puntaje del título solo (0-25), para decidir si reemplazar."""
    score = 0
    tlen  = len(titulo)
    if 40 <= tlen <= 60:
        score += 15
    elif 30 <= tlen < 40:
        score += 8
    elif tlen > 60:
        score += 5
    if _detectar_tipo(titulo) != "producto EcoFiver":
        score += 10
    return score


# ══════════════════════════════════════════════════════════════════════════════
#  DETECCIÓN DE TIPO DE PRODUCTO
# ══════════════════════════════════════════════════════════════════════════════

def _detectar_tipo(titulo: str, descripcion: str = "") -> str:
    # v8.2: Se usa SOLO el título para detectar el tipo de producto.
    # La descripción queda como parámetro por compatibilidad pero se ignora.
    # Motivo: las descripciones pueden mencionar cualquier tipo de producto en contexto
    # (ej: "reposera ideal junto al spa") sin que eso cambie lo que el item es.
    texto = titulo.lower()

    # ── SPA / JACUZZI — va PRIMERO porque sus keywords son más específicas.
    # PRFV y "fibra de vidrio" son materiales usados también en spas y bañeras,
    # no son exclusivos de piscinas, por eso NO van en el bloque de piscina.
    if any(k in texto for k in [
        "spa", "jacuzzi", "hidromasaje", "jets", "blower",
        "quadra", "orbis", "delta", "spa recta", "tina spa",
    ]):
        return "spa jacuzzi hidromasaje"

    # ── PISCINA — keywords exclusivas (no incluye "prfv" ni "fibra de vidrio")
    if any(k in texto for k in [
        "piscin", "pileta", "natatorio", "minideck",
        "miniportante", "autoportante", "arco romano",
        "monoblock", "wave", "bali",
    ]):
        return "piscina de fibra de vidrio"

    if any(k in texto for k in [
        "vivienda modular", "casa prefabricada", "casa modular", "vivienda prefabricada",
        "24 m", "25 m", "36 m", "48 m", "60 m",
    ]):
        return "vivienda modular prefabricada"

    if any(k in texto for k in [
        "módulo", "modulo", "habitacional", "celulosa estructural",
        "espacio habitacional", "módulo auxiliar",
    ]):
        return "módulo habitacional"

    if any(k in texto for k in [
        "bañera", "banhera", "lumina", "sensa", "vento", "aqua curve", "pure",
    ]):
        return "bañera de acrílico sanitario"

    if any(k in texto for k in [
        "receptáculo", "receptaculo", "ducha", "shower",
    ]):
        return "receptáculo de ducha acrílico"

    if any(k in texto for k in ["baño químico", "quimico", "portátil", "sanitario portátil"]):
        return "baño químico portátil"

    if any(k in texto for k in ["garita", "seguridad", "vigilancia", "caseta"]):
        return "garita de seguridad prefabricada"

    if any(k in texto for k in ["reposera", "tumbona", "deck chair"]):
        return "reposera de fibra de vidrio"

    if any(k in texto for k in ["cucha", "casilla para perro", "casita perro"]):
        return "cucha para perros"

    if any(k in texto for k in ["combo", "kit piscina", "piscina + módulo", "pileta y modulo"]):
        return "combo piscina y módulo"

    if any(k in texto for k in ["quincho", "pérgola", "pergola", "gazebo"]):
        return "quincho o pérgola prefabricada"

    return "producto EcoFiver"


# ══════════════════════════════════════════════════════════════════════════════
#  SANEAMIENTO Y GENERACIÓN DE TÍTULO (sin IA)
# ══════════════════════════════════════════════════════════════════════════════

def _sanear_titulo(titulo: str) -> str:
    """Elimina caracteres problemáticos en ML y corta a 60 sin partir palabras."""
    limpio = re.sub(r'[,|:;!?"–—_%*#@]', ' ', titulo)
    limpio = re.sub(r'\s+', ' ', limpio).strip()
    if len(limpio) <= 60:
        return limpio
    corte = limpio[:60]
    if ' ' in corte:
        corte = corte[:corte.rfind(' ')]
    return corte.strip()


def _generar_titulo_template(tipo: str, titulo_actual: str) -> str:
    """
    Genera un título SEO-optimizado sin IA.
    Extrae modelo/dimensiones del título actual y construye el mejor título posible.
    Siempre retorna un título de 35-60 chars, limpio, sin caracteres prohibidos.

    Estructura objetivo: Producto + Material + Modelo/medida + Diferenciador
    (basada en mejores prácticas ML 2026: keywords primero, diferenciador al final)
    """
    ta    = titulo_actual.strip()
    ta_lo = ta.lower()

    # ── Extraer dimensiones (ej: "4x2", "4.5 x 2.5", "3 x 2 m") ─────────────
    dim_m = re.search(r'(\d+[.,]?\d*)\s*[xX×]\s*(\d+[.,]?\d*)', ta)
    dim   = f"{dim_m.group(1)}x{dim_m.group(2)}" if dim_m else ""

    # ── Extraer metraje (ej: "12m2", "18 m2", "18m") ─────────────────────────
    metro_m = re.search(r'(\d+)\s*m(?:2|²)?(?:\s|$)', ta_lo)
    metro   = f"{metro_m.group(1)}m2" if metro_m else ""

    # ── Modelos de piscina ────────────────────────────────────────────────────
    mod_piscina = ""
    for m in ["minideck grande", "minideck chico", "minideck",
              "miniportante", "autoportante", "arco romano", "wave", "bali"]:
        if m in ta_lo:
            mod_piscina = m.title()
            break

    # ── Modelos de spa ────────────────────────────────────────────────────────
    mod_spa = ""
    for m in ["quadra", "orbis", "delta", "recta"]:
        if m in ta_lo:
            mod_spa = m.title()
            break

    # ── Modelos de bañera ─────────────────────────────────────────────────────
    mod_bañera = ""
    for m in ["lumina", "sensa", "vento", "aqua", "curve", "pure", "vita"]:
        if m in ta_lo:
            mod_bañera = m.title()
            break

    # ── Candidatos por tipo (de más específico a más genérico) ────────────────
    def _candidatos() -> list[str]:
        if tipo == "piscina de fibra de vidrio":
            return [
                f"Piscina fibra vidrio {mod_piscina} {dim} instalacion incluida"
                    if mod_piscina and dim else "",
                f"Pileta fibra de vidrio {mod_piscina} PRFV instalacion dia"
                    if mod_piscina else "",
                f"Piscina fibra de vidrio {dim}m PRFV instalacion incluida"
                    if dim else "",
                "Piscina de fibra de vidrio PRFV instalacion incluida",
            ]
        if tipo == "spa jacuzzi hidromasaje":
            return [
                f"Spa jacuzzi {mod_spa} acrílico jets instalacion incluida"
                    if mod_spa else "",
                "Spa jacuzzi hidromasaje acrílico PRFV jets instalacion",
            ]
        if tipo == "módulo habitacional":
            return [
                f"Modulo habitacional {metro} prefabricado instalacion dia"
                    if metro else "",
                "Modulo habitacional prefabricado instalacion el dia",
            ]
        if tipo == "vivienda modular prefabricada":
            return [
                f"Vivienda modular {metro} prefabricada celulosa estructural"
                    if metro else "",
                "Vivienda modular prefabricada celulosa estructural",
            ]
        if tipo == "bañera de acrílico sanitario":
            return [
                f"Bañera {mod_bañera} acrílico sanitario PRFV garantia 10 años"
                    if mod_bañera else "",
                "Bañera acrílico sanitario PRFV resistente garantia 10 años",
            ]
        if tipo == "receptáculo de ducha acrílico":
            return [
                "Receptaculo de ducha acrílico sanitario PRFV antideslizante",
            ]
        if tipo == "baño químico portátil":
            return [
                "Baño quimico portátil polipropileno alta densidad sanitario",
            ]
        if tipo == "garita de seguridad prefabricada":
            return [
                "Garita de seguridad prefabricada PRFV estructura metálica",
            ]
        if tipo == "reposera de fibra de vidrio":
            return [
                "Reposera fibra de vidrio PRFV piscina pileta jardin",
            ]
        if tipo == "cucha para perros":
            return [
                "Cucha casilla para perros madera tratada varios tamaños",
            ]
        if tipo == "combo piscina y módulo":
            return [
                "Combo piscina fibra de vidrio y modulo habitacional",
            ]
        if tipo == "quincho o pérgola prefabricada":
            return [
                "Quincho pergola prefabricada instalacion el dia",
            ]
        return ["Producto EcoFiver fabricacion propia Zarate Buenos Aires"]

    for candidato in _candidatos():
        if not candidato:
            continue
        saneado = _sanear_titulo(candidato)
        if 35 <= len(saneado) <= 60:
            return saneado

    # Fallback: usar el actual saneado si tiene suficiente largo
    if len(ta) >= 20:
        return _sanear_titulo(ta)
    return _sanear_titulo("Producto EcoFiver fabricacion propia Zarate")


# ══════════════════════════════════════════════════════════════════════════════
#  ATRIBUTOS (ficha técnica ML) — crítico para posición en filtros
# ══════════════════════════════════════════════════════════════════════════════

def _atributos_para_tipo(tipo: str) -> list[dict]:
    """
    Retorna la lista de atributos universales + específicos por tipo.
    Usa los IDs de atributo estándar de ML (válidos en todas las categorías).
    Solo incluimos atributos con altísima probabilidad de ser aceptados.
    La estrategia es: BRAND + WARRANTY siempre, más específicos por tipo.
    """
    # Atributos universales — válidos en todas las categorías ML
    base = [
        {"id": "BRAND",             "value_name": "EcoFiver"},
        {"id": "ITEM_CONDITION",    "value_name": "new"},
        {"id": "WARRANTY_TYPE",     "value_name": "Garantía del vendedor"},
        {"id": "WARRANTY_TIME",     "value_name": "10 años"},
    ]

    # Atributos específicos por tipo
    extra: dict[str, list[dict]] = {
        "piscina de fibra de vidrio": [
            {"id": "MAIN_MATERIAL", "value_name": "Fibra de vidrio"},
        ],
        "spa jacuzzi hidromasaje": [
            {"id": "MAIN_MATERIAL", "value_name": "Acrílico"},
        ],
        "módulo habitacional": [
            {"id": "MAIN_MATERIAL", "value_name": "Celulosa estructural"},
        ],
        "vivienda modular prefabricada": [
            {"id": "MAIN_MATERIAL", "value_name": "Celulosa estructural"},
        ],
        "bañera de acrílico sanitario": [
            {"id": "MAIN_MATERIAL", "value_name": "Acrílico"},
        ],
        "receptáculo de ducha acrílico": [
            {"id": "MAIN_MATERIAL", "value_name": "Acrílico"},
        ],
        "baño químico portátil": [
            {"id": "MAIN_MATERIAL", "value_name": "Polipropileno"},
        ],
        "garita de seguridad prefabricada": [
            {"id": "MAIN_MATERIAL", "value_name": "Fibra de vidrio"},
        ],
        "reposera de fibra de vidrio": [
            {"id": "MAIN_MATERIAL", "value_name": "Fibra de vidrio"},
        ],
        "cucha para perros": [
            {"id": "MAIN_MATERIAL", "value_name": "Madera"},
        ],
    }

    return base + extra.get(tipo, [])


# ══════════════════════════════════════════════════════════════════════════════
#  PLANTILLAS DE DESCRIPCIÓN (texto plano, sin HTML)
# ══════════════════════════════════════════════════════════════════════════════

def _descripcion_template(tipo: str, titulo_actual: str, precio: float) -> str:
    """
    Genera descripción completa de alta calidad en texto plano (sin HTML).
    ML solo acepta texto plano desde 2018.
    Cumple todos los bloques estándar EcoFiver para calidad 100/100.
    """
    precio_str = (
        f"${precio:,.0f}".replace(",", ".")
        if precio and precio > 0
        else "(ver precio en la publicación)"
    )

    cuerpos: dict[str, str] = {

        "piscina de fibra de vidrio": f"""Piscina de fibra de vidrio (PRFV) fabricada por EcoFiver

Esta piscina de fibra de vidrio, también conocida como pileta de fibra, natatorio monoblock o piscina de PRFV, se fabrica en la planta de EcoFiver en Zárate, Buenos Aires, mediante un proceso de laminado en capas que garantiza la resistencia estructural sin juntas ni soldaduras. El casco es de una sola pieza — monobloque — sin uniones que puedan filtrar. El gelcoat exterior es parte de la estructura, no una pintura superficial: no se descasca, no amarillea y resiste el cloro, el sol y la intemperie durante décadas.

Qué incluye el precio de {precio_str}

Fabricación completa del casco en planta propia EcoFiver.
Traslado desde Zárate, Buenos Aires, hasta el lugar de instalación.
Instalación profesional completa con equipo propio: nivelación, conexión hidráulica y puesta en marcha del sistema de filtrado.
El sistema se entrega probado y funcionando al finalizar la jornada de instalación.

No se terceriza ninguna parte del proceso. EcoFiver fabrica, transporta e instala con su propio equipo.

Qué NO incluye: excavación del pozo (para modelos que la requieren), sistema de calefacción, cubierta, iluminación submarina ni productos químicos de arranque. Estos son opcionales y se contratan aparte.

Colores disponibles sin cargo adicional: blanco, gris perla, azul turquesa, verde agua y piedra (varía según modelo).

Modelos disponibles

Minideck Chico y Minideck Grande: autoportantes, sin excavación. Van sobre cualquier superficie firme. Instalación en el mismo día.
Miniportante: semi-autoportante, requiere excavación mínima. Ideal para espacios donde el pozo completo no es viable.
Autoportante: completamente autoportante, sin excavación. Versión de mayor capacidad.
Arco Romano: diseño clásico con línea curva. Requiere pozo.
Wave y Bali: diseño contemporáneo con línea orgánica. Requieren pozo.

Cómo es la instalación

El equipo de instalación llega con el equipamiento necesario y completa todo en una sola jornada. Al terminar, la piscina está instalada, el agua circula por el filtro y el sistema está probado. Para modelos que requieren pozo, el comprador solo necesita tenerlo excavado con las dimensiones indicadas y el acceso de agua disponible. Para modelos autoportantes no es necesaria ninguna preparación previa.

Garantía de 10 años — la más extensa del rubro

Todos los cascos de fibra de vidrio de EcoFiver cuentan con 10 años de garantía sobre la estructura y el laminado. Si en ese período se presenta cualquier inconveniente estructural, el equipo de postventa de EcoFiver lo resuelve sin cargo. La garantía se entrega por escrito junto al certificado de calidad premium.

Cómo pagarlo

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta al momento de la compra. La compra está respaldada por MercadoLibre. Para coordinar la entrega y la fecha de instalación, nos contactamos después de que se concreta la compra.

Retiro y envío

Retiro SIN CARGO en dos puntos: CABA zona San Telmo (subte Línea C estación San Juan / Línea A estación Piedras, colectivos por Av. San Juan y Paseo Colón) y Zona Oeste Paso del Rey (Autopista del Oeste Ruta 7, Tren Sarmiento estación Paso del Rey).

Para envío e instalación en tu domicilio: el flete se cotiza a $4.000 por kilómetro desde la fábrica en Zárate, Buenos Aires. Si nos compartís tu código postal o localidad, calculamos el costo exacto sin compromiso. Ejemplos orientativos: CABA unos 90 km, GBA Oeste/Norte unos 70-80 km.""",

        "spa jacuzzi hidromasaje": f"""Spa de hidromasaje de acrílico sanitario fabricado por EcoFiver

Este spa de hidromasaje, también conocido como jacuzzi, bañera de jets o hidromasaje, se fabrica en acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material base que se usa en las piscinas de alta gama. La estructura autoportante metálica está incluida: se instala sin necesidad de obra de albañilería ni encofrado. Apto para uso interior o exterior, resistente a la intemperie y a los productos de tratamiento del agua.

Precio publicado: {precio_str} — qué incluye

La unidad de spa completa con acrílico sanitario y estructura metálica.
Motor de hidromasaje según el modelo.
Jets dirigibles vista cromo (cantidad varía por modelo: 4 a 8 jets).
Pulsador neumático de encendido.
Reguladores de flujo de aire independientes por zona.
Sistema de succión: filtro de pelos, sopapa y desborde conectados.
Conexión lista para agua fría y caliente, desagüe y toma eléctrica.

Qué NO incluye: kit blower, cromoterapia, grifería, revestimiento exterior decorativo. Estos son opcionales y se contratan aparte.

Colores disponibles sin cargo adicional: blanco, beige, negro, gris.

Modelos disponibles

Quadra: rectangular con 4 jets. Ideal para 1-2 personas.
Orbis: ovalado con 6 jets. Capacidad para 2-3 personas.
Delta: triangular esquinero con 8 jets. Para rincones o baños amplios.
Recta: rectangular alargado con 6 jets. Para espacios lineales.

Instalación sin obra — listo en horas

La instalación no requiere albañilería. El equipo de EcoFiver lleva el spa, lo posiciona en el lugar elegido, conecta el sistema hidráulico y eléctrico y lo deja funcionando el mismo día. Solo necesitás una toma de agua fría y caliente, un desagüe y una toma eléctrica cercana.

Garantía de 10 años con certificado

Todos los spas de EcoFiver tienen 10 años de garantía sobre la estructura y el acrílico sanitario. Si en ese período se presenta cualquier inconveniente estructural, el equipo de postventa lo resuelve sin cargo. La garantía se entrega por escrito junto al certificado de calidad premium al momento de la instalación.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta.

Logística y puntos de retiro

Retiro SIN CARGO en CABA zona San Telmo (subte Línea C estación San Juan / Línea A estación Piedras) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). También coordinando desde la planta en Zárate, Buenos Aires.

Para envío e instalación en tu domicilio: el flete se cotiza a $4.000 por kilómetro desde Zárate. Si compartís tu localidad, calculamos el costo exacto sin compromiso.""",

        "módulo habitacional": f"""Módulo habitacional prefabricado EcoFiver — Espacio listo en el mismo día

Este módulo habitacional prefabricado, también conocido como espacio habitacional auxiliar, módulo auxiliar o construcción en seco, se fabrica en núcleo de celulosa estructural, tecnología constructiva propia de EcoFiver desarrollada en la planta de Zárate, Buenos Aires. No es wood frame ni steel frame. Combina resistencia estructural, aislación térmica y acabado final de alta calidad en un mismo sistema.

Usos frecuentes: dormitorio de servicio, estudio en fondo de lote, oficina, sala de juegos, depósito herramientas, local pequeño.

Importante: los módulos de 6, 12 y 18 m² son módulos habitacionales auxiliares o complementarios. No son viviendas principales. Para viviendas completas, ver la línea de Viviendas Modulares de EcoFiver (desde 24 m²).

Precio publicado: {precio_str} — qué incluye

En AMBAS líneas (Base y Premium):
Piso colocado y aberturas (puerta y ventana) instaladas.
Pintura completa blanca interior.
Instalaciones internas de luz (cableado y bocas).
Instalación sobre pilotes propios de EcoFiver con escalera de acceso incluida.
Si ya tenés platea de cemento, se apoya directamente sobre ella sin cargo extra.

Línea Base: estructura base sin acabado final de exterior premium.
Línea Premium: doble aislante con malla centrifugada + acabado final de fibra (resina náutica y shelcio) que lo hace resistente a lluvia, humedad y rayos UV. Acabado final superior en aspecto y durabilidad.

Tamaños disponibles: 6 m², 12 m², 18 m².

Qué NO incluye: instalación de plomería/gas (se contratan por separado con un gasista matriculado), revestimiento exterior decorativo adicional, equipamiento interior.

Instalación en el mismo día

El equipo de EcoFiver llega con el módulo y todos los materiales necesarios. El montaje se completa en una sola jornada. Al finalizar el día, el módulo está instalado, nivelado, con instalación eléctrica y listo para usar.

Cobertura de instalación: toda la Provincia de Buenos Aires y GBA.

Garantía de 10 años

Todos los módulos habitacionales de EcoFiver tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al momento de la instalación.

Cómo pagarlo

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés abonar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta.

Retiro y logística

Retiro SIN CARGO desde los puntos de entrega en CABA (zona San Telmo, subte Línea C/A) y Zona Oeste (Paso del Rey, Ruta 7 y Tren Sarmiento). Para instalación en tu domicilio, el flete se cotiza a $4.000 por kilómetro desde la fábrica en Zárate, Buenos Aires.""",

        "vivienda modular prefabricada": f"""Vivienda modular prefabricada EcoFiver — Construcción en seco con entrega rápida

Esta vivienda modular prefabricada, también conocida como casa prefabricada, vivienda prefabricada o construcción en seco, se fabrica en núcleo de celulosa estructural, tecnología propia de EcoFiver desarrollada en la planta de Zárate, Buenos Aires. A partir de los 24 m² son viviendas completas aptas para uso familiar o comercial.

Disponibles: desde 24 m² hasta 60 m² (24, 30, 36, 42, 48, 54, 60 m²) y combinaciones según proyecto.

Usos: vivienda familiar principal, vivienda secundaria o de campo, oficina o local comercial prefabricado.

Precio publicado: {precio_str}

El precio publicado es orientativo según el metraje base. El precio final depende del metraje exacto, las terminaciones elegidas y la zona de instalación. Una vez coordinado, el precio incluye:
Fabricación completa en planta propia de EcoFiver.
Traslado hasta el lugar de instalación.
Montaje completo por el equipo de EcoFiver.
Terminaciones exteriores e interiores según el plan elegido.
Aberturas, piso y pintura interior.

Tiempo de fabricación: 45 a 60 días hábiles según metraje y acabado. No es instalación en el día (se diferencia del módulo auxiliar).

Qué NO incluye: instalación de plomería/gas (contratada con gasista matriculado), muebles, equipamiento de cocina.

Garantía 10 años — la más extensa del rubro

Todas las viviendas modulares de EcoFiver tienen 10 años de garantía sobre la estructura. La garantía se entrega por escrito junto al certificado de calidad premium al momento de la entrega.

Cómo comprarlo

Escribinos por el chat de MercadoLibre para coordinar el presupuesto final según el metraje y la zona de instalación. Contamos con opciones de financiación. El pago se procesa a través de MercadoLibre con tarjeta de crédito en cuotas, o mediante acuerdo de financiación propia.

Logística y puntos de contacto

Fabricamos en Zárate, Buenos Aires. Instalamos en toda la Provincia de Buenos Aires, GBA y el interior del país. El flete y la instalación se cotizan según la distancia desde la fábrica. Retiro coordinado desde la planta de Zárate o desde los puntos de entrega en CABA (San Telmo) y Zona Oeste (Paso del Rey).""",

        "bañera de acrílico sanitario": f"""Bañera de acrílico sanitario reforzado con PRFV — EcoFiver

Esta bañera se fabrica en acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material base que se usa en las piscinas de alta gama y los spas. La superficie es lisa, antideslizante en la base y resistente a los productos de limpieza habituales. No se descasca, no amarillea y mantiene su aspecto original con limpieza básica.

Precio publicado: {precio_str} — producto solo, sin instalación ni flete incluidos.

Modelos disponibles de EcoFiver

Lumina: 1,90 × 0,90 × 0,50 m — rectangular estándar, ideal para baños de medida estándar.
Sensa: 1,70 × 1,18 × 0,45 m — angular con doble asiento, para baños amplios.
Vento: 1,40 × 0,77 × 0,49 m — compacta rectangular para espacios reducidos.
Aqua: 1,65 × 1,40 × 0,50 m — doble asiento extra large, modelo familiar.
Curve: 1,40 × 1,40 × 0,55 m — esquinera cuadrada para baños en esquina.
Pure: 1,84 × 0,96 × 0,45 m — rectangular clásica, proporciones perfectas.
Vita: 1,80 × 0,90 × 0,50 m — rectangular estándar alargada.

Colores disponibles sin cargo adicional: blanco, beige, negro, gris.

Qué NO incluye: grifería, duchador, sifón de desagüe, obra de albañilería ni instalación (se contratan aparte con un plomero o gasista matriculado).

Instalación directa sin obra compleja

La bañera se apoya sobre el piso con la estructura propia incluida. La conexión se hace a los caños de agua fría y caliente existentes y al desagüe de piso. No requiere obra mayor de albañilería. La instalación la puede realizar cualquier plomero matriculado.

Garantía de 10 años con certificado de calidad premium

Todas las bañeras de EcoFiver tienen 10 años de garantía sobre la estructura de acrílico y el refuerzo de PRFV. El certificado de calidad premium se entrega junto con la unidad al momento de la entrega.

Cómo pagar

El pago es 100% a través de MercadoLibre, con la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta al momento de la compra.

Retiro y envío

Retiro SIN CARGO en CABA zona San Telmo (subte Líneas C y A) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). También desde la planta en Zárate, Buenos Aires, coordinando previamente. Para envío a domicilio, el flete se cotiza según la zona.""",

        "receptáculo de ducha acrílico": f"""Receptáculo de ducha de acrílico sanitario PRFV — EcoFiver

Este receptáculo de ducha se fabrica en acrílico sanitario reforzado con PRFV (Poliéster Reforzado con Fibra de Vidrio). La base tiene tratamiento antideslizante en la superficie de pisada para mayor seguridad. Resistente a los productos de limpieza habituales, a la humedad constante y al uso diario intensivo. No requiere mantenimiento especial más allá de la limpieza habitual.

Precio publicado: {precio_str} — producto solo, sin instalación ni flete incluidos.

Modelos disponibles con medidas exactas

Clásico: 1,10 × 1,10 × 0,10 m — cuadrado estándar, el más versátil.
Esquinero: 0,99 × 0,75 × 0,10 m — rectangular, ideal para baños con espacio limitado.
Pequeño: 0,90 × 0,90 × 0,09 m — compacto, para baños muy reducidos.

Colores disponibles sin cargo adicional: blanco, beige, negro, gris.

Qué NO incluye: grifería, mampara, duchador, sifón de desagüe, obra de albañilería ni instalación.

Instalación sencilla

El receptáculo se apoya directamente sobre el contrapiso o sobre el piso existente. Se fija con sellador de silicona y se conecta al desagüe existente. No requiere obra de albañilería mayor. La instalación la puede realizar cualquier plomero matriculado en pocas horas.

Garantía de 10 años con certificado de calidad

Todos los receptáculos de ducha de EcoFiver tienen 10 años de garantía sobre la estructura de acrílico y el refuerzo de PRFV. El certificado de calidad premium se entrega junto con la unidad.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta.

Logística

Retiro SIN CARGO en CABA zona San Telmo (subte Líneas C y A) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). Para envío a tu domicilio, el flete se cotiza según la localidad.""",

        "baño químico portátil": f"""Baño químico portátil EcoFiver — Solución de saneamiento para obras y eventos

Este baño químico portátil se fabrica en polipropileno de alta densidad, resistente a la intemperie, al uso intensivo y a los productos de limpieza industriales. Disponible en modelo estándar y con lavamanos integrado. Cumple con los requisitos de ART y organismos municipales para obras de construcción.

Precio publicado: {precio_str}

Qué incluye la unidad completa

Estructura de polipropileno de alta densidad.
Depósito de residuos sellado con válvula de descarga.
Ventilación natural superior para reducir olores.
Luz interior difusa por traslúcido del material.
Sistema de cierre interior y exterior con señal libre/ocupado.
En modelos con lavamanos: depósito de agua limpia (10 litros) y dispensador de jabón.

Qué NO incluye: producto líquido de tratamiento de residuos para primer uso (se consigue en ferreterías o directamente con EcoFiver), servicio periódico de limpieza (disponible aparte).

Usos frecuentes

Obras de construcción (requisito obligatorio de ART y municipios).
Eventos al aire libre: recitales, ferias, exposiciones agropecuarias, festivales.
Parques, plazas y espacios públicos.
Alquiler por jornada, semana o mes (consultá disponibilidad y tarifas).

Instalación y puesta en marcha

La unidad llega lista para usar. Se coloca sobre superficie plana, sin conexión a red de cloacas. Para el primer uso, agregar el producto de tratamiento en el depósito y la unidad está operativa.

Garantía de 10 años

Todos los baños químicos portátiles de EcoFiver tienen 10 años de garantía sobre la estructura de polipropileno. El certificado de calidad premium se entrega junto con la unidad.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés abonar con tarjeta de crédito en cuotas según las opciones disponibles.

Logística

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para entrega en domicilio, el flete se cotiza según la localidad.""",

        "garita de seguridad prefabricada": f"""Garita de seguridad prefabricada EcoFiver — Instalación en el mismo día

Esta garita de seguridad prefabricada se fabrica con estructura metálica y paredes de PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material usado en las piscinas de alta gama. Resistente a la intemperie, liviana para facilitar el transporte e instalación, y fácil de mantener. Disponible en modelos básico, con baño integrado y doble puesto.

Precio publicado: {precio_str}

Qué incluye

Estructura metálica reforzada.
Paredes y techo de PRFV resistente a la intemperie.
Ventanas fijas con vidrio de seguridad y puerta de acceso con cerradura.
Instalación eléctrica básica (cableado y bocas de luz).
Aislación térmica incluida en paredes y techo.
Los modelos con baño integrado incluyen inodoro químico o conexión a red según el caso.

Qué NO incluye: aire acondicionado, calefacción, mobiliario interior, conexión a red eléctrica del inmueble (solo el cableado interno).

Usos frecuentes

Countries y barrios privados.
Edificios de propiedad horizontal (PH).
Plantas industriales, depósitos y galpones.
Accesos a playas de estacionamiento.
Portería de hospitales, universidades o colegios.

Instalación en el mismo día

El equipo de EcoFiver llega, posiciona la garita sobre superficie plana y la deja instalada y funcionando en la misma jornada. No requiere obra de albañilería ni fundaciones complejas. Solo necesitás una superficie nivelada y acceso a la red eléctrica del lugar si la garita tiene iluminación.

Garantía de 10 años

Todas las garitas de EcoFiver tienen 10 años de garantía sobre la estructura de PRFV y metálica. El certificado de calidad premium se entrega por escrito al momento de la instalación.

Cómo pagar

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma.

Logística y retiro

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para instalación en tu domicilio, el flete se cotiza según la localidad.""",

        "reposera de fibra de vidrio": f"""Reposera de fibra de vidrio PRFV EcoFiver — Calidad de piscina, durabilidad de décadas

Esta reposera se fabrica en PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material que los cascos de piscina de alta gama. Resistente al agua de pileta, al sol, al cloro y a la intemperie durante décadas. No se dobla, no se oxida, no se raja, no requiere mantenimiento ni pintura.

Precio publicado: {precio_str} por unidad. También disponible en par de dos reposeras con precio especial (consultá la publicación correspondiente o escribinos por el chat).

Características del producto

Estructura monoblock de fibra de vidrio: sin piezas metálicas que puedan oxidarse con el cloro.
Respaldo reclinable en múltiples posiciones (3 o 5 posiciones según el modelo).
Superficie contorneada ergonómica para mayor confort.
Colores disponibles: blanco y beige.
Peso: 4,5 kg. Liviana, fácil de mover y reposicionar.
Limpieza: agua y jabón neutro.
Sin tapizado incluido (el tapizado se puede agregar aparte con almohadillas de piscina estándar).

Por qué PRFV para una reposera

Las reposeras de plástico de baja densidad se deforman con el calor del sol. Las metálicas se oxidan con el cloro y la humedad. Las de PRFV mantienen su forma y aspecto durante décadas en condiciones exteriores, sin requerir pintura ni mantenimiento estructural.

Garantía de 10 años

Todas las reposeras de EcoFiver tienen 10 años de garantía sobre la estructura de fibra de vidrio. Ante cualquier inconveniente estructural, el equipo de postventa de EcoFiver lo resuelve sin cargo.

Cómo pagar

El pago es 100% a través de MercadoLibre con tarjeta de crédito en cuotas según las opciones de tu tarjeta.

Retiro y envío

Retiro SIN CARGO en CABA zona San Telmo (subte Líneas C y A) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). Para envío a domicilio, el flete se cotiza según la zona.""",

        "cucha para perros": f"""Cucha para perros de madera tratada — EcoFiver

Esta cucha para perros se fabrica en madera tratada resistente a la intemperie. Disponible en cuatro tallas: chica, mediana, grande y extra grande, para razas de cualquier tamaño. Techado con pendiente de escurrimiento para el agua de lluvia. Ventilación cruzada interior. Piso elevado del suelo para proteger al animal de la humedad.

Precio publicado: {precio_str}

Tallas disponibles

Chica: ideal para razas pequeñas (Chihuahua, Poodle miniatura, Yorkshire, Maltés, etc.)
Mediana: para razas medianas (Beagle, Cocker Spaniel, Bulldog Francés, Boxer pequeño, etc.)
Grande: para razas grandes (Labrador, Golden Retriever, Pastor Alemán, Dóberman, etc.)
Extra grande: para razas gigantes (Gran Danés, Rottweiler, Mastín Napolitano, etc.)

Al momento de hacer la consulta, indicá la raza y el peso de tu perro para que te recomendemos la talla adecuada.

Características del producto

Madera tratada resistente a la humedad y la intemperie.
Techo con pendiente de escurrimiento para el agua de lluvia.
Piso elevado del suelo: protege al animal de la humedad y el frío del piso.
Ventilación interior adecuada para el confort del animal.
Fácil de limpiar con agua y desinfectante.

Qué NO incluye: colchoneta interior ni comedero (disponibles aparte).

Por qué EcoFiver

EcoFiver fabrica con los mismos estándares de control de calidad que aplica a sus piscinas y módulos habitacionales. Cada cucha se fabrica en la planta de Zárate, Buenos Aires, con revisión individual.

Garantía

Garantía de estructura incluida. Certificado de calidad entregado junto con el producto.

Cómo pagar

El pago es 100% a través de MercadoLibre con tarjeta de crédito en cuotas según las opciones disponibles.

Logística y retiro

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para envío a domicilio, cotizamos el flete según la localidad.""",

        "combo piscina y módulo": f"""Combo piscina de fibra de vidrio y módulo habitacional EcoFiver — En el mismo día

Este combo incluye una piscina de fibra de vidrio más un módulo habitacional auxiliar, ambos fabricados en la planta de EcoFiver en Zárate, Buenos Aires, y entregados e instalados en el mismo día por el mismo equipo.

La ventaja del combo: una sola empresa, una sola logística, un solo día de instalación. Sin coordinar dos proveedores distintos.

Precio publicado: {precio_str} — precio orientativo del combo. El precio final varía según el modelo de piscina y el tamaño del módulo. Consultanos por el chat para coordinar.

Qué incluye el combo

PISCINA DE FIBRA DE VIDRIO:
Casco monobloque de PRFV (sin juntas ni soldaduras).
Fabricación, traslado e instalación profesional completa.
Puesta en marcha del sistema de filtrado.
El sistema se entrega probado y funcionando al finalizar el día.

MÓDULO HABITACIONAL (vestuario, sala de descanso o espacio de servicio junto a la piscina):
Piso colocado y aberturas instaladas.
Pintura interior blanca completa.
Instalaciones de luz internas.
Montaje en el mismo día sobre pilotes propios o platea existente.

Qué NO incluye: excavación del pozo para la piscina (si aplica), sistema de calefacción, cubierta, iluminación submarina ni instalación de plomería/gas en el módulo.

Instalación en el mismo día

El equipo de EcoFiver llega con el combo completo y realiza la instalación en una sola jornada. La piscina queda instalada y funcionando, y el módulo está montado y listo para usar al terminar el día.

Garantía de 10 años en ambos productos

Tanto la piscina como el módulo tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al finalizar la instalación.

Cómo pagarlo

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles.

Logística

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para instalación a domicilio, el flete se cotiza según la localidad ($4.000 por km desde Zárate).""",

        "quincho o pérgola prefabricada": f"""Quincho o pérgola prefabricada EcoFiver — Espacio de reunión listo para usar

Este quincho o pérgola prefabricada se fabrica con estructura de madera o metal según la línea, con revestimiento en materiales seleccionados para resistir la intemperie. Disponible en modelos abiertos (solo techo y pilares) o cerrados (con paredes laterales opcionales). Ideal para jardines, fondos de lote, terrazas y espacios al aire libre.

Precio publicado: {precio_str}

Para qué sirve

Quincho o espacio de asado cubierto.
Pérgola para sombra en jardín o junto a la piscina.
Gazebo o espacio de reunión techado.
Extensión cubierta de la vivienda hacia el jardín o el fondo de lote.

Qué incluye

Estructura completa armada e instalada por el equipo de EcoFiver.
Techo y cobertura según el modelo (policarbonato, chapa prepintada o madera según línea).
Anclajes y refuerzos para resistencia al viento.
Montaje en el mismo día de entrega.

Qué NO incluye: iluminación, mobiliario exterior, parrilla/asador ni revestimiento decorativo adicional.

Instalación en el mismo día

El equipo de EcoFiver llega con todos los materiales y realiza el montaje completo en una sola jornada. Al finalizar, el quincho o pérgola está instalado, fijado y listo para usar.

Garantía de 10 años

Todos los quinchos y pérgolas de EcoFiver tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al momento de la instalación.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles.

Logística y retiro

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para instalación en tu domicilio, el flete se cotiza según la localidad.""",
    }

    # Fallback genérico
    cuerpo_generico = f"""Producto EcoFiver — Fabricación propia, calidad garantizada

EcoFiver fabrica, transporta e instala todos sus productos con equipo propio desde la planta de Zárate, Buenos Aires. No somos intermediarios ni revendedores: controlamos todo el proceso desde la fabricación hasta la instalación en el domicilio del cliente.

Precio publicado: {precio_str}

El precio publicado incluye la fabricación del producto y, según el modelo, la instalación profesional completa con equipo propio. Consultá los detalles específicos de este modelo en la descripción o por el chat de MercadoLibre.

Qué NO incluye: consultá por el chat de MercadoLibre para conocer exactamente qué está incluido y qué es opcional para este modelo.

Por qué elegir EcoFiver

Fabricación propia con control de calidad en cada unidad.
Instalación con equipo propio: no tercerizamos ninguna etapa del proceso.
Más de 10 años de experiencia en fabricación de fibra de vidrio, acrílico sanitario y módulos prefabricados.
Garantía de 10 años en todos los productos.

Garantía de 10 años con certificado de calidad premium

Todos los productos de EcoFiver tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al momento de la instalación o entrega.

Cómo pagar

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta.

Logística y retiro

Retiro SIN CARGO en dos puntos: CABA zona San Telmo (subte Líneas C y A, colectivos por Av. San Juan y Paseo Colón) y Zona Oeste Paso del Rey (Autopista del Oeste Ruta 7, Tren Sarmiento estación Paso del Rey). También desde la planta de Zárate coordinando previamente.

Para envío e instalación en tu domicilio: el flete se cotiza a $4.000 por kilómetro desde la fábrica en Zárate, Buenos Aires."""

    cuerpo = cuerpos.get(tipo, cuerpo_generico)
    return f"{DESC_ENCABEZADO}\n\n{cuerpo}\n\n{DESC_PIE}"


# ══════════════════════════════════════════════════════════════════════════════
#  GENERACIÓN DE CONTENIDO (100% sin IA)
# ══════════════════════════════════════════════════════════════════════════════

def _generar_contenido(item: dict, desc_actual: str, tipo: str) -> dict:
    """
    Genera título y descripción optimizados sin IA — puramente por reglas y plantillas.

    Estrategia de título:
      1. Evalúa el título actual con _score_titulo()
      2. Si score < THRESHOLD_TITULO (= muy corto o sin keywords) → genera template
      3. Si score >= THRESHOLD_TITULO → sanea el actual (limpia chars prohibidos)

    Estrategia de descripción:
      Siempre usa la plantilla de alta calidad para garantizar los 6 bloques EcoFiver.

    Retorna siempre {"titulo": str, "descripcion": str, "via": "template_v8"}.
    """
    titulo_act = item.get("title", "").strip()
    precio     = item.get("price", 0) or 0

    # ── Título ────────────────────────────────────────────────────────────────
    ts = _score_titulo(titulo_act)
    if ts < THRESHOLD_TITULO:
        titulo_nuevo = _generar_titulo_template(tipo, titulo_act)
        log.info(f"[AUDIT-ML]   Título reemplazado (score {ts}/25 < {THRESHOLD_TITULO}): «{titulo_nuevo}»")
    else:
        titulo_nuevo = _sanear_titulo(titulo_act)
        log.info(f"[AUDIT-ML]   Título conservado y saneado (score {ts}/25): «{titulo_nuevo}»")

    # ── Descripción ───────────────────────────────────────────────────────────
    desc_nueva = _descripcion_template(tipo, titulo_act, precio)

    return {"titulo": titulo_nuevo, "descripcion": desc_nueva, "via": "template_v8"}


# ══════════════════════════════════════════════════════════════════════════════
#  FETCH DE PUBLICACIONES DESDE ML
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_todos_los_items(token: str, user_id: str) -> list[dict]:
    """
    Trae todos los items activos y pausados del vendedor, con detalles completos.
    Filtra catalog listings (inaccesibles por API) y estados no editables.
    """
    from routers.mercadolibre import ML_BASE, _ml_headers

    async def _paginar_por_status(status: str) -> list[str]:
        ids: list[str] = []
        off = 0
        while True:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(
                    f"{ML_BASE}/users/{user_id}/items/search",
                    headers=_ml_headers(token),
                    params={"limit": 50, "offset": off, "status": status},
                )
            if r.status_code != 200:
                log.warning(f"[AUDIT-ML] Paginación status={status} detuvo en offset={off}: {r.status_code}")
                break
            data  = r.json()
            pagina = data.get("results", [])
            ids.extend(pagina)
            total  = data.get("paging", {}).get("total", len(ids))
            off   += 50
            if not pagina or len(ids) >= total:
                break
        log.info(f"[AUDIT-ML] status={status}: {len(ids)} items encontrados")
        return ids

    ids_active = await _paginar_por_status("active")
    ids_paused = await _paginar_por_status("paused")
    item_ids   = list(dict.fromkeys(ids_active + ids_paused))

    if not item_ids:
        return []

    log.info(f"[AUDIT-ML] {len(item_ids)} IDs activos/pausados. Obteniendo detalles en paralelo...")

    ESTADOS_EXCLUIDOS = {"closed", "under_review", "not_yet_active", "payment_required"}
    semaforo = asyncio.Semaphore(8)

    async def _fetch_lote(ids_lote: list[str]) -> list[dict]:
        async with semaforo:
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r2 = await c.get(
                        f"{ML_BASE}/items",
                        headers=_ml_headers(token),
                        params={"ids": ",".join(ids_lote)},
                    )
                if r2.status_code != 200:
                    return []
                resultado = []
                for entry in r2.json():
                    body = entry.get("body", {})
                    if not body:
                        continue
                    if body.get("status") in ESTADOS_EXCLUIDOS:
                        continue
                    if body.get("catalog_listing"):
                        continue  # ML controla estas — no editables por vendedor
                    resultado.append(body)
                return resultado
            except Exception as e:
                log.debug(f"[AUDIT-ML] Lote falló: {e}")
                return []

    lotes = [item_ids[i : i + 20] for i in range(0, len(item_ids), 20)]
    resultados_raw = await asyncio.gather(*[_fetch_lote(lote) for lote in lotes])

    items: list[dict] = []
    for grupo in resultados_raw:
        items.extend(grupo)

    saltados = len(item_ids) - len(items)
    log.info(
        f"[AUDIT-ML] {len(items)} publicaciones editables de {len(item_ids)} totales "
        f"({saltados} saltadas: catálogo ML, bajo revisión u otros estados)."
    )
    return items


async def _fetch_descripcion_actual(item_id: str, token: str) -> str:
    """Trae la descripción actual del item en ML (texto plano)."""
    from routers.mercadolibre import ML_BASE, _ml_headers
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{ML_BASE}/items/{item_id}/description",
                headers=_ml_headers(token),
            )
        if r.status_code == 200:
            return (r.json().get("plain_text") or "").strip()
    except Exception as e:
        log.debug(f"[AUDIT-ML] Sin descripción para {item_id}: {e}")
    return ""


async def _fetch_nombre_categoria(cat_id: str, token: str) -> str:
    """Trae el nombre de una categoría ML. Retorna '' si falla."""
    from routers.mercadolibre import ML_BASE, _ml_headers
    if not cat_id:
        return ""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                f"{ML_BASE}/categories/{cat_id}",
                headers=_ml_headers(token),
            )
        if r.status_code == 200:
            # Armar path completo: raíz > sub > sub
            data = r.json()
            path = data.get("path_from_root", [])
            nombre = " > ".join(n.get("name", "") for n in path) if path else data.get("name", "")
            return nombre.lower()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  ACTUALIZACIÓN EN ML
# ══════════════════════════════════════════════════════════════════════════════

async def _actualizar_en_ml(
    item_id: str, token: str, titulo: str, descripcion: str, atributos: list[dict]
) -> tuple[bool, bool, bool, bool, str]:
    """
    Actualiza título, descripción y atributos en MercadoLibre.
    Retorna (titulo_ok, titulo_bloqueado, desc_ok, attrs_ok, mensaje_error).
    """
    from routers.mercadolibre import ML_BASE, _ml_headers

    titulo_ok   = False
    titulo_bloq = False
    desc_ok     = False
    attrs_ok    = False
    errores: list[str] = []

    # — Título + condition + atributos (en un solo PUT)
    payload_put: dict = {
        "title":     titulo,
        "condition": "new",
    }
    if atributos:
        payload_put["attributes"] = atributos

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(
                f"{ML_BASE}/items/{item_id}",
                headers=_ml_headers(token),
                json=payload_put,
            )
        if r.status_code in (200, 201, 204):
            titulo_ok = True
            attrs_ok  = True
        elif r.status_code == 400 and _TITULO_NO_MODIFICABLE in r.text:
            titulo_bloq = True
            # Reintentar sin el título para que al menos se actualicen atributos
            payload_sin_titulo = {
                "condition":  "new",
                "attributes": atributos,
            } if atributos else {"condition": "new"}
            try:
                async with httpx.AsyncClient(timeout=15) as c2:
                    r2 = await c2.put(
                        f"{ML_BASE}/items/{item_id}",
                        headers=_ml_headers(token),
                        json=payload_sin_titulo,
                    )
                attrs_ok = r2.status_code in (200, 201, 204)
            except Exception:
                pass
        else:
            errores.append(f"PUT título {r.status_code}: {r.text[:120]}")
    except Exception as e:
        errores.append(f"PUT excepción: {str(e)[:100]}")

    await asyncio.sleep(0.5)

    # — Descripción (POST primero, PUT si ya existe)
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            rd = await c.post(
                f"{ML_BASE}/items/{item_id}/description",
                headers=_ml_headers(token),
                json={"plain_text": descripcion},
            )
        if rd.status_code in (200, 201):
            desc_ok = True
        elif rd.status_code == 400 and "already" in rd.text.lower():
            async with httpx.AsyncClient(timeout=15) as c2:
                rd2 = await c2.put(
                    f"{ML_BASE}/items/{item_id}/description",
                    headers=_ml_headers(token),
                    json={"plain_text": descripcion},
                )
            if rd2.status_code in (200, 201, 204):
                desc_ok = True
            else:
                errores.append(f"desc PUT {rd2.status_code}: {rd2.text[:120]}")
        else:
            errores.append(f"desc POST {rd.status_code}: {rd.text[:120]}")
    except Exception as e:
        errores.append(f"desc excepción: {str(e)[:100]}")

    return titulo_ok, titulo_bloq, desc_ok, attrs_ok, " | ".join(errores)


async def _reactivar_item(item_id: str, token: str) -> bool:
    """
    Reactiva un item cerrado incorrectamente (lo vuelve a 'active').
    Usado en v8.1 para corregir cierres erróneos de v8.
    """
    from routers.mercadolibre import ML_BASE, _ml_headers
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(
                f"{ML_BASE}/items/{item_id}",
                headers=_ml_headers(token),
                json={"status": "active"},
            )
        if r.status_code in (200, 201, 204):
            log.info(f"[AUDIT-ML]   ✓ REACTIVADO {item_id}")
            return True
        else:
            log.error(f"[AUDIT-ML]   ✗ No se pudo reactivar {item_id}: {r.status_code} {r.text[:80]}")
            return False
    except Exception as e:
        log.error(f"[AUDIT-ML]   ✗ Error al reactivar {item_id}: {e}")
        return False


async def _cerrar_item(item_id: str, token: str, motivo: str) -> bool:
    """
    Cierra (pausa/elimina) un item en ML por estar en categoría incorrecta.
    En ML la acción de 'cerrar' es DELETE /items/{id} o status=closed.
    Retorna True si fue exitoso.
    """
    from routers.mercadolibre import ML_BASE, _ml_headers
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(
                f"{ML_BASE}/items/{item_id}",
                headers=_ml_headers(token),
                json={"status": "closed"},
            )
        if r.status_code in (200, 201, 204):
            log.warning(
                f"[AUDIT-ML]   ⛔ CERRADO {item_id}: {motivo}"
            )
            return True
        else:
            log.error(f"[AUDIT-ML]   ✗ No se pudo cerrar {item_id}: {r.status_code} {r.text[:80]}")
            return False
    except Exception as e:
        log.error(f"[AUDIT-ML]   ✗ Error al cerrar {item_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  JOB PRINCIPAL DE AUDITORÍA
# ══════════════════════════════════════════════════════════════════════════════

async def auditar_y_optimizar_publicaciones():
    """
    Auditoría completa de calidad v8 — sin IA, 100% reglas y plantillas.

    FASES:
    1. Autenticación ML
    2. Fetch de todos los items editables
    3. Fetch de descripciones actuales
    4. Score de calidad + priorización (peores primero)
    5. Validación de categoría (detección de mismatches)
    6. Cierre de publicaciones en categoría incorrecta
    7. Actualización de título + descripción + atributos para el resto
    8. Reporte final con resumen y lista de títulos bloqueados
    """
    db = SessionLocal()
    try:
        ya_corrido = _get_audit_flag(db) == AUDIT_VERSION
        if ya_corrido:
            log.info(f"[AUDIT-ML] Auditoría {AUDIT_VERSION} ya completada — skip.")
            return

        log.info("═" * 60)
        log.info(f"[AUDIT-ML] Iniciando auditoría completa {AUDIT_VERSION} (sin IA)")
        log.info(f"[AUDIT-ML] Objetivo: 100% de calidad en TODAS las publicaciones")
        log.info("═" * 60)

        # ── FASE 1: Autenticación ML ──────────────────────────────────────────
        from routers.mercadolibre import _ml_valid_token, _get_user_id
        try:
            token   = await _ml_valid_token(db)
            user_id = await _get_user_id(token, db)
        except Exception as e:
            log.error(f"[AUDIT-ML] No se pudo autenticar con ML: {e}")
            return

        log.info(f"[AUDIT-ML] Autenticado ML — user_id={user_id}")

        # ── FASE 0: Recuperación de cierres incorrectos de v8 y v8.1 ────────────
        # v8: spas/jacuzzis mal clasificados como piscinas → cerrados en bañeras
        # v8.1: reposeras mal clasificadas como spa → cerradas por mismatch de categoría
        # v8.2: recuperación dinámica adicional — busca en ML todos los items cerrados
        #       y reactiva los que tienen "reposera" o "tumbona" en el título.

        lista_recuperar = list(
            dict.fromkeys(
                _ITEMS_CERRADOS_INCORRECTAMENTE_V8 + _ITEMS_CERRADOS_INCORRECTAMENTE_V8_1
            )
        )
        log.info(
            f"[AUDIT-ML] FASE 0 — Recuperando {len(lista_recuperar)} items "
            f"cerrados incorrectamente en v8/v8.1..."
        )
        recuperados_ok = 0
        for iid in lista_recuperar:
            ok_r = await _reactivar_item(iid, token)
            if ok_r:
                recuperados_ok += 1
            await asyncio.sleep(0.5)
        log.info(f"[AUDIT-ML] Recuperación lista fija: {recuperados_ok}/{len(lista_recuperar)} ok.")

        # Recuperación dinámica: buscar en ML items cerrados con "reposera" en el título
        # (captura los que el log no alcanzó a registrar en v8.1)
        log.info("[AUDIT-ML] FASE 0b — Buscando reposeras cerradas dinámicamente en ML...")
        try:
            ids_closed: list[str] = []
            off = 0
            from routers.mercadolibre import ML_BASE, _ml_headers
            while True:
                async with httpx.AsyncClient(timeout=20) as c:
                    r_closed = await c.get(
                        f"{ML_BASE}/users/{user_id}/items/search",
                        headers=_ml_headers(token),
                        params={"limit": 50, "offset": off, "status": "closed"},
                    )
                if r_closed.status_code != 200:
                    break
                data_c = r_closed.json()
                pagina_c = data_c.get("results", [])
                ids_closed.extend(pagina_c)
                total_c = data_c.get("paging", {}).get("total", len(ids_closed))
                off += 50
                if not pagina_c or len(ids_closed) >= total_c or len(ids_closed) >= 500:
                    break
                await asyncio.sleep(0.3)

            log.info(f"[AUDIT-ML] {len(ids_closed)} items cerrados encontrados en ML.")

            # Obtener detalles de los cerrados en lotes
            keywords_reactivar = ["reposera", "tumbona"]
            lotes_c = [ids_closed[i : i + 20] for i in range(0, len(ids_closed), 20)]
            reactivados_din = 0
            for lote_c in lotes_c:
                try:
                    async with httpx.AsyncClient(timeout=15) as c2:
                        r2 = await c2.get(
                            f"{ML_BASE}/items",
                            headers=_ml_headers(token),
                            params={"ids": ",".join(lote_c)},
                        )
                    if r2.status_code != 200:
                        continue
                    for entry in r2.json():
                        body = entry.get("body", {})
                        if not body:
                            continue
                        iid_c  = body.get("id", "")
                        tit_c  = body.get("title", "").lower()
                        # Solo reactivar si está cerrado Y tiene keywords de reposera/tumbona
                        if body.get("status") == "closed" and any(kw in tit_c for kw in keywords_reactivar):
                            if iid_c not in lista_recuperar:  # no duplicar los de la lista fija
                                log.info(f"[AUDIT-ML] FASE 0b — Reposera cerrada detectada: {iid_c} «{body.get('title', '')}»")
                                ok_d = await _reactivar_item(iid_c, token)
                                if ok_d:
                                    reactivados_din += 1
                                await asyncio.sleep(0.5)
                except Exception as e:
                    log.debug(f"[AUDIT-ML] FASE 0b lote falló: {e}")
                await asyncio.sleep(0.3)

            log.info(f"[AUDIT-ML] FASE 0b completada — {reactivados_din} reposeras reactivadas dinámicamente.")
        except Exception as e:
            log.error(f"[AUDIT-ML] FASE 0b error: {e}", exc_info=True)
            log.warning("[AUDIT-ML] La recuperación dinámica falló, pero el audit continúa.")

        # ── FASE 2: Fetch de items ────────────────────────────────────────────
        items = await _fetch_todos_los_items(token, user_id)
        if not items:
            log.warning("[AUDIT-ML] No hay publicaciones activas para optimizar.")
            _set_audit_flag(db, AUDIT_VERSION)
            return

        total = len(items)
        log.info(f"[AUDIT-ML] {total} publicaciones a auditar...")

        # ── FASE 3: Fetch de descripciones en paralelo ────────────────────────
        semaforo_desc = asyncio.Semaphore(5)

        async def _fetch_desc_seguro(iid: str) -> str:
            async with semaforo_desc:
                return await _fetch_descripcion_actual(iid, token)

        descripciones_raw = await asyncio.gather(
            *[_fetch_desc_seguro(it.get("id", "")) for it in items]
        )
        descripciones = {it.get("id", ""): d for it, d in zip(items, descripciones_raw)}

        # ── FASE 4: Score + priorización (peores primero) ─────────────────────
        items_con_score: list[tuple[dict, str, dict]] = []
        for item in items:
            iid  = item.get("id", "")
            desc = descripciones.get(iid, "")
            sc   = _score_item(item, desc)
            items_con_score.append((item, desc, sc))

        items_con_score.sort(key=lambda x: x[2]["score"])

        scores_antes = [x[2]["score"] for x in items_con_score]
        promedio_antes = sum(scores_antes) / len(scores_antes) if scores_antes else 0
        necesitan_fix  = sum(1 for s in scores_antes if s < THRESHOLD_OPTIMIZAR)

        log.info("─" * 60)
        log.info(f"[AUDIT-ML] CALIDAD INICIAL — promedio: {promedio_antes:.0f}/100")
        log.info(f"[AUDIT-ML]   {necesitan_fix} publicaciones bajo el umbral de {THRESHOLD_OPTIMIZAR}/100")
        log.info(f"[AUDIT-ML]   {total - necesitan_fix} publicaciones ya supera el umbral")
        log.info("─" * 60)

        # ── FASE 5: Validación de categorías ─────────────────────────────────
        log.info("[AUDIT-ML] Validando categorías de todas las publicaciones...")
        cat_ids_unicos = list({it.get("category_id", "") for it, _, _ in items_con_score if it.get("category_id")})
        cat_nombres: dict[str, str] = {}

        semaforo_cat = asyncio.Semaphore(4)
        async def _fetch_cat_seguro(cid: str) -> tuple[str, str]:
            async with semaforo_cat:
                await asyncio.sleep(0.2)
                nombre = await _fetch_nombre_categoria(cid, token)
                return cid, nombre

        cat_resultados = await asyncio.gather(*[_fetch_cat_seguro(cid) for cid in cat_ids_unicos])
        for cid, nombre in cat_resultados:
            cat_nombres[cid] = nombre

        log.info(f"[AUDIT-ML] Nombres de {len(cat_nombres)} categorías obtenidos")

        # ── FASE 6: Validación de categoría — SOLO LOGUEAR, sin cerrar ──────────
        # v8.2: se elimina el cierre automático. La detección de tipo por keywords
        # no es lo suficientemente confiable para cerrar publicaciones automáticamente.
        # Los mismatches se loguean como WARNING para revisión manual.
        items_cerrados: list[dict] = []  # siempre vacío en v8.2
        items_a_procesar: list[tuple[dict, str, dict]] = []
        mismatches_detectados: list[dict] = []

        for item, desc_actual, scoring in items_con_score:
            item_id  = item.get("id", "")
            cat_id   = item.get("category_id", "")
            tipo     = scoring["tipo"]
            titulo   = item.get("title", "—")
            cat_name = cat_nombres.get(cat_id, "")

            # Solo verificamos si detectamos el tipo y tenemos nombre de categoría
            if tipo != "producto EcoFiver" and cat_name:
                expected = _CATEGORIA_KEYWORDS.get(tipo, [])
                categoria_ok = any(kw in cat_name for kw in expected)
                if not categoria_ok:
                    log.warning(
                        f"[AUDIT-ML] ⚠ MISMATCH CATEGORÍA (solo log, no se cierra): "
                        f"{item_id} «{titulo[:45]}» — "
                        f"tipo='{tipo}' pero categoría='{cat_name}'"
                    )
                    mismatches_detectados.append({
                        "item_id": item_id,
                        "titulo": titulo,
                        "tipo": tipo,
                        "categoria_nombre": cat_name,
                    })

            # En v8.2 todos los items pasan a la fase de actualización de contenido
            items_a_procesar.append((item, desc_actual, scoring))

        if mismatches_detectados:
            log.info(
                f"[AUDIT-ML] {len(mismatches_detectados)} mismatches de categoría detectados "
                f"(requieren revisión manual — no se cerraron automáticamente)."
            )

        # ── FASE 7: Actualización de contenido ────────────────────────────────
        total_proc = len(items_a_procesar)
        ok, parcial, sin_cambios, err = 0, 0, 0, 0
        titulos_bloqueados: list[dict] = []

        for idx, (item, desc_actual, scoring) in enumerate(items_a_procesar, 1):
            item_id    = item.get("id", "")
            titulo_act = item.get("title", "—")
            score      = scoring["score"]
            tipo       = scoring["tipo"]

            log.info(
                f"[AUDIT-ML] [{idx:03d}/{total_proc}] {item_id} "
                f"score {score}/100 — «{titulo_act[:50]}»"
            )

            if scoring["issues"]:
                log.info(f"[AUDIT-ML]   Problemas: {' · '.join(scoring['issues'][:4])}")

            # Publicaciones con desc ya larga: aún así actualizamos para v8 templates
            # Solo saltamos si score muy alto Y desc ya cumple todo
            if score >= 90 and len(desc_actual) >= 1800:
                sin_cambios += 1
                log.info(f"[AUDIT-ML]   ✓ Calidad excelente ({score}/100) — skip")
                continue

            try:
                # ── Generar contenido (sin IA) ─────────────────────────────
                contenido    = _generar_contenido(item, desc_actual, tipo)
                titulo_nuevo = contenido["titulo"]
                desc_nueva   = contenido["descripcion"]
                atributos    = _atributos_para_tipo(tipo)

                log.info(
                    f"[AUDIT-ML]   Título: «{titulo_nuevo}» ({len(titulo_nuevo)} chars) | "
                    f"Desc: {len(desc_nueva)} chars | Attrs: {len(atributos)}"
                )

                # ── Actualizar en ML ──────────────────────────────────────
                t_ok, t_bloq, d_ok, a_ok, error_msg = await _actualizar_en_ml(
                    item_id, token, titulo_nuevo, desc_nueva, atributos
                )

                # ── Registrar título bloqueado para el reporte ────────────
                if t_bloq:
                    titulos_bloqueados.append({
                        "item_id":   item_id,
                        "titulo_actual": titulo_act,
                        "titulo_sugerido": titulo_nuevo,
                        "score_titulo": _score_titulo(titulo_act),
                        "permalink": item.get("permalink", ""),
                    })

                # ── Actualizar cache local en CRM ─────────────────────────
                pub = db.query(PublicacionML).filter(
                    PublicacionML.item_id == item_id
                ).first()
                if pub:
                    if t_ok:
                        pub.titulo = titulo_nuevo
                    if d_ok:
                        pub.descripcion = desc_nueva
                    db.commit()

                # ── Clasificar resultado ──────────────────────────────────
                if d_ok and (t_ok or t_bloq):
                    ok += 1
                    if t_ok:
                        log.info(f"[AUDIT-ML]   ✓ Título + descripción + atributos actualizados")
                    else:
                        log.info(
                            f"[AUDIT-ML]   ✓ Descripción actualizada "
                            f"(título bloqueado — cambiar manualmente)"
                        )
                elif d_ok:
                    ok += 1
                    log.info(f"[AUDIT-ML]   ✓ Descripción actualizada ({error_msg[:60]})")
                elif t_ok or t_bloq:
                    parcial += 1
                    log.warning(f"[AUDIT-ML]   ⚠ Descripción falló — {error_msg[:80]}")
                else:
                    err += 1
                    log.error(f"[AUDIT-ML]   ✗ Nada actualizado — {error_msg[:80]}")

            except Exception as e:
                err += 1
                log.error(f"[AUDIT-ML]   ✗ Excepción inesperada: {e}", exc_info=True)

            await asyncio.sleep(_PAUSA_ENTRE_ITEMS)

        # ── Guardar flag y reporte ─────────────────────────────────────────────
        if ok > 0 or parcial > 0 or sin_cambios == total_proc:
            _set_audit_flag(db, AUDIT_VERSION)
        else:
            log.warning(
                f"[AUDIT-ML] Sin actualizaciones — flag {AUDIT_VERSION!r} NO guardado. "
                "Reintentará en el próximo arranque."
            )

        reporte = {
            "version":                  AUDIT_VERSION,
            "total_evaluadas":          total,
            "total_cerradas":           0,   # v8.2: cierre automático eliminado
            "total_actualizadas":       ok,
            "total_parciales":          parcial,
            "total_sin_cambios":        sin_cambios,
            "total_errores":            err,
            "calidad_inicial":          round(promedio_antes, 1),
            "items_cerrados":           [],  # v8.2: siempre vacío
            "mismatches_categoria":     mismatches_detectados,
            "titulos_bloqueados":       titulos_bloqueados,
        }
        _set_reporte(db, reporte)

        # ── Reporte final en logs ─────────────────────────────────────────────
        log.info("═" * 60)
        log.info(f"[AUDIT-ML] AUDITORÍA {AUDIT_VERSION} — COMPLETADA")
        log.info(f"[AUDIT-ML]   Total publicaciones evaluadas       : {total}")
        log.info(f"[AUDIT-ML]   ✓ Actualizadas completamente        : {ok}")
        log.info(f"[AUDIT-ML]   ⚠ Actualizadas parcialmente         : {parcial}")
        log.info(f"[AUDIT-ML]   ─ Ya estaban con calidad excelente  : {sin_cambios}")
        log.info(f"[AUDIT-ML]   ✗ Con errores                      : {err}")
        log.info(f"[AUDIT-ML]   ⚠ Mismatches categoría (revisar)   : {len(mismatches_detectados)}")
        log.info(f"[AUDIT-ML]   Calidad inicial promedio             : {promedio_antes:.0f}/100")
        log.info("─" * 60)

        if mismatches_detectados:
            log.info(f"[AUDIT-ML] MISMATCHES DE CATEGORÍA (revisar manualmente — NO cerrados):")
            for mm in mismatches_detectados:
                log.info(
                    f"[AUDIT-ML]   ⚠ {mm['item_id']} «{mm['titulo'][:40]}» — "
                    f"tipo='{mm['tipo']}' cat='{mm['categoria_nombre']}'"
                )

        if titulos_bloqueados:
            log.info("─" * 60)
            log.info(f"[AUDIT-ML] TÍTULOS BLOQUEADOS POR ML ({len(titulos_bloqueados)} items):")
            log.info("[AUDIT-ML] → Cambiar manualmente en mercadolibre.com.ar > Mis publicaciones:")
            for tb in titulos_bloqueados:
                log.info(
                    f"[AUDIT-ML]   • {tb['item_id']} "
                    f"ACTUAL: «{tb['titulo_actual'][:40]}» "
                    f"→ SUGERIDO: «{tb['titulo_sugerido']}»"
                )

        log.info("═" * 60)

    except Exception as e:
        log.error(f"[AUDIT-ML] Error general en auditoría: {e}", exc_info=True)
    finally:
        db.close()


async def _delayed_audit_job():
    """
    Wrapper para asyncio.create_task: espera 5 minutos después del arranque
    para dar tiempo al app a terminar de inicializar y tener el token ML listo.
    """
    log.info("[AUDIT-ML] Auditoría ML v8.1 programada — arrancará en 5 minutos.")
    await asyncio.sleep(5 * 60)
    await auditar_y_optimizar_publicaciones()
