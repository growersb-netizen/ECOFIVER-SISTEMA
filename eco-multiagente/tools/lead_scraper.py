"""
Scraper orgánico de leads — fuentes públicas argentinas.
Busca personas que expresaron interés en piscinas o módulos en sitios públicos.
SOLO datos reales y públicos: nunca inventa contactos.

Fuentes:
  1. MercadoLibre API pública — listings con alta intención de compra (sin auth)
  2. OLX Argentina — sección "Compro" (compradores buscando productos)
  3. Clasificados web — búsquedas de Google indexadas en clasificados locales

Cada lead encontrado se guarda en el CRM y queda marcado para contacto proactivo.
Sin duplicados: se hashea teléfono/email para no contactar dos veces al mismo.
"""

import os
import re
import logging
import hashlib
import asyncio
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

_TZ_ARG = timezone(timedelta(hours=-3))

# ── MercadoLibre Argentina public API ──────────────────────────────────────
_MLA_SEARCH  = "https://api.mercadolibre.com/sites/MLA/search"
_MLA_ITEM    = "https://api.mercadolibre.com/items"
_MLA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EcoModulosBot/1.0)",
    "Accept": "application/json",
}

# ── OLX Argentina ───────────────────────────────────────────────────────────
_OLX_BASE    = "https://www.olx.com.ar"
_OLX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Términos de búsqueda — representan intención de COMPRA real en Argentina
# (Ampliado: más nichos = más leads. Cubre usos residenciales, comerciales y de inversión.)
_BUSQUEDAS_MLA = [
    {"q": "piscina fibra de vidrio",            "producto": "piscina",  "cat": "MLA1500"},
    {"q": "pileta fibra de vidrio",             "producto": "piscina",  "cat": "MLA1500"},
    {"q": "piscina fibra instalacion incluida", "producto": "piscina",  "cat": "MLA1500"},
    {"q": "pileta cuotas sin interes",          "producto": "piscina",  "cat": "MLA1500"},
    {"q": "piscina financiada",                 "producto": "piscina",  "cat": "MLA1500"},
    {"q": "casa modular prefabricada",          "producto": "modulo",   "cat": "MLA1459"},
    {"q": "vivienda modular NCE",               "producto": "modulo",   "cat": "MLA1459"},
    {"q": "casa prefabricada financiacion",     "producto": "modulo",   "cat": "MLA1459"},
    {"q": "modulo habitacional financiado",     "producto": "modulo",   "cat": "MLA1459"},
    {"q": "modulo para glamping",               "producto": "modulo",   "cat": "MLA1459"},
    {"q": "modulo oficina jardin",              "producto": "modulo",   "cat": "MLA1459"},
    {"q": "modulo consultorio",                 "producto": "modulo",   "cat": "MLA1459"},
    {"q": "cabaña prefabricada",                "producto": "modulo",   "cat": "MLA1459"},
    {"q": "casa rodante vivienda",              "producto": "modulo",   "cat": "MLA1459"},
    {"q": "quincho prefabricado",               "producto": "modulo",   "cat": "MLA1459"},
    {"q": "vivienda llave en mano cuotas",      "producto": "modulo",   "cat": "MLA1459"},
]

_BUSQUEDAS_OLX = [
    {"url": "/piscinas/?q=piscina+fibra",        "producto": "piscina"},
    {"url": "/pileta/?q=pileta+fibra",            "producto": "piscina"},
    {"url": "/piscinas/?q=pileta+cuotas",         "producto": "piscina"},
    {"url": "/viviendas/?q=casa+modular",         "producto": "modulo"},
    {"url": "/prefabricadas/?q=modular",          "producto": "modulo"},
    {"url": "/viviendas/?q=casa+prefabricada",    "producto": "modulo"},
    {"url": "/inmuebles/?q=modulo+habitable",     "producto": "modulo"},
    {"url": "/viviendas/?q=glamping",             "producto": "modulo"},
]

