"""
Auditoría y optimización automática de publicaciones activas en MercadoLibre.

FUNCIONAMIENTO
--------------
Este módulo corre UNA SOLA VEZ, 5 minutos después del primer arranque donde
esté activado. El estado se persiste en ConfiguracionSistema con la clave
`ml_audit_version`. Para forzar una nueva ejecución (por ej. cuando agreguen
publicaciones nuevas):
  → Borrar la fila con clave="ml_audit_version" en ConfiguracionSistema
  → O subir AUDIT_VERSION a "v2", "v3", etc.

No tiene endpoints ni botones — corre en segundo plano sin intervención humana.
Los logs muestran cada publicación procesada con su título viejo vs. nuevo.
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
from utils.contexto_ecofiver import ctx_seo_ml

log = logging.getLogger(__name__)

# Incrementar para forzar re-ejecución (ej: "v6")
AUDIT_VERSION = "v5"
AUDIT_FLAG_KEY = "ml_audit_version"

# Pausa entre publicaciones (segundos) — respetar rate limit ML
# Con 5000 items en el catálogo, los activos reales pueden ser 50-200.
# A 1.5s cada uno: 200 items × 1.5s = 5 minutos de procesamiento puro.
_PAUSA_ENTRE_ITEMS = 1.5

# ML bloquea cambiar títulos de publicaciones que ya tuvieron interacciones.
# Se trata como limitación conocida (no como error), y la descripción igual se actualiza.
_TITULO_NO_MODIFICABLE = "item.title.not_modifiable"


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


# ─── Detección de tipo de producto ───────────────────────────────────────────

def _detectar_tipo(titulo: str, descripcion: str = "") -> str:
    """Infiere el tipo de producto a partir del título y descripción para darle
    contexto preciso a la IA al generar el nuevo contenido."""
    texto = (titulo + " " + descripcion).lower()

    # Piscinas (primero, ya que es la línea principal)
    if any(k in texto for k in [
        "piscin", "pileta", "natatorio", "fibra de vidrio", "minideck",
        "miniportante", "autoportante", "arco romano", "wave", "bali",
        "prfv", "monoblock",
    ]):
        return "piscina de fibra de vidrio"

    # Spas / jacuzzis
    if any(k in texto for k in [
        "spa", "jacuzzi", "hidromasaje", "jets", "blower",
        "quadra", "orbis", "delta", "spa recta",
    ]):
        return "spa jacuzzi hidromasaje"

    # Módulos y viviendas
    if any(k in texto for k in [
        "módulo", "modulo", "habitacional", "vivienda modular",
        "casa prefabricada", "prefabricada", "celulosa estructural",
    ]):
        return "módulo habitacional o vivienda modular"

    # Bañeras y receptáculos
    if any(k in texto for k in [
        "bañera", "banhera", "receptáculo", "receptaculo",
        "ducha", "sanitari",
    ]):
        return "bañera o receptáculo de ducha de acrílico sanitario"

    # Baños químicos
    if any(k in texto for k in [
        "baño químico", "sanitario portátil", "quimico portátil",
        "portátil", "camping",
    ]):
        return "baño químico portátil"

    # Garitas
    if any(k in texto for k in [
        "garita", "seguridad", "vigilancia", "caseta",
    ]):
        return "garita de seguridad prefabricada"

    # Reposeras
    if any(k in texto for k in ["reposera", "tumbona", "deck chair"]):
        return "reposera de fibra de vidrio PRFV"

    # Cuchas
    if any(k in texto for k in ["cucha", "casilla para perro", "casita perro"]):
        return "cucha para perros de fibra de vidrio"

    # Combos
    if any(k in texto for k in ["combo", "kit piscina", "piscina + módulo"]):
        return "combo piscina de fibra de vidrio con módulo habitacional"

    # Pérgolas / quinchos
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


# ─── Fetch publicaciones desde ML ────────────────────────────────────────────

async def _fetch_todos_los_items(token: str, user_id: str) -> list[dict]:
    """
    Trae todos los items activos y pausados del vendedor, con detalles.

    Estrategia eficiente para catálogos grandes (5000+ ítems históricos):
    1. Pagina todos los IDs sin límite artificial.
    2. Hace el fetch de detalles en PARALELO (semáforo de 8 concurrentes)
       para convertir 250 llamadas secuenciales en ~30 segundos vs. 4 minutos.
    3. Filtra a activos/pausados al momento de recibir cada lote.
    """
    from routers.mercadolibre import ML_BASE, _ml_headers

    # ── 1. Listar IDs filtrando por status desde la API ──────────────────────
    # ML limita la paginación sin filtro a ~1050 items históricos.
    # Filtrando por status=active y status=paused obtenemos SOLO los editables
    # y sin ese límite, pudiendo paginar todos aunque sean miles.
    item_ids: list[str] = []

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
    item_ids = list(dict.fromkeys(ids_active + ids_paused))  # dedup preservando orden

    if not item_ids:
        return []

    log.info(f"[AUDIT-ML] {len(item_ids)} IDs totales en la cuenta ML. Filtrando activos/pausados...")

    # ── 2. Fetch de detalles en PARALELO (semáforo de 8 concurrentes) ────────
    # Con 5000 IDs → 250 lotes de 20 → 8 paralelos → ~30 grupos de 8
    # → ~30s de fetch en vez de ~4 minutos secuencial
    # Con el filtro de status en la query, los bodies deberían ser solo activos/pausados.
    # Igual filtramos por si acaso ML devuelve alguno en otro estado.
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
                    # Las publicaciones de catálogo ML no son editables por el vendedor
                    if body.get("catalog_listing"):
                        continue
                    resultado.append(body)
                return resultado
            except Exception as e:
                log.debug(f"[AUDIT-ML] Lote falló: {e}")
                return []

    lotes = [item_ids[i : i + 20] for i in range(0, len(item_ids), 20)]
    log.info(f"[AUDIT-ML] Fetching detalles en paralelo: {len(lotes)} lotes × 20 = hasta {len(item_ids)} items...")

    resultados_raw = await asyncio.gather(*[_fetch_lote(lote) for lote in lotes])

    items: list[dict] = []
    for grupo in resultados_raw:
        items.extend(grupo)

    # Contar cuántos active/paused quedaron fuera por ser de catálogo
    # (el _fetch_lote ya los filtró; estimamos comparando con los IDs pedidos)
    log.info(
        f"[AUDIT-ML] De los {len(item_ids)} items activos/pausados: "
        f"{len(items)} son editables (no-catálogo) y serán optimizados."
    )
    if len(item_ids) - len(items) > 0:
        log.info(
            f"[AUDIT-ML] {len(item_ids) - len(items)} items saltados "
            f"(catálogo ML, bajo revisión, u otro estado no editable)."
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


# ─── Generación de contenido con IA ──────────────────────────────────────────

async def _generar_contenido(db: Session, item: dict, desc_actual: str) -> dict | None:
    """
    Llama a la IA con contexto completo de EcoFiver + contenido actual del item
    para generar un título y descripción optimizados para ML.

    Devuelve {"titulo": str, "descripcion": str} o None si falla.
    """
    item_id     = item.get("id", "")
    titulo_act  = item.get("title", "").strip()
    precio      = item.get("price", 0) or 0
    categoria   = item.get("category_id", "")
    tipo        = _detectar_tipo(titulo_act, desc_actual)

    # Contexto del item actual para que la IA no trabaje en el vacío
    contexto_item = f"""
