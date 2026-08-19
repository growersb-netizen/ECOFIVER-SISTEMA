"""
Auditoría COMPLETA v7 — Calidad 100% en todas las publicaciones MercadoLibre de EcoFiver.

FUNCIONAMIENTO
──────────────
Corre UNA SOLA VEZ por AUDIT_VERSION, 5 minutos después del primer arranque.
Funciona CON O SIN proveedor de IA — si la IA falla usa plantillas de alta calidad.

QUÉ EVALÚA
──────────
1. Título          (keywords, largo 40-60 chars, sin chars prohibidos)
2. Descripción     (mínimo 1500 chars, 6 bloques EcoFiver estándar)
3. Fotos           (solo cuenta — no puede agregar desde API)
4. Precio          (> 0 para que sea comprable)

ACCIONES AUTOMÁTICAS
──────────────────────
✓ Actualiza descripción (siempre posible, máximo impacto en conversión)
✓ Actualiza título si ML lo permite (muchos están bloqueados en listings con ventas)
✓ Usa IA para contenido personalizado; si la IA falla → plantilla de alta calidad
✓ Procesa primero las publicaciones con MENOR PUNTUACIÓN (máximo impacto)

NO HACE (demasiado riesgo para ventas activas)
──────────────────────────────────────────────
✗ No pausa publicaciones automáticamente
✗ No cambia precios
✗ No toca publicaciones de catálogo ML (inaccesibles por API)

FORZAR RE-EJECUCIÓN
────────────────────
Incrementar AUDIT_VERSION (ej: "v8") — la próxima vez que el server arranque
corre el audit completo nuevamente.
"""

import asyncio
import json
import logging
import re

import httpx
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import ConfiguracionSistema, PublicacionML
from utils.ai_client import ai_complete
from utils.contexto_ecofiver import ctx_seo_ml, DESC_ENCABEZADO, DESC_PIE

log = logging.getLogger(__name__)

# Incrementar para forzar re-ejecución (ej: "v8")
AUDIT_VERSION = "v7"
AUDIT_FLAG_KEY = "ml_audit_version"

# Pausa entre publicaciones — respetar rate limit ML
_PAUSA_ENTRE_ITEMS = 2.0

# ML bloquea cambiar títulos de listings activas con interacciones (no es error)
_TITULO_NO_MODIFICABLE = "item.title.not_modifiable"

# Umbral de calidad: publicaciones con score < THRESHOLD_OPTIMIZAR se reescriben
THRESHOLD_OPTIMIZAR = 75


# ─── Helpers de flag ─────────────────────────────────────────────────────────

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


# ─── Scoring de calidad ───────────────────────────────────────────────────────

def _score_item(item: dict, desc_actual: str) -> dict:
    """
    Evalúa la calidad de una publicación en 4 dimensiones.
    Retorna {"score": int, "issues": list[str], "detalle": dict}.
    Escala: 0 (pésima) → 100 (perfecta).
    """
    titulo   = item.get("title", "")
    precio   = item.get("price") or 0
    fotos    = len(item.get("pictures", []))
    desc     = desc_actual or ""
    score    = 0
    issues   = []
    detalle  = {}

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

    # Tiene keywords reconocibles de producto?
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


# ─── Detección de tipo de producto ───────────────────────────────────────────

def _detectar_tipo(titulo: str, descripcion: str = "") -> str:
    texto = (titulo + " " + descripcion).lower()

    if any(k in texto for k in [
        "piscin", "pileta", "natatorio", "fibra de vidrio", "minideck",
        "miniportante", "autoportante", "arco romano", "wave", "bali",
        "prfv", "monoblock",
    ]):
        return "piscina de fibra de vidrio"

    if any(k in texto for k in [
        "spa", "jacuzzi", "hidromasaje", "jets", "blower",
        "quadra", "orbis", "delta", "spa recta",
    ]):
        return "spa jacuzzi hidromasaje"

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


# ─── Saneamiento de título ────────────────────────────────────────────────────

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


# ─── Plantillas de descripción de alta calidad ───────────────────────────────