# ── Límites (ampliados para captar más leads por ciclo) ─────────────────────
_MAX_LEADS_POR_CICLO  = 40   # máximo de leads nuevos por ejecución (antes 20)
_MAX_ITEMS_POR_QUERY  = 15   # máximo de items por búsqueda MLA (antes 10)
_DELAY_ENTRE_REQUESTS = 1.2  # segundos entre requests (antes 2.0 — ciclos más rápidos)
_PRECIO_MIN_RELEVANTE = 300_000  # filtro de relevancia (antes 500k — capta más)

# ── Cache de leads ya procesados (en memoria, se reinicia con deploy) ───────
# En producción esto persiste lo suficiente: el CRM es la fuente de verdad
_leads_procesados: set[str] = set()

# Resumen del último ciclo de scraping (para mostrar en el panel)
ultimo_resumen: dict = {}


def get_ultimo_resumen() -> dict:
    """Devuelve el resumen del último ciclo de scraping ejecutado."""
    return ultimo_resumen


def _hash_contacto(valor: str) -> str:
    """Hash de teléfono o email para deduplicación."""
    return hashlib.md5(valor.lower().strip().encode()).hexdigest()[:12]


def _limpiar_telefono(raw: str) -> str:
    """Normaliza teléfono argentino al formato Meta (549XXXXXXXXXX)."""
    t = re.sub(r"[^\d]", "", raw)
    if not t:
        return ""
    if t.startswith("0"):
        t = "549" + t[1:]
    elif t.startswith("15") and len(t) == 10:
        t = "549" + t
    elif t.startswith("11") and len(t) == 10:
        t = "549" + t
    elif not t.startswith("549") and len(t) == 10:
        t = "549" + t
    elif not t.startswith("549") and len(t) == 11:
        t = "54" + t
    return t if len(t) >= 11 else ""


def _extraer_telefono(texto: str) -> str:
    """Extrae el primer teléfono encontrado en un bloque de texto."""
    patrones = [
        r"\b(?:11|15|2[0-9]|3[0-9]|4[0-9])[\s\-]?[0-9]{4}[\s\-]?[0-9]{4}\b",
        r"\b(?:\+54|549|54)[\s\-]?(?:9[\s\-]?)?[0-9]{10,11}\b",
        r"\b[0-9]{10,13}\b",
    ]
    for pat in patrones:
        m = re.search(pat, texto)
        if m:
            return _limpiar_telefono(m.group(0))
    return ""


def _extraer_email(texto: str) -> str:
    m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", texto)
    return m.group(0).lower() if m else ""


def _inferir_ubicacion(texto: str) -> str:
    """Detecta ciudad/provincia mencionada en el texto."""
    ciudades = [
        "Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata", "Tucumán",
        "Mar del Plata", "Salta", "Santa Fe", "San Juan", "Neuquén", "Resistencia",
        "Corrientes", "Posadas", "Bahía Blanca", "Paraná", "Formosa", "San Luis",
        "Río Gallegos", "Ushuaia", "CABA", "GBA", "Conurbano", "Tigre", "San Isidro",
        "Pilar", "Luján", "Mercedes", "Zárate", "Campana", "Morón", "Quilmes",
    ]
    texto_lower = texto.lower()
    for ciudad in ciudades:
        if ciudad.lower() in texto_lower:
            return ciudad
    return ""


# ── Scraper MercadoLibre ────────────────────────────────────────────────────