DATOS DEL ITEM A OPTIMIZAR
──────────────────────────
Item ID: {item_id}
Título actual (a mejorar): {titulo_act}
Tipo de producto: {tipo}
Precio publicado: ${precio:,.0f} ARS (incluye fabricación e instalación completa)
Categoría ML: {categoria}
Descripción actual (primeros 900 caracteres, para referencia):
{desc_actual[:900] if desc_actual else "(sin descripción cargada aún)"}
"""

    prompt = f"""{ctx_seo_ml(tipo_producto=tipo, descripcion_existente=titulo_act)}

{contexto_item}

════════════════════════════════════════════════════
TAREA: OPTIMIZACIÓN DE PUBLICACIÓN EXISTENTE EN ML
════════════════════════════════════════════════════

Revisá el título actual y la descripción. Generá versiones MEJORADAS que:

TÍTULO (60 caracteres máximo — contarlos):
- Incluí el tipo de producto + material + medida principal + diferenciador
- Usá términos de búsqueda reales que usa la gente en Argentina
- Evitá palabras vacías: "ideal para", "de calidad", "excelente", "premium"
- Sin: !, ?, comas, mayúsculas sostenidas, emojis, marca "EcoFiver"
- Si podés inferir el modelo exacto de los datos del item, usalo

DESCRIPCIÓN (mínimo 1500 caracteres reales — OBLIGATORIO):
- Incluí los 6 bloques del contexto (qué es, qué incluye, instalación, garantía, cuotas, logística)
- Texto plano sin markdown, sin asteriscos, sin guiones de lista, sin emojis
- El precio publicado es ${precio:,.0f} ARS — mencionarlo en el bloque de cuotas/compra
- Terminá con los bloques de encabezado y pie estándar indicados en el contexto