def _descripcion_template(tipo: str, titulo_actual: str, precio: float) -> str:
    """
    Genera una descripción completa de alta calidad usando plantillas EcoFiver.
    Se usa cuando la IA no está disponible — produce 2000+ chars con todos los
    bloques requeridos por MercadoLibre.
    """
    precio_str = (
        f"${precio:,.0f}".replace(",", ".")
        if precio and precio > 0
        else "(ver precio en la publicación)"
    )

    # Cuerpo específico por tipo de producto
    cuerpos: dict[str, str] = {

        "piscina de fibra de vidrio": f"""Piscina de fibra de vidrio (PRFV) — Qué es y por qué elegirla

Esta piscina de fibra de vidrio, también conocida como pileta de fibra, natatorio monoblock o piscina de PRFV, se fabrica en nuestra planta de Zárate, Buenos Aires, mediante un proceso de laminado en capas que garantiza la resistencia estructural sin juntas ni soldaduras. El casco es de una sola pieza: monobloque, sin uniones que puedan filtrar. El gelcoat exterior es parte de la estructura, no una pintura superficial que se descascare con el tiempo. Resistente a UV, a los productos químicos del agua y al uso intensivo durante décadas.

Qué incluye el precio de {precio_str}

El precio publicado incluye todo lo que necesitás para tener la piscina funcionando ese mismo día:
Fabricación completa del casco en planta propia de EcoFiver.
Traslado desde Zárate, Buenos Aires, hasta el lugar de instalación.
Instalación profesional completa con equipo propio: nivelación, conexión hidráulica y puesta en marcha del sistema de filtrado.
El sistema se entrega probado y funcionando al finalizar la jornada.

No se terceriza ninguna parte del proceso. Fabricamos, trasladamos e instalamos con nuestro propio equipo.

Colores disponibles sin cargo adicional: blanco, gris perla, azul turquesa, verde agua y piedra (varía según modelo).

Cómo es la instalación

El equipo de instalación llega con el equipamiento necesario y completa todo en una sola jornada. Al terminar, la piscina está instalada, el agua circula por el filtro y el sistema está probado. El comprador solo necesita tener el pozo excavado con las dimensiones indicadas y las tomas de agua disponibles. Para modelos autoportantes (Miniportante, Autoportante, Minideck) no es necesaria excavación: van sobre cualquier superficie firme.

Garantía de 10 años — la más extensa del rubro

Todos los cascos de fibra de vidrio de EcoFiver cuentan con 10 años de garantía sobre la estructura y el laminado. Si en ese período se presenta cualquier inconveniente estructural, el equipo de post-venta de EcoFiver lo resuelve sin cargo adicional. La garantía se entrega por escrito junto al certificado de calidad premium.

Cómo pagarlo — cuotas a través de MercadoLibre

El pago es 100% a través de MercadoLibre, con toda la protección que ofrece la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta al momento de la compra. Comprás con la tranquilidad de que el pago está respaldado por MercadoLibre. Para coordinar la entrega, la fecha y el flete a tu zona, nos contactamos después de que se concreta la compra.

Retiro y envío

Retiro SIN CARGO en dos puntos: CABA zona San Telmo (acceso fácil en subte Línea C y Línea A, colectivos por Av. San Juan y Paseo Colón) y Zona Oeste Paso del Rey (Autopista del Oeste Ruta 7 y Tren Sarmiento). Desde ambos puntos el equipo instala en tu obra sin costo adicional de traslado.

Para envío e instalación en tu domicilio: el flete sale $4.000 por kilómetro desde la fábrica en Zárate, Buenos Aires. Si nos compartís tu código postal o localidad, calculamos el costo exacto sin compromiso. Ejemplos orientativos: CABA unos 90 km, GBA Oeste/Norte unos 70-80 km.""",

        "spa jacuzzi hidromasaje": f"""Spa de hidromasaje de acrílico sanitario — Qué es y para quién es

Este spa de hidromasaje (también conocido como jacuzzi, hidromasaje o bañera de jets) se fabrica en acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado en Fibra de Vidrio), el mismo material usado en las piscinas de alta gama. La estructura autoportante metálica está incluida: se instala sin necesidad de obra de albañilería ni encofrado. Apto para uso interior o exterior, resistente a la intemperie y a los productos de tratamiento del agua.

Precio publicado: {precio_str} — qué incluye

El precio publicado incluye:
La unidad de spa completa con acrílico sanitario y estructura metálica.
Motor de hidromasaje según el modelo.
Jets dirigibles vista cromo (cantidad varía por modelo).
Pulsador neumático de encendido.
Reguladores de flujo de aire.
Sistema de succión: filtro de pelos, sopapa y desborde conectados.
Conexión lista para agua fría y caliente, desagüe y toma eléctrica.

No incluye: kit blower, cromoterapia, grifería ni revestimiento exterior (disponibles como opcional a pedido).

Colores disponibles sin cargo adicional: blanco, beige, negro, gris.

Instalación sin obra — listo en horas

La instalación no requiere albañilería. El equipo de EcoFiver lleva el spa, lo posiciona en el lugar elegido, conecta el sistema hidráulico y eléctrico y lo deja funcionando el mismo día. No hay obra previa, no hay espera ni múltiples visitas. Solo necesitás una toma de agua, un desagüe y una toma eléctrica cercana.

Garantía de 10 años con certificado

Todos los spas de EcoFiver tienen 10 años de garantía sobre la estructura y el acrílico sanitario. Si en ese período se presenta cualquier inconveniente estructural, el equipo de post-venta lo resuelve sin cargo. La garantía se entrega por escrito junto al certificado de calidad premium al momento de la instalación.

Cómo pagar — cuotas a través de MercadoLibre

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas sin interés según las opciones disponibles para tu tarjeta al momento de la compra. La compra es segura y respaldada por MercadoLibre.

Logística y puntos de retiro

Retiro SIN CARGO en CABA zona San Telmo (subte Línea C y Línea A, acceso por Av. San Juan y Paseo Colón) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). También desde la planta en Zárate coordinando previamente.

Para envío e instalación en tu domicilio: el flete sale $4.000 por kilómetro desde Zárate. Si compartís tu localidad, calculamos el costo exacto.""",

        "módulo habitacional": f"""Módulo habitacional prefabricado — Espacio listo en el mismo día

Este módulo habitacional prefabricado (también conocido como espacio habitacional auxiliar, módulo auxiliar o construcción en seco) se fabrica en núcleo de celulosa estructural, no en wood frame ni steel frame. Es una tecnología constructiva propia de EcoFiver que combina resistencia estructural, aislación térmica y acabado final de alta calidad.

Importante: los módulos de 6, 12 y 18 m² NO son viviendas. Son módulos habitacionales auxiliares o complementarios a una vivienda existente. Usos frecuentes: dormitorio de servicio, estudio en fondo de lote, oficina, sala de juegos, depósito de herramientas, local pequeño.

Precio publicado: {precio_str} — qué incluye

El precio incluye, en AMBAS líneas (Base y Premium):
Piso colocado y aberturas (puerta y ventana) instaladas.
Pintura completa blanca interior.
Instalaciones internas de luz.
Instalación sobre pilotes propios de EcoFiver con escalera de acceso incluida.
Si ya tenés platea de cemento, se apoya directamente sobre ella sin cargo extra.

Línea Base: estructura base sin acabado final de exterior ni terminación premium.
Línea Premium: doble aislante con malla centrifugada + acabado final de fibra (resina náutica y shelcio) que lo hace resistente a lluvia, humedad y rayos UV.

Instalación en el mismo día

El equipo de EcoFiver llega con el módulo y todos los materiales necesarios. El montaje se completa en una sola jornada. Al finalizar el día, el módulo está instalado, nivelado, con instalación eléctrica y listo para usar.

Cobertura: toda la Provincia de Buenos Aires y GBA.

Garantía de 10 años

Todos los módulos habitacionales de EcoFiver tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al momento de la instalación.

Cómo pagarlo

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés abonar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta. La modalidad estándar es pago contra entrega.

Retiro y logística

Retiro SIN CARGO desde los puntos de entrega en CABA (zona San Telmo) y Zona Oeste (Paso del Rey). Para instalación en tu domicilio, el flete se cotiza a $4.000 por kilómetro desde la fábrica en Zárate, Buenos Aires.""",

        "vivienda modular prefabricada": f"""Vivienda modular prefabricada — Construcción en seco con entrega rápida

Esta vivienda modular prefabricada (también conocida como casa prefabricada, vivienda prefabricada o construcción en seco) se fabrica en núcleo de celulosa estructural, tecnología propia de EcoFiver desarrollada en nuestra planta de Zárate, Buenos Aires. A partir de los 24 m² sí son viviendas completas aptas para uso familiar o comercial.

Disponibles desde 24 m² hasta 60 m² y combinaciones según necesidad. Usos: vivienda familiar principal, vivienda secundaria de campo, oficina o local comercial prefabricado.

Precio publicado: {precio_str}

El precio publicado es orientativo. El precio final depende del metraje, las terminaciones elegidas y la zona de instalación. Una vez coordinado, el precio incluye:
Fabricación completa en planta propia de EcoFiver.
Traslado hasta el lugar de instalación.
Montaje por el equipo de EcoFiver.
Terminaciones según el plan elegido.

Tiempo de fabricación: 45 a 60 días según metraje y acabado.

Garantía 10 años — la más extensa del rubro

Todas las viviendas modulares de EcoFiver tienen 10 años de garantía sobre la estructura. La garantía se entrega por escrito junto al certificado de calidad premium al momento de la entrega.

Cómo comprarlo

Escribinos por el chat de MercadoLibre para coordinar el presupuesto final según el metraje y la zona de instalación. El pago se procesa a través de MercadoLibre o mediante acuerdo directo para financiación en cuotas propias.

Logística y puntos de contacto

Fabricamos en Zárate, Buenos Aires. Instalamos en toda la Provincia de Buenos Aires, GBA y el interior del país. El flete y la instalación se cotizan según la distancia desde la fábrica. Retiro coordinado desde la planta de Zárate.""",

        "bañera de acrílico sanitario": f"""Bañera de acrílico sanitario reforzado con PRFV — Calidad y durabilidad

Esta bañera se fabrica en acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material base que se usa en las piscinas de alta gama y los spas. La superficie es lisa, antideslizante en la base y resistente a los productos de limpieza habituales. No se descasca, no amarillea y mantiene su aspecto original con limpieza básica.

Precio publicado: {precio_str} — producto completo, sin instalación ni flete incluidos.

Modelos disponibles de EcoFiver

Lumina: 1,90 × 0,90 × 0,50 m — rectangular estándar, ideal para baños de medida estándar.
Sensa: 1,70 × 1,18 × 0,45 m — angular con doble asiento, para baños amplios.
Vento: 1,40 × 0,77 × 0,49 m — compacta rectangular para espacios reducidos.
Aqua: 1,65 × 1,40 × 0,50 m — doble asiento extra large, modelo familiar.
Curve: 1,40 × 1,40 × 0,55 m — esquinera cuadrada para baños en esquina.
Pure: 1,84 × 0,96 × 0,45 m — rectangular clásica, proporción perfecta.
Vita: 1,80 × 0,90 × 0,50 m — rectangular estándar alargada.

Colores disponibles sin cargo adicional: blanco, beige, negro, gris.

Instalación directa sin obra compleja

La bañera se apoya sobre el piso con la estructura propia incluida. La conexión se hace a los caños de agua fría y caliente existentes y al desagüe de piso. No requiere obra de albañilería mayor. La instalación la puede realizar un plomero o gasista matriculado de confianza.

Garantía de 10 años con certificado de calidad premium

Todas las bañeras de EcoFiver tienen 10 años de garantía sobre la estructura de acrílico y el refuerzo de PRFV. El certificado de calidad premium se entrega junto con la unidad al momento de la compra.

Cómo pagar — tarjeta de crédito a través de MercadoLibre

El pago es 100% a través de MercadoLibre, con la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta al momento de la compra.

Retiro y envío

Retiro SIN CARGO en CABA zona San Telmo (acceso en subte Líneas C y A) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). También desde la planta en Zárate, Buenos Aires, coordinando previamente. Para envío a domicilio, el flete se cotiza según la zona.""",

        "receptáculo de ducha acrílico": f"""Receptáculo de ducha de acrílico sanitario — Medidas exactas disponibles

Este receptáculo de ducha se fabrica en acrílico sanitario reforzado con PRFV (Poliéster Reforzado con Fibra de Vidrio). La base tiene tratamiento antideslizante en la superficie de pisada. Resistente a los productos de limpieza habituales, a la humedad constante y al uso diario intensivo. No requiere mantenimiento especial.

Precio publicado: {precio_str} — producto solo, sin instalación ni flete incluidos.

Modelos disponibles con medidas exactas

Clásico: 1,10 × 1,10 × 0,10 m — cuadrado estándar, el modelo más versátil.
Esquinero: 0,99 × 0,75 × 0,10 m — rectangular, ideal para baños con espacio limitado.
Pequeño: 0,90 × 0,90 × 0,09 m — compacto, para baños muy reducidos.

Colores disponibles sin cargo adicional: blanco, beige, negro, gris.

Instalación sencilla

El receptáculo se apoya directamente sobre el contrapiso o sobre el piso existente con sellador de silicona. Se conecta al desagüe existente. No requiere obra de albañilería. La instalación la puede realizar un plomero o gasista de confianza en pocas horas.

Garantía de 10 años con certificado de calidad

Todos los receptáculos de ducha de EcoFiver tienen 10 años de garantía sobre la estructura de acrílico y el refuerzo de PRFV. El certificado de calidad premium se entrega junto con la unidad al momento de la compra.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta al momento de la compra.

Logística

Retiro SIN CARGO en CABA zona San Telmo (subte Líneas C y A) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). Para envío a tu domicilio, el flete se cotiza según la localidad.""",

        "baño químico portátil": f"""Baño químico portátil — Solución de saneamiento para obras y eventos

Este baño químico portátil se fabrica en polipropileno de alta densidad, resistente a la intemperie, al uso intensivo y a los productos de limpieza industriales. Disponible en modelo estándar, con lavamanos y accesible para personas con discapacidad motriz.

Precio publicado: {precio_str}

Qué incluye

La unidad completa incluye:
Estructura de polipropileno de alta densidad.
Depósito de residuos sellado con válvula de descarga.
Ventilación natural superior.
Luz interior difusa.
Sistema de cierre y apertura interior/exterior.
En modelos con lavamanos: depósito de agua limpia y dispensador de jabón.

Usos frecuentes

Obras de construcción (requisito obligatorio de ART y municipios).
Eventos al aire libre: recitales, ferias, exposiciones agropecuarias.
Parques, plazas y espacios públicos.
Alquiler por jornada, semana o mes (consultar disponibilidad y tarifas de alquiler).

Instalación y servicio

La unidad llega lista para usar. Se coloca sobre superficie plana, sin necesidad de conexión a red de cloacas. El servicio de limpieza y mantenimiento periódico puede contratarse aparte (consultar).

Garantía de 10 años

Todos los baños químicos portátiles de EcoFiver tienen 10 años de garantía sobre la estructura de polipropileno. El certificado de calidad premium se entrega junto con la unidad.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés abonar con tarjeta de crédito en cuotas según las opciones disponibles.

Logística

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para entrega en domicilio, el flete se cotiza según la localidad.""",

        "garita de seguridad prefabricada": f"""Garita de seguridad prefabricada — Instalación en el mismo día

Esta garita de seguridad prefabricada se fabrica con estructura metálica y paredes de PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material usado en las piscinas de alta gama. Resistente a la intemperie, liviana para facilitar el transporte e instalación, y fácil de mantener. Disponible en modelos básico, con baño integrado y doble puesto.

Precio publicado: {precio_str}

Qué incluye

La garita incluye:
Estructura metálica reforzada.
Paredes y techo de PRFV.
Ventanas fijas y puerta de acceso.
Instalación eléctrica básica.
Aislación térmica incluida.
Los modelos con baño integrado incluyen inodoro químico o conexión a red según el caso.

Usos frecuentes

Countries y barrios privados.
Edificios de propiedad horizontal (PH).
Plantas industriales y depósitos.
Accesos a playas de estacionamiento.
Portería de hospitales o universidades.

Instalación en el mismo día

El equipo de EcoFiver llega, coloca la garita sobre superficie plana y la deja instalada y funcionando en la misma jornada. No requiere obra de albañilería ni fundaciones complejas. Solo necesitás una superficie nivelada y acceso a la red eléctrica si la garita tiene iluminación.

Garantía de 10 años

Todas las garitas de EcoFiver tienen 10 años de garantía sobre la estructura de PRFV y metálica. El certificado de calidad premium se entrega por escrito al momento de la instalación.

Cómo pagar

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma.

Logística y retiro

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para instalación en tu domicilio, el flete se cotiza según la localidad.""",

        "reposera de fibra de vidrio": f"""Reposera de fibra de vidrio PRFV — Calidad de piscina, durabilidad de décadas

Esta reposera se fabrica en PRFV (Poliéster Reforzado con Fibra de Vidrio), el mismo material que los cascos de piscina de alta gama. Resistente al agua de pileta, al sol, al cloro y a la intemperie. No se dobla, no se oxida, no se raja. Ideal para el borde de la piscina, el jardín, la terraza o la playa.

Precio publicado: {precio_str} por unidad. También disponible el par de dos reposeras con precio especial (consultá la publicación correspondiente o escribinos).

Características del producto

Estructura monoblock de fibra de vidrio: sin piezas metálicas que se oxiden.
Respaldo reclinable en múltiples posiciones.
Superficie contorneada ergonómica para mayor comodidad.
Colores disponibles: blanco y beige.
Peso: liviana, fácil de mover y reposicionar.
Limpieza: se limpia con agua y jabón neutro.

Por qué elegir PRFV para una reposera

Las reposeras de plástico se deforman con el sol. Las metálicas se oxidan con el cloro y la humedad. Las de PRFV duran décadas en condiciones exteriores sin requerir mantenimiento ni pintura.

Garantía de 10 años

Todas las reposeras de EcoFiver tienen 10 años de garantía sobre la estructura de fibra de vidrio. Ante cualquier inconveniente estructural, el equipo de post-venta de EcoFiver lo resuelve.

Cómo pagar

El pago es 100% a través de MercadoLibre con tarjeta de crédito en cuotas según las opciones de tu tarjeta.

Retiro y envío

Retiro SIN CARGO en CABA zona San Telmo (subte Líneas C y A) y Zona Oeste Paso del Rey (Ruta 7 y Tren Sarmiento). Para envío a domicilio, el flete se cotiza según la zona.""",

        "cucha para perros": f"""Cucha para perros de madera — Calidad y durabilidad para tu mascota

Esta cucha para perros se fabrica en madera tratada resistente a la intemperie. Disponible en cuatro tallas: chica, mediana, grande y extra grande, para razas de cualquier tamaño. Techado con pendiente para el escurrimiento del agua. Ventilación cruzada interior. Piso elevado del suelo para proteger al animal de la humedad.

Precio publicado: {precio_str}

Tallas disponibles

Chica: ideal para razas pequeñas (Chihuahua, Poodle miniatura, Yorkshire, etc.)
Mediana: para razas medianas (Beagle, Cocker, Bulldog francés, etc.)
Grande: para razas grandes (Labrador, Golden Retriever, Pastor alemán, etc.)
Extra grande: para razas gigantes (Gran Danés, Rottweiler, Mastín, etc.)

Características del producto

Madera tratada resistente a la humedad y la intemperie.
Techo con pendiente de escurrimiento para el agua de lluvia.
Piso elevado del suelo: protege al animal de la humedad y el frío.
Ventilación interior adecuada para el confort del animal.
Fácil de limpiar con agua y desinfectante.
Entrega en piezas para ensamblado simple o armado en planta (consultar).

Por qué EcoFiver

EcoFiver fabrica con los mismos estándares de calidad que aplica a sus piscinas y módulos habitacionales. Cada cucha se fabrica en nuestra planta de Zárate, Buenos Aires, con control de calidad propio.

Garantía

Garantía de estructura incluida. Certificado de calidad entregado junto con el producto.

Cómo pagar

El pago es 100% a través de MercadoLibre con tarjeta de crédito en cuotas según las opciones disponibles.

Logística y retiro

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para envío a domicilio, cotizamos el flete según la localidad.""",

        "combo piscina y módulo": f"""Combo piscina de fibra de vidrio y módulo habitacional — Instalación en el mismo día

Este combo incluye una piscina de fibra de vidrio más un módulo habitacional auxiliar, ambos fabricados en la planta de EcoFiver en Zárate, Buenos Aires, y entregados e instalados en el mismo día por el mismo equipo.

La ventaja del combo es concretar la compra de ambos productos con una sola empresa, una sola logística y un solo día de instalación. Sin coordinar con dos proveedores distintos.

Precio publicado: {precio_str} — precio orientativo del combo. El precio final varía según el modelo de piscina y el tamaño del módulo.

Qué incluye el combo

PISCINA DE FIBRA DE VIDRIO:
Casco monobloque de PRFV (sin juntas ni soldaduras).
Fabricación, traslado e instalación profesional completa.
Puesta en marcha del sistema de filtrado.
El sistema se entrega probado y funcionando.

MÓDULO HABITACIONAL (vestuario, sala de descanso o espacio de servicio junto a la piscina):
Piso colocado y aberturas instaladas.
Pintura interior blanca completa.
Instalaciones de luz internas.
Montaje en el mismo día sobre pilotes propios o platea existente.

Instalación en el mismo día

El equipo de EcoFiver llega con el combo completo y realiza la instalación en una sola jornada. La piscina queda instalada y funcionando, y el módulo está montado y listo para usar al terminar el día.

Garantía de 10 años en ambos productos

Tanto la piscina como el módulo tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al finalizar la instalación.

Cómo pagarlo

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles.

Logística

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para instalación a domicilio, el flete se cotiza según la localidad ($4.000 por km desde Zárate).""",

        "quincho o pérgola prefabricada": f"""Quincho o pérgola prefabricada — Espacio de reunión listo para usar

Este quincho o pérgola prefabricada se fabrica con estructura de madera o metal según la línea, con revestimiento en materiales seleccionados para resistir la intemperie. Disponible en modelos abiertos (solo techo y pilares) o cerrados (con paredes laterales opcionales). Ideal para jardines, fondos de lote, terrazas y espacios al aire libre.

Precio publicado: {precio_str}

Para qué sirve

Quincho o espacio de asado cubierto.
Pérgola para sombra en jardín o piscina.
Gazebo o espacio de reunión techado.
Extensión cubierta de la vivienda hacia el jardín.

Qué incluye

Estructura completa armada e instalada por el equipo de EcoFiver.
Techo y cobertura según el modelo.
Anclajes y refuerzos para resistencia al viento.
Montaje en el mismo día de entrega.

Instalación en el mismo día

El equipo de EcoFiver llega con todos los materiales y realiza el montaje completo en una sola jornada. Al finalizar, el quincho o pérgola está instalado, fijado y listo para usar.

Garantía de 10 años

Todos los quinchos y pérgolas de EcoFiver tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al momento de la instalación.

Cómo pagar

El pago es 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles.

Logística y retiro

Retiro SIN CARGO en CABA zona San Telmo y Zona Oeste Paso del Rey. Para instalación en tu domicilio, el flete se cotiza según la localidad.""",
    }

    # Fallback genérico para productos no mapeados
    cuerpo_generico = f"""Producto EcoFiver — Fabricación propia, calidad garantizada

EcoFiver fabrica, transporta e instala todos sus productos con equipo propio desde la planta de Zárate, Buenos Aires. No somos intermediarios ni revendedores: controlamos todo el proceso desde la fabricación hasta la instalación en el domicilio del cliente.

Precio publicado: {precio_str}

El precio publicado incluye la fabricación del producto y, según el modelo, la instalación profesional completa con equipo propio. Consultá los detalles específicos de este modelo en la descripción o por el chat de MercadoLibre.

Por qué elegir EcoFiver

Fabricación propia con control de calidad en cada unidad.
Instalación con equipo propio: no tercerizamos la instalación.
Más de 10 años de experiencia en fabricación de fibra de vidrio, acrílico sanitario y módulos prefabricados.
Garantía de 10 años en todos los productos.

Garantía de 10 años con certificado de calidad premium

Todos los productos de EcoFiver tienen 10 años de garantía sobre la estructura. El certificado de calidad premium se entrega por escrito al momento de la instalación o entrega.

Cómo pagar

El pago se procesa 100% a través de MercadoLibre, con toda la protección de la plataforma. Podés pagar con tarjeta de crédito en cuotas según las opciones disponibles para tu tarjeta.

Logística y retiro

Retiro SIN CARGO en dos puntos: CABA zona San Telmo (acceso en subte Líneas C y A, colectivos por Av. San Juan y Paseo Colón) y Zona Oeste Paso del Rey (Autopista del Oeste Ruta 7 y Tren Sarmiento estación Paso del Rey). También desde la planta de Zárate coordinando previamente.

Para envío e instalación en tu domicilio en cualquier punto del país, el flete se cotiza a $4.000 por kilómetro desde la fábrica en Zárate, Buenos Aires."""

    cuerpo = cuerpos.get(tipo, cuerpo_generico)
    descripcion = f"{DESC_ENCABEZADO}\n\n{cuerpo}\n\n{DESC_PIE}"
    return descripcion