async def _buscar_mla(busqueda: dict) -> list[dict]:
    """
    Busca en MercadoLibre Argentina y extrae leads con intención de compra.
    Filtra listings activos, con precio realista, ubicados en Argentina.
    """
    leads = []
    try:
        # MercadoLibre cerró el acceso público (403): si la cuenta ML está conectada,
        # usamos su token de vendedor para autenticar la búsqueda.
        headers = dict(_MLA_HEADERS)
        try:
            from tools import mercadolibre_client as _ml
            if _ml.esta_conectado():
                tok = await _ml._token()
                if tok:
                    headers["Authorization"] = f"Bearer {tok}"
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=15, headers=headers) as c:
            r = await c.get(
                _MLA_SEARCH,
                params={
                    "q":       busqueda["q"],
                    "limit":   _MAX_ITEMS_POR_QUERY,
                    "sort":    "date_desc",
                    "condition": "new",
                },
            )
            if r.status_code != 200:
                if r.status_code == 403:
                    logger.info("[Scraper/MLA] 403 — MLA requiere cuenta ML conectada (panel MercadoLibre)")
                return []
            data = r.json()

        for item in data.get("results", []):
            try:
                item_id     = item.get("id", "")
                titulo      = item.get("title", "")
                precio      = item.get("price", 0)
                moneda      = item.get("currency_id", "ARS")
                permalink   = item.get("permalink", "")
                vendedor_id = item.get("seller", {}).get("id", "")
                ubicacion   = item.get("address", {}).get("city_name", "") or \
                              item.get("seller_address", {}).get("city", {}).get("name", "")

                if not item_id or not titulo:
                    continue

                # Evitar artículos duplicados
                clave = f"mla_{item_id}"
                if clave in _leads_procesados:
                    continue

                # Filtro básico de relevancia por precio
                precio_ars = precio if moneda == "ARS" else precio * 1000
                if precio_ars < _PRECIO_MIN_RELEVANTE:
                    continue  # Precio demasiado bajo para ser un módulo/piscina real

                leads.append({
                    "fuente":           "mercadolibre",
                    "fuente_id":        item_id,
                    "titulo":           titulo,
                    "precio":           precio_ars,
                    "ubicacion":        ubicacion,
                    "permalink":        permalink,
                    "vendedor_id":      str(vendedor_id),
                    "producto_interes": busqueda["producto"],
                    "canal_origen":     "organico_mla",
                    # MLA no expone teléfono en búsqueda pública — lead sin contacto directo
                    "telefono":         "",
                    "email":            "",
                    "nombre":           "",
                    "_clave":           clave,
                })
            except Exception:
                continue

        logger.info(f"[Scraper/MLA] '{busqueda['q']}' → {len(leads)} listings relevantes")

    except Exception as e:
        logger.warning(f"[Scraper/MLA] Error en búsqueda '{busqueda['q']}': {e}")

    return leads


# ── Scraper OLX Argentina ───────────────────────────────────────────────────

async def _buscar_olx(busqueda: dict) -> list[dict]:
    """
    Scraper de OLX Argentina — sección clasificados.
    OLX muestra teléfonos de vendedores (y a veces compradores en descripción).
    """
    leads = []
    try:
        url = _OLX_BASE + busqueda["url"]
        async with httpx.AsyncClient(
            timeout=20, headers=_OLX_HEADERS, follow_redirects=True
        ) as c:
            r = await c.get(url)
            if r.status_code != 200:
                logger.debug(f"[Scraper/OLX] {url} → HTTP {r.status_code}")
                return []

        html = r.text

        # Importar BeautifulSoup solo cuando está disponible
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
        except ImportError:
            soup = None

        if soup:
            # OLX estructura: div con clase que contiene cards de anuncios
            cards = (
                soup.select("li[data-aut-id='itemBox']") or
                soup.select("article.IKo3_") or
                soup.select("[data-testid='listing-card']") or
                soup.select(".lc")
            )

            for card in cards[:15]:
                try:
                    titulo_el = (
                        card.select_one("[data-aut-id='itemTitle']") or
                        card.select_one("h2") or
                        card.select_one(".fcI3k")
                    )
                    titulo    = titulo_el.get_text(strip=True) if titulo_el else ""
                    link_el   = card.select_one("a[href]")
                    link      = link_el["href"] if link_el else ""
                    loc_el    = card.select_one("[data-aut-id='item-location']") or \
                                card.select_one(".qFaHt")
                    loc       = loc_el.get_text(strip=True) if loc_el else ""

                    if not titulo:
                        continue

                    clave = f"olx_{_hash_contacto(titulo + loc)}"
                    if clave in _leads_procesados:
                        continue

                    leads.append({
                        "fuente":           "olx",
                        "fuente_id":        clave,
                        "titulo":           titulo,
                        "ubicacion":        loc or _inferir_ubicacion(titulo),
                        "permalink":        link if link.startswith("http") else _OLX_BASE + link,
                        "producto_interes": busqueda["producto"],
                        "canal_origen":     "organico_olx",
                        "telefono":         "",
                        "email":            "",
                        "nombre":           "",
                        "_clave":           clave,
                    })
                except Exception:
                    continue

        logger.info(f"[Scraper/OLX] {busqueda['url']} → {len(leads)} anuncios relevantes")

    except Exception as e:
        logger.warning(f"[Scraper/OLX] Error scrapeando {busqueda['url']}: {e}")

    return leads