Respondé EXCLUSIVAMENTE con JSON válido, sin texto extra ni markdown:
{{"titulo": "...", "descripcion": "..."}}"""

    try:
        texto = await ai_complete(db, prompt, max_tokens=3200, temperature=0.3)
    except Exception as e:
        log.warning(f"[AUDIT-ML] IA falló para {item_id}: {e}")
        return None

    # Parsear JSON
    try:
        resultado = json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', texto, re.DOTALL)
        if not m:
            log.warning(f"[AUDIT-ML] IA no devolvió JSON válido para {item_id}. Respuesta: {texto[:200]}")
            return None
        try:
            resultado = json.loads(m.group())
        except Exception:
            log.warning(f"[AUDIT-ML] No se pudo parsear JSON de IA para {item_id}")
            return None

    titulo_nuevo = _sanear_titulo(resultado.get("titulo") or "")
    desc_nueva   = (resultado.get("descripcion") or "").strip()

    if not titulo_nuevo:
        log.warning(f"[AUDIT-ML] IA devolvió título vacío para {item_id}")
        return None
    if len(desc_nueva) < 600:
        log.warning(
            f"[AUDIT-ML] Descripción demasiado corta para {item_id}: "
            f"{len(desc_nueva)} chars — descartando"
        )
        return None

    return {"titulo": titulo_nuevo, "descripcion": desc_nueva}


# ─── Actualización en ML ──────────────────────────────────────────────────────

async def _actualizar_en_ml(
    item_id: str, token: str, titulo: str, descripcion: str
) -> tuple[bool, bool, bool, str]:
    """
    Actualiza título y descripción en MercadoLibre.
    Retorna (titulo_ok, desc_ok, mensaje_error).
    """
    from routers.mercadolibre import ML_BASE, _ml_headers

    titulo_ok     = False
    titulo_bloq   = False   # True cuando ML bloquea el cambio (limitación de plataforma)
    desc_ok       = False
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
            # ML no permite cambiar títulos de publicaciones activas con interacciones.
            # Esto es una restricción de la plataforma — no se cuenta como error.
            titulo_bloq = True
        else:
            errores.append(f"título ML {r.status_code}: {r.text[:120]}")
    except Exception as e:
        errores.append(f"título excepción: {str(e)[:100]}")

    await asyncio.sleep(0.5)

    # — Descripción (POST actualiza si ya existe, crea si no)
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
            # Descripción ya existe → usar PUT
            async with httpx.AsyncClient(timeout=15) as c2:
                rd2 = await c2.put(
                    f"{ML_BASE}/items/{item_id}/description",
                    headers=_ml_headers(token),
                    json={"plain_text": descripcion},
                )
            if rd2.status_code in (200, 201, 204):
                desc_ok = True
            else:
                errores.append(f"descripción PUT ML {rd2.status_code}: {rd2.text[:120]}")
        else:
            errores.append(f"descripción ML {rd.status_code}: {rd.text[:120]}")
    except Exception as e:
        errores.append(f"descripción excepción: {str(e)[:100]}")

    return titulo_ok, titulo_bloq, desc_ok, " | ".join(errores)


# ─── Job principal ────────────────────────────────────────────────────────────

async def auditar_y_optimizar_publicaciones():
    """
    Audita y optimiza TODAS las publicaciones activas en MercadoLibre con IA.

    Corre una sola vez por versión AUDIT_VERSION. El estado se guarda en
    ConfiguracionSistema[ml_audit_version]. Para forzar re-ejecución: borrar
    esa fila o incrementar AUDIT_VERSION en este módulo.
    """
    db = SessionLocal()
    try:
        ya_corrido = _get_audit_flag(db) == AUDIT_VERSION
        if ya_corrido:
            log.info(f"[AUDIT-ML] Auditoría {AUDIT_VERSION} ya completada — skip.")
            return

        log.info(f"[AUDIT-ML] ═══════════════════════════════════════════")
        log.info(f"[AUDIT-ML] Iniciando auditoría ML {AUDIT_VERSION}")
        log.info(f"[AUDIT-ML] Objetivo: optimizar títulos y descripciones")
        log.info(f"[AUDIT-ML] ═══════════════════════════════════════════")

        # Obtener token y user_id ML
        from routers.mercadolibre import _ml_valid_token, _get_user_id
        try:
            token   = await _ml_valid_token(db)
            user_id = await _get_user_id(token, db)
        except Exception as e:
            log.error(f"[AUDIT-ML] No se pudo autenticar con ML: {e}")
            return

        log.info(f"[AUDIT-ML] Autenticado ML — user_id={user_id}")

        items = await _fetch_todos_los_items(token, user_id)
        if not items:
            log.warning("[AUDIT-ML] No hay publicaciones activas para optimizar.")
            _set_audit_flag(db, AUDIT_VERSION)
            return

        total   = len(items)
        ok      = 0
        parcial = 0
        err     = 0
        err_ia_consecutivos = 0   # corte anticipado si la IA no responde

        log.info(f"[AUDIT-ML] {total} publicaciones a procesar.")

        for idx, item in enumerate(items, 1):
            item_id    = item.get("id", "")
            titulo_act = item.get("title", "—")
            precio     = item.get("price", 0)

            log.info(f"[AUDIT-ML] [{idx}/{total}] {item_id} — «{titulo_act}» (${precio:,.0f})")

            try:
                # 1. Traer descripción actual de ML
                desc_actual = await _fetch_descripcion_actual(item_id, token)

                # 2. Generar contenido optimizado
                contenido = await _generar_contenido(db, item, desc_actual)
                if not contenido:
                    log.warning(f"[AUDIT-ML]   → IA no generó contenido válido — skip")
                    err += 1
                    err_ia_consecutivos += 1
                    # Corte anticipado: si los primeros 3 ítems consecutivos fallan por IA,
                    # es probable que el proveedor esté caído o sin créditos → abortar
                    # y no marcar como completo (reintentará en el próximo arranque).
                    if err_ia_consecutivos >= 3 and ok == 0:
                        log.error(
                            "[AUDIT-ML] ✗ 3 fallos de IA consecutivos sin ningún éxito — "
                            "proveedor de IA no disponible o sin créditos. "
                            "La auditoría se reintentará en el próximo arranque. "
                            "Configurá una API key válida en el panel de Configuración."
                        )
                        return   # <-- sale sin marcar el flag; reintentará al reiniciar
                    await asyncio.sleep(_PAUSA_ENTRE_ITEMS)
                    continue

                err_ia_consecutivos = 0   # reset: la IA respondió bien
                titulo_nuevo = contenido["titulo"]
                desc_nueva   = contenido["descripcion"]

                log.info(f"[AUDIT-ML]   Título viejo : «{titulo_act}»")
                log.info(f"[AUDIT-ML]   Título nuevo : «{titulo_nuevo}»")
                log.info(f"[AUDIT-ML]   Desc nueva   : {len(desc_nueva)} chars")

                # 3. Actualizar en ML
                t_ok, t_bloq, d_ok, error_msg = await _actualizar_en_ml(
                    item_id, token, titulo_nuevo, desc_nueva
                )

                # 4. Actualizar cache local en CRM
                pub = db.query(PublicacionML).filter(
                    PublicacionML.item_id == item_id
                ).first()
                if pub:
                    if t_ok:
                        pub.titulo = titulo_nuevo
                    if d_ok:
                        pub.descripcion = desc_nueva
                    db.commit()

                # 5. Loguear resultado
                if d_ok and (t_ok or t_bloq):
                    # Desc actualizada; título OK o bloqueado por ML (no es error nuestro)
                    ok += 1
                    if t_ok:
                        log.info(f"[AUDIT-ML]   ✓ Título + descripción actualizados")
                    else:
                        log.info(
                            f"[AUDIT-ML]   ✓ Descripción actualizada "
                            f"(título bloqueado por ML — cambiarlo desde el portal de vendedor)"
                        )
                elif d_ok:
                    ok += 1
                    log.info(f"[AUDIT-ML]   ✓ Descripción actualizada (título: {error_msg})")
                elif t_ok or t_bloq:
                    parcial += 1
                    log.warning(f"[AUDIT-ML]   ⚠ Descripción falló — {error_msg}")
                else:
                    err += 1
                    log.error(f"[AUDIT-ML]   ✗ Nada actualizado — {error_msg}")

            except Exception as e:
                err += 1
                log.error(f"[AUDIT-ML]   ✗ Excepción inesperada: {e}")

            # Rate limit entre items
            await asyncio.sleep(_PAUSA_ENTRE_ITEMS)

        # Solo marcar como completado si al menos un ítem fue actualizado.
        # Si nada pudo actualizarse (ej: sin IA, sin token ML), el flag queda sin setear
        # y la auditoría reintentará automáticamente en el próximo arranque del servidor.
        if ok > 0 or parcial > 0:
            _set_audit_flag(db, AUDIT_VERSION)
        else:
            log.warning(
                f"[AUDIT-ML] Sin actualizaciones exitosas — flag {AUDIT_VERSION!r} NO guardado. "
                "La auditoría reintentará al próximo arranque."
            )

        log.info(f"[AUDIT-ML] ═══════════════════════════════════════════")
        log.info(f"[AUDIT-ML] Auditoría {AUDIT_VERSION} COMPLETADA")
        log.info(f"[AUDIT-ML]   ✓ {ok} publicaciones actualizadas completamente")
        log.info(f"[AUDIT-ML]   ⚠ {parcial} actualizadas parcialmente")
        log.info(f"[AUDIT-ML]   ✗ {err} con errores")
        log.info(f"[AUDIT-ML] ═══════════════════════════════════════════")

    except Exception as e:
        log.error(f"[AUDIT-ML] Error general en auditoría: {e}", exc_info=True)
    finally:
        db.close()


async def _delayed_audit_job():
    """
    Wrapper para APScheduler / asyncio.create_task: espera 5 minutos después
    del arranque para dar tiempo al app a terminar de inicializar.
    """
    log.info("[AUDIT-ML] Job de auditoría ML programado — arrancará en 5 minutos.")
    await asyncio.sleep(5 * 60)
    await auditar_y_optimizar_publicaciones()