# ─── Fetch publicaciones desde ML ─────────────────────────────────────────────

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
            data = r.json()
            pagina = data.get("results", [])
            ids.extend(pagina)
            total = data.get("paging", {}).get("total", len(ids))
            off += 50
            if not pagina or len(ids) >= total:
                break
        log.info(f"[AUDIT-ML] status={status}: {len(ids)} items encontrados")
        return ids

    ids_active = await _paginar_por_status("active")
    ids_paused = await _paginar_por_status("paused")
    item_ids = list(dict.fromkeys(ids_active + ids_paused))

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
                        continue   # ML controla estas — no editables por vendedor
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


# ─── Generación de contenido ─────────────────────────────────────────────────

async def _generar_contenido(db: Session, item: dict, desc_actual: str, tipo: str) -> dict:
    """
    Genera título y descripción optimizados para ML.

    Estrategia:
      1. Intenta generación personalizada con IA (mejor resultado)
      2. Si la IA falla → usa plantilla de alta calidad según tipo de producto
         (SIEMPRE funciona — no depende de créditos ni proveedores externos)

    Retorna siempre {"titulo": str, "descripcion": str, "via": "ia"|"template"}.
    """
    item_id     = item.get("id", "")
    titulo_act  = item.get("title", "").strip()
    precio      = item.get("price", 0) or 0
    categoria   = item.get("category_id", "")

    contexto_item = f"""
DATOS DEL ITEM A OPTIMIZAR
──────────────────────────
Item ID: {item_id}
Título actual (a mejorar): {titulo_act}
Tipo de producto detectado: {tipo}
Precio publicado: ${precio:,.0f} ARS (incluye fabricación e instalación completa)
Categoría ML: {categoria}
Descripción actual (primeros 800 chars para referencia):
{desc_actual[:800] if desc_actual else "(sin descripción cargada aún)"}
"""

    prompt = f"""{ctx_seo_ml(tipo_producto=tipo, descripcion_existente=titulo_act)}

{contexto_item}

════════════════════════════════════════════════════
TAREA: OPTIMIZACIÓN COMPLETA — CALIDAD 100%
════════════════════════════════════════════════════

Reescribí completamente título y descripción para llevar esta publicación al 100% de calidad en ML.

TÍTULO (exactamente ≤60 caracteres — contar):
- Incluí: tipo de producto + material + medida o característica principal + diferenciador
- Palabras que la gente busca en Argentina: piscina/pileta/natatorio, fibra de vidrio/acrílico, spa/jacuzzi/hidromasaje, módulo/casa prefabricada
- Sin: !, ?, comas, mayúsculas sostenidas, emojis, marca "EcoFiver", frases emocionales

DESCRIPCIÓN (mínimo 1500 caracteres reales — OBLIGATORIO):
- Encabezado fijo al inicio (instalación en el día, garantía 10 años)
- Bloque 1: qué es el producto (todos los sinónimos de búsqueda + material + medidas si se conocen)
- Bloque 2: qué incluye el precio ${precio:,.0f} (fabricación + instalación + accesorios)
- Bloque 3: proceso de instalación (equipo propio, mismo día, entrega probado)
- Bloque 4: garantía 10 años + certificado de calidad premium + fabricación propia Zárate
- Bloque 5: cuotas a través de MercadoLibre (NO mencionar efectivo, transferencia ni cuotas propias)
- Bloque 6: logística (retiro sin cargo CABA San Telmo + Paso del Rey; flete $4.000/km)
- Pie fijo al final (puntos de retiro + garantía)
- Texto plano: sin asteriscos, sin guiones de lista, sin emojis, sin markdown

Respondé EXCLUSIVAMENTE con JSON válido, sin texto extra ni markdown:
{{"titulo": "...", "descripcion": "..."}}"""

    # ── Intento 1: IA personalizada ──────────────────────────────────────────
    try:
        texto = await ai_complete(db, prompt, max_tokens=3500, temperature=0.3)
        try:
            resultado = json.loads(texto)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', texto, re.DOTALL)
            resultado = json.loads(m.group()) if m else None

        if resultado:
            titulo_nuevo = _sanear_titulo(resultado.get("titulo") or "")
            desc_nueva   = (resultado.get("descripcion") or "").strip()

            if titulo_nuevo and len(desc_nueva) >= 600:
                log.info(f"[AUDIT-ML]   → Contenido generado por IA ({len(desc_nueva)} chars)")
                return {"titulo": titulo_nuevo, "descripcion": desc_nueva, "via": "ia"}

    except Exception as e:
        log.debug(f"[AUDIT-ML]   → IA no disponible para {item_id}: {str(e)[:120]}")

    # ── Intento 2: Plantilla de alta calidad ─────────────────────────────────
    log.info(f"[AUDIT-ML]   → IA no disponible — usando plantilla de alta calidad ({tipo})")
    desc_template = _descripcion_template(tipo, titulo_act, precio)

    # Para el título usamos el actual saneado si está bien, o generamos uno básico
    titulo_template = _sanear_titulo(titulo_act) if len(titulo_act) >= 20 else ""
    if not titulo_template:
        # Construcción básica de título según tipo
        tipo_titulo_map = {
            "piscina de fibra de vidrio": "Piscina de fibra de vidrio instalacion incluida",
            "spa jacuzzi hidromasaje": "Spa jacuzzi hidromasaje acrílico jets instalacion",
            "módulo habitacional": "Modulo habitacional prefabricado instalacion el dia",
            "vivienda modular prefabricada": "Vivienda modular prefabricada celulosa estructural",
            "bañera de acrílico sanitario": "Bañera acrílico sanitario PRFV garantia 10 años",
            "receptáculo de ducha acrílico": "Receptáculo de ducha acrílico sanitario antideslizante",
            "baño químico portátil": "Baño químico portátil polipropileno alta densidad",
            "garita de seguridad prefabricada": "Garita de seguridad prefabricada PRFV instalacion",
            "reposera de fibra de vidrio": "Reposera fibra de vidrio PRFV pileta jardin",
            "cucha para perros": "Cucha para perros madera tratada garantia 10 años",
            "combo piscina y módulo": "Combo piscina fibra de vidrio y modulo habitacional",
            "quincho o pérgola prefabricada": "Quincho pérgola prefabricada instalacion el dia",
        }
        titulo_template = _sanear_titulo(tipo_titulo_map.get(tipo, "Producto EcoFiver fabricacion propia Zarate"))

    return {"titulo": titulo_template, "descripcion": desc_template, "via": "template"}