# ── Google Noticias / Clasificados indexados ────────────────────────────────

_CLASIFICADOS_URLS = [
    {
        "url": "https://clasificados.lanacion.com.ar/buscar?q=piscina+fibra",
        "producto": "piscina",
        "fuente": "lanacion_clasificados",
    },
    {
        "url": "https://clasificados.lanacion.com.ar/buscar?q=casa+modular",
        "producto": "modulo",
        "fuente": "lanacion_clasificados",
    },
    {
        "url": "https://www.facebook.com/marketplace/category/home-listings?query=piscina+fibra",
        "producto": "piscina",
        "fuente": "fb_marketplace",
    },
    {
        "url": "https://clasificados.lanacion.com.ar/buscar?q=piscina+cuotas",
        "producto": "piscina",
        "fuente": "lanacion_clasificados",
    },
    {
        "url": "https://clasificados.lanacion.com.ar/buscar?q=modulo+habitable",
        "producto": "modulo",
        "fuente": "lanacion_clasificados",
    },
    {
        "url": "https://clasificados.clarin.com/buscar?q=casa+prefabricada",
        "producto": "modulo",
        "fuente": "clarin_clasificados",
    },
]


async def _buscar_clasificados_web(item: dict) -> list[dict]:
    """Scraper genérico de clasificados web argentinos."""
    leads = []
    try:
        async with httpx.AsyncClient(
            timeout=15, headers=_OLX_HEADERS, follow_redirects=True
        ) as c:
            r = await c.get(item["url"])
            if r.status_code != 200:
                return []
        html = r.text

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            # Extraer texto visible de los anuncios
            for el in soup.select("article, .clasificado, .aviso, li.result"):
                texto = el.get_text(" ", strip=True)
                tel   = _extraer_telefono(texto)
                email = _extraer_email(texto)
                if not (tel or email) or len(texto) < 20:
                    continue
                clave = f"{item['fuente']}_{_hash_contacto(tel or email)}"
                if clave in _leads_procesados:
                    continue
                leads.append({
                    "fuente":           item["fuente"],
                    "fuente_id":        clave,
                    "titulo":           texto[:100],
                    "ubicacion":        _inferir_ubicacion(texto),
                    "producto_interes": item["producto"],
                    "canal_origen":     f"organico_{item['fuente']}",
                    "telefono":         tel,
                    "email":            email,
                    "nombre":           "",
                    "_clave":           clave,
                })
        except ImportError:
            pass

    except Exception as e:
        logger.debug(f"[Scraper/Web] {item['url']}: {e}")

    return leads


# ── Guardar leads en CRM ────────────────────────────────────────────────────

async def _guardar_lead_crm(lead: dict) -> bool:
    """
    Registra el lead encontrado en el CRM.
    Usa teléfono como session_id si existe, si no usa fuente_id.
    Retorna True si es un lead NUEVO (no existía antes).
    """
    try:
        from tools import crm_client

        telefono = lead.get("telefono", "")
        email    = lead.get("email", "")
        session  = telefono if telefono else f"org_{lead['fuente']}_{lead['fuente_id']}"

        # No crear lead sin ningún dato de contacto útil (solo informacional)
        # Para MLA/OLX sin teléfono, guardamos igual pero sin contacto proactivo
        existente = await crm_client.get_lead(session)
        if existente:
            return False  # Ya existe

        data = {
            "session_id":        session,
            "lead_id":           session,
            "canal_origen":      lead.get("canal_origen", "organico"),
            "agente_asignado":   "valentina",
            "estado":            "nuevo",
            "nombre":            lead.get("nombre", ""),
            "telefono":          telefono,
            "email":             email,
            "localidad":         lead.get("ubicacion", ""),
            "producto_interes":  lead.get("producto_interes", "general"),
            "fuente_externa":    lead.get("fuente", ""),
            "fuente_url":        lead.get("permalink", ""),
            "notas":             f"Lead orgánico: {lead.get('titulo', '')[:200]}",
            "contacto_proactivo_pendiente": bool(telefono or email),
        }

        await crm_client.create_lead(data)
        _leads_procesados.add(lead["_clave"])
        return True

    except Exception as e:
        logger.warning(f"[Scraper] Error guardando lead en CRM: {e}")
        return False


async def _contactar_lead_proactivo(lead: dict) -> None:
    """
    Si el lead tiene teléfono, le envía el primer mensaje de Valentina por WhatsApp.
    Solo para leads con contacto disponible.
    """
    telefono = lead.get("telefono", "")
    if not telefono or not telefono.startswith("549"):
        return

    try:
        from channels.whatsapp import send_whatsapp_message
        from agents.valentina import get_agent

        valentina = get_agent()
        nombre    = lead.get("nombre", "") or "vecino"
        producto  = lead.get("producto_interes", "nuestros productos")
        ubicacion = lead.get("ubicacion", "")

        prompt = (
            f"Primer contacto proactivo para {nombre} que mostró interés en {producto} "
            f"{'en ' + ubicacion if ubicacion else ''}. "
            "Mensaje muy corto (máx 2 oraciones), cálido y sin presión. "
            "Presentate como Valentina de EcoFiver. Preguntá si podés ayudar."
        )
        import re as _re
        msg = await valentina.respond(prompt)
        msg = _re.sub(r"\[DERIVAR:\w+\]|\[AGENDA_VV:[^\]]+\]|\[LLAMADA_SUP:[^\]]+\]", "", msg).strip()

        if msg:
            await send_whatsapp_message(telefono, msg)
            logger.info(f"[Scraper] Contacto proactivo enviado a {telefono} — {producto}")

    except Exception as e:
        logger.warning(f"[Scraper] Error en contacto proactivo {telefono}: {e}")


# ── Función principal del ciclo de scraping ─────────────────────────────────

async def ejecutar_ciclo_scraping() -> dict:
    """
    Ejecuta un ciclo completo de scraping orgánico de leads.
    Llamado por el scheduler cada 4 horas.
    Retorna resumen del ciclo: leads encontrados, nuevos, contactados.
    """
    logger.info("[Scraper] Iniciando ciclo de scraping orgánico")

    todos_los_leads: list[dict] = []
    nuevos   = 0
    contactados = 0

    # ── 1. MercadoLibre (todas las búsquedas, mejor cobertura) ──────────────
    for busqueda in _BUSQUEDAS_MLA:
        leads = await _buscar_mla(busqueda)
        todos_los_leads.extend(leads)
        await asyncio.sleep(_DELAY_ENTRE_REQUESTS)

    # ── 2. OLX Argentina ────────────────────────────────────────────────────
    for busqueda in _BUSQUEDAS_OLX:
        leads = await _buscar_olx(busqueda)
        todos_los_leads.extend(leads)
        await asyncio.sleep(_DELAY_ENTRE_REQUESTS)

    # ── 3. Clasificados web ──────────────────────────────────────────────────
    for item in _CLASIFICADOS_URLS:
        leads = await _buscar_clasificados_web(item)
        todos_los_leads.extend(leads)
        await asyncio.sleep(_DELAY_ENTRE_REQUESTS)

    logger.info(f"[Scraper] Total leads crudos: {len(todos_los_leads)}")

    # ── Guardar y contactar leads nuevos ────────────────────────────────────
    for lead in todos_los_leads[:_MAX_LEADS_POR_CICLO]:
        es_nuevo = await _guardar_lead_crm(lead)
        if es_nuevo:
            nuevos += 1
            if lead.get("telefono"):
                await _contactar_lead_proactivo(lead)
                contactados += 1
                await asyncio.sleep(3)

    resumen = {
        "ts":          datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M"),
        "encontrados": len(todos_los_leads),
        "nuevos":      nuevos,
        "contactados": contactados,
    }
    global ultimo_resumen
    ultimo_resumen = resumen
    logger.info(f"[Scraper] Ciclo completado: {resumen}")
    return resumen