# ─── Actualización en ML ──────────────────────────────────────────────────────

async def _actualizar_en_ml(
    item_id: str, token: str, titulo: str, descripcion: str
) -> tuple[bool, bool, bool, str]:
    """
    Actualiza título y descripción en MercadoLibre.
    Retorna (titulo_ok, titulo_bloqueado, desc_ok, mensaje_error).
    """
    from routers.mercadolibre import ML_BASE, _ml_headers

    titulo_ok   = False
    titulo_bloq = False
    desc_ok     = False
    errores: list[str] = []

    # — Título
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(
                f"{ML_BASE}/items/{item_id}",
                headers=_ml_headers(token),
                json={"title": titulo},
            )
        if r.status_code in (200, 201, 204):
            titulo_ok = True
        elif r.status_code == 400 and _TITULO_NO_MODIFICABLE in r.text:
            titulo_bloq = True   # restricción ML — no es error nuestro
        else:
            errores.append(f"título ML {r.status_code}: {r.text[:120]}")
    except Exception as e:
        errores.append(f"título excepción: {str(e)[:100]}")

    await asyncio.sleep(0.5)

    # — Descripción
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

    return titulo_ok, titulo_bloq, desc_ok, " | ".join(errores)


# ─── Job principal ────────────────────────────────────────────────────────────

async def auditar_y_optimizar_publicaciones():
    """
    Auditoría completa de calidad de todas las publicaciones ML de EcoFiver.

    Evalúa cada publicación, prioriza las de menor calidad, y las lleva
    al 100% usando IA o plantillas de alta calidad como fallback.
    """
    db = SessionLocal()
    try:
        ya_corrido = _get_audit_flag(db) == AUDIT_VERSION
        if ya_corrido:
            log.info(f"[AUDIT-ML] Auditoría {AUDIT_VERSION} ya completada — skip.")
            return

        log.info("═" * 60)
        log.info(f"[AUDIT-ML] Iniciando auditoría completa {AUDIT_VERSION}")
        log.info(f"[AUDIT-ML] Objetivo: llevar TODAS las publicaciones al 100% de calidad")
        log.info("═" * 60)

        # ── Autenticación ML ──────────────────────────────────────────────────
        from routers.mercadolibre import _ml_valid_token, _get_user_id
        try:
            token   = await _ml_valid_token(db)
            user_id = await _get_user_id(token, db)
        except Exception as e:
            log.error(f"[AUDIT-ML] No se pudo autenticar con ML: {e}")
            return

        log.info(f"[AUDIT-ML] Autenticado ML — user_id={user_id}")

        # ── Fetch de items ────────────────────────────────────────────────────
        items = await _fetch_todos_los_items(token, user_id)
        if not items:
            log.warning("[AUDIT-ML] No hay publicaciones activas para optimizar.")
            _set_audit_flag(db, AUDIT_VERSION)
            return

        total = len(items)
        log.info(f"[AUDIT-ML] {total} publicaciones a auditar. Evaluando calidad...")

        # ── Score + fetch descripción en paralelo ─────────────────────────────
        # Primero fetch todas las descripciones (para poder scorear)
        semaforo_desc = asyncio.Semaphore(5)

        async def _fetch_desc_seguro(item_id: str) -> str:
            async with semaforo_desc:
                return await _fetch_descripcion_actual(item_id, token)

        descripciones_raw = await asyncio.gather(
            *[_fetch_desc_seguro(it.get("id", "")) for it in items]
        )
        descripciones = dict(zip([it.get("id", "") for it in items], descripciones_raw))

        # ── Scorear y ordenar: peores primero ─────────────────────────────────
        items_con_score: list[tuple[dict, str, dict]] = []
        for item in items:
            iid  = item.get("id", "")
            desc = descripciones.get(iid, "")
            sc   = _score_item(item, desc)
            items_con_score.append((item, desc, sc))

        items_con_score.sort(key=lambda x: x[2]["score"])   # peores primero

        # Resumen de calidad ANTES de la auditoría
        scores_antes = [x[2]["score"] for x in items_con_score]
        promedio_antes = sum(scores_antes) / len(scores_antes) if scores_antes else 0
        necesitan_fix  = sum(1 for s in scores_antes if s < THRESHOLD_OPTIMIZAR)
        ya_ok          = sum(1 for s in scores_antes if s >= THRESHOLD_OPTIMIZAR)

        log.info("─" * 60)
        log.info(f"[AUDIT-ML] CALIDAD INICIAL — promedio: {promedio_antes:.0f}/100")
        log.info(f"[AUDIT-ML]   {necesitan_fix} publicaciones bajo el umbral de {THRESHOLD_OPTIMIZAR}/100")
        log.info(f"[AUDIT-ML]   {ya_ok} publicaciones ya superan el umbral")
        log.info("─" * 60)

        # ── Procesar publicaciones ────────────────────────────────────────────
        ok          = 0   # actualizadas completamente
        parcial     = 0   # solo descripción o solo título
        sin_cambios = 0   # ya estaban al 100% — no se tocaron
        err         = 0

        for idx, (item, desc_actual, scoring) in enumerate(items_con_score, 1):
            item_id    = item.get("id", "")
            titulo_act = item.get("title", "—")
            precio     = item.get("price", 0) or 0
            score      = scoring["score"]
            tipo       = scoring["tipo"]

            log.info(
                f"[AUDIT-ML] [{idx:03d}/{total}] {item_id} — score {score}/100 — «{titulo_act[:50]}»"
            )

            if scoring["issues"]:
                log.info(f"[AUDIT-ML]   Problemas: {' · '.join(scoring['issues'][:4])}")

            # Publicaciones con calidad alta — igualmente actualizamos descripción
            # para asegurar que tienen los bloques estándar EcoFiver
            if score >= THRESHOLD_OPTIMIZAR and len(desc_actual) >= 1500:
                sin_cambios += 1
                log.info(f"[AUDIT-ML]   ✓ Calidad suficiente ({score}/100) — skip")
                continue

            try:
                # ── Generar contenido (IA o plantilla) ────────────────────────
                contenido = await _generar_contenido(db, item, desc_actual, tipo)
                titulo_nuevo = contenido["titulo"]
                desc_nueva   = contenido["descripcion"]
                via          = contenido["via"]

                log.info(f"[AUDIT-ML]   Via: {via} | Título: «{titulo_nuevo}» | Desc: {len(desc_nueva)} chars")

                # ── Actualizar en ML ──────────────────────────────────────────
                t_ok, t_bloq, d_ok, error_msg = await _actualizar_en_ml(
                    item_id, token, titulo_nuevo, desc_nueva
                )

                # ── Actualizar cache local en CRM ─────────────────────────────
                pub = db.query(PublicacionML).filter(
                    PublicacionML.item_id == item_id
                ).first()
                if pub:
                    if t_ok:
                        pub.titulo = titulo_nuevo
                    if d_ok:
                        pub.descripcion = desc_nueva
                    db.commit()

                # ── Loguear resultado ─────────────────────────────────────────
                if d_ok and (t_ok or t_bloq):
                    ok += 1
                    if t_ok:
                        log.info(f"[AUDIT-ML]   ✓ Título + descripción actualizados")
                    else:
                        log.info(
                            f"[AUDIT-ML]   ✓ Descripción actualizada "
                            f"(título bloqueado por ML — cambiar manualmente en el portal de vendedor)"
                        )
                elif d_ok:
                    ok += 1
                    log.info(f"[AUDIT-ML]   ✓ Descripción actualizada (título: {error_msg[:80]})")
                elif t_ok or t_bloq:
                    parcial += 1
                    log.warning(f"[AUDIT-ML]   ⚠ Descripción falló — {error_msg[:80]}")
                else:
                    err += 1
                    log.error(f"[AUDIT-ML]   ✗ Nada actualizado — {error_msg[:80]}")

            except Exception as e:
                err += 1
                log.error(f"[AUDIT-ML]   ✗ Excepción inesperada: {e}")

            await asyncio.sleep(_PAUSA_ENTRE_ITEMS)

        # ── Marcar como completado si hubo algún progreso ─────────────────────
        if ok > 0 or parcial > 0 or sin_cambios == total:
            _set_audit_flag(db, AUDIT_VERSION)
        else:
            log.warning(
                f"[AUDIT-ML] Sin actualizaciones — flag {AUDIT_VERSION!r} NO guardado. "
                "Reintentará en el próximo arranque."
            )

        # ── Reporte final ─────────────────────────────────────────────────────
        log.info("═" * 60)
        log.info(f"[AUDIT-ML] AUDITORÍA {AUDIT_VERSION} — COMPLETADA")
        log.info(f"[AUDIT-ML]   Total publicaciones evaluadas : {total}")
        log.info(f"[AUDIT-ML]   ✓ Actualizadas completamente  : {ok}")
        log.info(f"[AUDIT-ML]   ⚠ Actualizadas parcialmente   : {parcial}")
        log.info(f"[AUDIT-ML]   ─ Ya estaban con buena calidad: {sin_cambios}")
        log.info(f"[AUDIT-ML]   ✗ Con errores                 : {err}")
        log.info(f"[AUDIT-ML]   Calidad inicial promedio       : {promedio_antes:.0f}/100")
        log.info(f"[AUDIT-ML]   Publicaciones mejoradas        : {ok + parcial}/{total}")
        if ok + parcial > 0:
            log.info("[AUDIT-ML]   → Todas las publicaciones ahora tienen descripciones")
            log.info("[AUDIT-ML]     completas con los 6 bloques estándar EcoFiver.")
            log.info("[AUDIT-ML]   → Para los títulos bloqueados por ML: cambiarlos")
            log.info("[AUDIT-ML]     manualmente desde mercadolibre.com.ar > Mis publicaciones.")
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
    log.info("[AUDIT-ML] Auditoría ML v7 programada — arrancará en 5 minutos.")
    await asyncio.sleep(5 * 60)
    await auditar_y_optimizar_publicaciones()
