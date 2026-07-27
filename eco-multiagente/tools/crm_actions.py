"""
Parser y ejecutor de acciones CRM desde mensajes de Máximo.

Detecta señales [CRM_ACTION:{...}] en las respuestas del agente,
las ejecuta contra el CRM y retorna el resultado.

Formato de señal:
    [CRM_ACTION:{"tipo":"venta_contado","datos":{...}}]

Múltiples acciones en un mismo mensaje son procesadas en orden.
"""

import json
import re
import logging
from tools import crm_client

logger = logging.getLogger(__name__)

# Regex que soporta un nivel de anidamiento en el JSON ({"tipo":"...","datos":{...}})
# Tolerante a variaciones que suelen escribir los LLM: CRM_ACTION, CRCM_ACTION,
# "CRM ACTION", CRM_ACCION, ACTION:, etc. (case-insensitive).
CRM_ACTION_PATTERN = re.compile(
    r'\[[A-Z_ ]*(?:ACTION|ACCION)\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})\]',
    re.IGNORECASE | re.DOTALL,
)


def detectar_acciones(reply: str) -> list[dict]:
    """Extrae todas las acciones CRM de la respuesta del agente."""
    acciones = []
    for match in CRM_ACTION_PATTERN.finditer(reply):
        try:
            acciones.append(json.loads(match.group(1)))
        except Exception as e:
            logger.warning(f"[CRMActions] JSON inválido en acción: {e} — raw: {match.group(1)[:80]}")
    return acciones


def limpiar_acciones(reply: str) -> str:
    """Elimina las marcas de acción CRM de la respuesta."""
    return CRM_ACTION_PATTERN.sub("", reply).strip()


async def ejecutar_acciones(acciones: list[dict]) -> str:
    """
    Ejecuta una lista de acciones CRM en orden.
    Retorna un bloque de texto con los resultados.
    """
    if not acciones:
        return ""

    resultados = []
    for accion in acciones:
        tipo = accion.get("tipo", "").lower()
        datos = accion.get("datos", {})
        try:
            resultado = await _ejecutar_una(tipo, datos)
        except Exception as e:
            resultado = f"❌ Error inesperado en '{tipo}': {e}"
            logger.error(f"[CRMActions] {resultado}")
        resultados.append(resultado)

    return "\n".join(resultados)


async def _ejecutar_una(tipo: str, datos: dict) -> str:
    if tipo == "venta_contado":
        return await _venta_contado(datos)
    elif tipo == "venta_financiada":
        return await _venta_financiada(datos)
    elif tipo == "pagar_cuota":
        return await _pagar_cuota(datos)
    elif tipo == "stock_piscina_add":
        return await _stock_piscina_add(datos)
    elif tipo == "stock_material_add":
        return await _stock_material(datos, "ENTRADA")
    elif tipo == "stock_material_salida":
        return await _stock_material(datos, "SALIDA")
    elif tipo == "update_lead":
        return await _update_lead(datos)
    elif tipo == "gestion_cobranza":
        return await _gestion_cobranza(datos)
    # ── Acciones operativas (ventas / leads) ──────────────────────────────
    elif tipo == "contactar_lead":
        return await _contactar_lead(datos)
    elif tipo == "contactar_leads_sin_respuesta":
        return await _contactar_leads_sin_respuesta(datos)
    elif tipo == "reasignar_lead":
        return await _reasignar_lead(datos)
    elif tipo == "cambiar_estado_lead":
        return await _cambiar_estado_lead(datos)
    elif tipo == "agendar_videollamada":
        return await _agendar_videollamada(datos)
    # ── Cobranzas ─────────────────────────────────────────────────────────
    elif tipo == "recordatorio_cobranza":
        return await _recordatorio_cobranza(datos)
    # ── Marketing / captación ─────────────────────────────────────────────
    elif tipo == "publicar_contenido":
        return await _publicar_contenido(datos)
    elif tipo == "disparar_scraping":
        return await _disparar_scraping(datos)
    elif tipo == "reactivar_leads_frios":
        return await _reactivar_leads_frios(datos)
    # ── Conocimiento persistente ────────────────────────────────────────────
    elif tipo == "recordar":
        return await _recordar(datos)
    else:
        return f"⚠️ Tipo de acción desconocido: '{tipo}'"


# ── Implementaciones individuales ─────────────────────────────────────────────

async def _venta_contado(datos: dict) -> str:
    result = await crm_client.registrar_venta_contado(datos)
    if isinstance(result, dict) and not result.get("error"):
        vid = result.get("id", "?")
        cliente = datos.get("cliente_nombre", "cliente")
        producto = datos.get("modelo_especifico", datos.get("producto", ""))
        precio = datos.get("precio_final", 0)
        return f"✅ Venta contado registrada — {cliente} / {producto} / ${precio:,.0f} — ID #{vid}"
    err = result.get("error", "sin detalle") if isinstance(result, dict) else str(result)
    return f"❌ Error al registrar venta contado: {err}"


async def _venta_financiada(datos: dict) -> str:
    result = await crm_client.registrar_venta_financiada(datos)
    if isinstance(result, dict) and not result.get("error"):
        vid = result.get("id", "?")
        cliente = datos.get("cliente_nombre", "cliente")
        cuotas = datos.get("cantidad_cuotas", "?")
        cuota_val = datos.get("valor_cuota", 0)
        return f"✅ Venta financiada registrada — {cliente} / {cuotas}c de ${cuota_val:,.0f} — ID #{vid}"
    err = result.get("error", "sin detalle") if isinstance(result, dict) else str(result)
    return f"❌ Error al registrar venta financiada: {err}"


async def _pagar_cuota(datos: dict) -> str:
    venta_id = datos.get("venta_id")
    monto = datos.get("monto")
    notas = datos.get("notas", "Pago registrado desde WhatsApp")
    concepto = datos.get("concepto", "cuota")  # "cuota" | "entrada" | "saldo_final"
    modalidad = datos.get("modalidad", "")
    if not venta_id or monto is None:
        return "❌ Falta venta_id o monto para registrar cuota"
    r = await crm_client.pagar_cuota(int(venta_id), float(monto), notas, concepto, modalidad)
    if not r.get("ok"):
        return f"❌ Error al registrar pago — Venta #{venta_id}: {r.get('error','')}"
    base = f"✅ Pago registrado — Venta #{venta_id} — ${float(monto):,.0f}"
    recibo = r.get("recibo")
    if recibo and recibo.get("download_url"):
        base += f" — recibo: {recibo['download_url']}"
        if recibo.get("es_cierre"):
            base += " (saldo cancelado)"
    return base


async def _stock_piscina_add(datos: dict) -> str:
    result = await crm_client.agregar_stock_piscina(datos)
    if isinstance(result, dict) and not result.get("error"):
        modelo = datos.get("modelo", "?")
        color = datos.get("color", "?")
        cant = datos.get("cantidad", "?")
        return f"✅ Stock piscina actualizado — {modelo} {color}: +{cant} unidad(es)"
    err = result.get("error", "sin detalle") if isinstance(result, dict) else str(result)
    return f"❌ Error al actualizar stock piscina: {err}"


async def _stock_material(datos: dict, tipo: str) -> str:
    mat_id = datos.get("material_id")
    cantidad = datos.get("cantidad")
    nombre = datos.get("nombre", f"material #{mat_id}")
    motivo = datos.get("motivo", f"{'Ingreso' if tipo == 'ENTRADA' else 'Salida'} desde WhatsApp")
    if not mat_id or cantidad is None:
        return f"❌ Falta material_id o cantidad para registrar {tipo.lower()}"
    ok = await crm_client.movimiento_material(int(mat_id), tipo, float(cantidad), motivo)
    flecha = "+" if tipo == "ENTRADA" else "-"
    accion = "Ingreso" if tipo == "ENTRADA" else "Salida"
    if ok:
        return f"✅ {accion} registrado — {nombre} (ID {mat_id}): {flecha}{cantidad}"
    return f"❌ Error al registrar {accion.lower()} de {nombre}"


async def _update_lead(datos: dict) -> str:
    lead_id = datos.get("lead_id")
    campos = datos.get("campos", {})
    if not lead_id:
        return "❌ Falta lead_id para actualizar lead"
    ok = await crm_client.update_lead_by_id(int(lead_id), campos)
    if ok:
        return f"✅ Lead #{lead_id} actualizado — campos: {', '.join(campos.keys())}"
    return f"❌ Error al actualizar lead #{lead_id}"


async def _gestion_cobranza(datos: dict) -> str:
    venta_id = datos.get("venta_id")
    canal = datos.get("canal", "whatsapp")
    resultado = datos.get("resultado", "")
    notas = datos.get("notas", "")
    if not venta_id:
        return "❌ Falta venta_id para registrar gestión de cobranza"
    ok = await crm_client.registrar_gestion_cobranza(int(venta_id), canal, resultado, notas)
    if ok:
        return f"✅ Gestión de cobranza registrada — Venta #{venta_id} ({resultado})"
    return f"❌ Error al registrar gestión de cobranza — Venta #{venta_id}"


# ── Acciones operativas: contacto real con leads/clientes ──────────────────

def _normalizar_tel(raw: str) -> str:
    import re as _re
    t = _re.sub(r"[^\d]", "", raw or "")
    if not t:
        return ""
    if not t.startswith("549") and len(t) == 10:
        t = "549" + t
    elif t.startswith("0"):
        t = "549" + t[1:]
    elif not t.startswith("54"):
        t = "549" + t
    return t


async def _contactar_lead(datos: dict) -> str:
    """Envía un WhatsApp real a un lead puntual."""
    tel = _normalizar_tel(datos.get("telefono", ""))
    mensaje = (datos.get("mensaje") or "").strip()
    nombre = datos.get("nombre", "")
    if not tel or not mensaje:
        return "❌ Falta teléfono o mensaje para contactar al lead"
    try:
        from channels.whatsapp import send_whatsapp_message
        ok = await send_whatsapp_message(tel, mensaje)
        if ok:
            # Registrar el contacto en el CRM si hay session/lead
            if datos.get("session_id"):
                try:
                    await crm_client.save_message(
                        lead_id=datos["session_id"], user_msg="",
                        agent_reply=mensaje, agent_name=datos.get("agente", "sistema"),
                    )
                except Exception:
                    pass
            return f"✅ WhatsApp enviado a {nombre or tel}"
        return f"❌ No se pudo enviar el WhatsApp a {tel}"
    except Exception as e:
        return f"❌ Error contactando lead: {e}"


async def _contactar_leads_sin_respuesta(datos: dict) -> str:
    """
    Contacta REALMENTE a los leads sin respuesta (acción masiva).
    Genera un primer mensaje con Valentina y lo envía por WhatsApp.
    datos opcional: horas (default 2), limite (default 10).
    """
    horas  = int(datos.get("horas", 2))
    limite = int(datos.get("limite", 10))
    try:
        leads = await crm_client.get_leads_sin_respuesta(horas)
    except Exception as e:
        return f"❌ No pude leer los leads sin respuesta: {e}"
    if not leads:
        return "✅ No hay leads sin respuesta para contactar en este momento."

    enviados, sin_tel = 0, 0
    try:
        from channels.whatsapp import send_whatsapp_message
        from agents.valentina import get_agent
        import re as _re
        valentina = get_agent()
        for l in leads[:limite]:
            tel = _normalizar_tel(l.get("telefono", ""))
            if not tel:
                sin_tel += 1
                continue
            nombre = l.get("nombre", "") or "vecino"
            prod = l.get("producto_interes", "nuestros productos")
            prompt = (
                f"Reescribí en 1-2 oraciones, cálido y sin presión, un primer mensaje para "
                f"{nombre} que consultó por {prod} y quedó sin respuesta. Presentate como Valentina "
                f"de EcoFiver. Preguntá si seguís pudiendo ayudar."
            )
            msg = await valentina.respond(prompt)
            msg = _re.sub(r"\[[^\]]+\]", "", msg).strip()
            if msg and await send_whatsapp_message(tel, msg):
                enviados += 1
    except Exception as e:
        return f"❌ Error en el contacto masivo: {e}"

    resumen = f"✅ Contacté {enviados} lead(s) sin respuesta por WhatsApp"
    if sin_tel:
        resumen += f" ({sin_tel} no tenían teléfono cargado)"
    return resumen


async def _reasignar_lead(datos: dict) -> str:
    lead_id = datos.get("lead_id")
    agente = datos.get("agente", "")
    if not lead_id or not agente:
        return "❌ Falta lead_id o agente para reasignar"
    ok = await crm_client.update_lead_by_id(int(lead_id), {"agente_asignado": agente})
    return f"✅ Lead #{lead_id} reasignado a {agente}" if ok else f"❌ No se pudo reasignar el lead #{lead_id}"


async def _cambiar_estado_lead(datos: dict) -> str:
    lead_id = datos.get("lead_id")
    estado = datos.get("estado", "")
    if not lead_id or not estado:
        return "❌ Falta lead_id o estado"
    ok = await crm_client.update_lead_by_id(int(lead_id), {"estado": estado})
    return f"✅ Lead #{lead_id} → estado '{estado}'" if ok else f"❌ No se pudo cambiar el estado del lead #{lead_id}"


async def _agendar_videollamada(datos: dict) -> str:
    lead_id = datos.get("lead_id")
    fecha   = datos.get("fecha_hora", "")
    tipo    = datos.get("tipo", "videollamada")
    agente  = datos.get("agente", "")
    if not lead_id or not fecha:
        return "❌ Falta lead_id o fecha_hora para agendar"
    res = await crm_client.agendar_videollamada(str(lead_id), fecha, tipo, agente)
    if isinstance(res, dict) and not res.get("error") and res.get("ok", True):
        return f"✅ {tipo.capitalize()} agendada — Lead {lead_id} para {fecha}"
    return f"❌ No se pudo agendar: {res.get('error','error') if isinstance(res, dict) else res}"


async def _recordatorio_cobranza(datos: dict) -> str:
    """Envía un recordatorio de pago real por WhatsApp y registra la gestión."""
    tel = _normalizar_tel(datos.get("telefono", ""))
    mensaje = (datos.get("mensaje") or "").strip()
    venta_id = datos.get("venta_id")
    if not tel or not mensaje:
        return "❌ Falta teléfono o mensaje para el recordatorio de cobranza"
    try:
        from channels.whatsapp import send_whatsapp_message
        ok = await send_whatsapp_message(tel, mensaje)
        if ok and venta_id:
            await crm_client.registrar_gestion_cobranza(
                int(venta_id), "whatsapp", "recordatorio_enviado", mensaje[:200])
        return "✅ Recordatorio de cobranza enviado" if ok else "❌ No se pudo enviar el recordatorio"
    except Exception as e:
        return f"❌ Error en recordatorio de cobranza: {e}"


# ── Marketing / captación ──────────────────────────────────────────────────

async def _publicar_contenido(datos: dict) -> str:
    """Genera (si hace falta) y publica contenido en FB/IG."""
    try:
        from tools import content_poster
        texto = (datos.get("texto") or "").strip()
        if not texto:
            cont = await content_poster.generar_contenido()
            if not cont:
                return "❌ No se pudo generar el contenido"
            texto = cont["texto_fb"]
        fb = await content_poster.publicar_facebook(texto)
        return f"✅ Contenido publicado en Facebook" if fb else "❌ No se pudo publicar (¿token Meta?)"
    except Exception as e:
        return f"❌ Error publicando contenido: {e}"


async def _disparar_scraping(datos: dict) -> str:
    try:
        from tools.lead_scraper import ejecutar_ciclo_scraping
        r = await ejecutar_ciclo_scraping()
        return (f"✅ Scraping ejecutado — encontrados: {r.get('encontrados',0)}, "
                f"nuevos: {r.get('nuevos',0)}, contactados: {r.get('contactados',0)}")
    except Exception as e:
        return f"❌ Error en scraping: {e}"


async def _reactivar_leads_frios(datos: dict) -> str:
    """Contacta leads fríos para reactivarlos (acción real)."""
    dias   = int(datos.get("dias", 30))
    limite = int(datos.get("limite", 10))
    try:
        leads = await crm_client.get_leads_frios_para_reactivar(dias)
    except Exception as e:
        return f"❌ No pude leer leads fríos: {e}"
    if not leads:
        return "✅ No hay leads fríos para reactivar ahora."
    enviados = 0
    try:
        from channels.whatsapp import send_whatsapp_message
        from agents.valentina import get_agent
        import re as _re
        valentina = get_agent()
        for l in leads[:limite]:
            tel = _normalizar_tel(l.get("telefono", ""))
            if not tel:
                continue
            nombre = l.get("nombre", "") or "vecino"
            prompt = (f"Mensaje corto y cálido de reactivación para {nombre}, que consultó hace "
                      f"un tiempo y no avanzó. Sin presión, ofrecé novedad/beneficio. Como Valentina de EcoFiver.")
            msg = _re.sub(r"\[[^\]]+\]", "", await valentina.respond(prompt)).strip()
            if msg and await send_whatsapp_message(tel, msg):
                enviados += 1
    except Exception as e:
        return f"❌ Error reactivando: {e}"
    return f"✅ Reactivé {enviados} lead(s) frío(s) por WhatsApp"


async def _recordar(datos: dict) -> str:
    """
    Guarda un hecho/instrucción como conocimiento PERMANENTE del agente —
    sobrevive a reinicios y deploys (a diferencia del historial de chat).
    datos: {"contenido": "texto a recordar", "agentes": ["maximo"] (opcional,
    default solo Máximo), "titulo": "..." (opcional)}
    """
    contenido = (datos.get("contenido") or "").strip()
    if not contenido:
        return "❌ Falta 'contenido' para recordar"
    try:
        from tools.knowledge_base import aprender
        doc = aprender(contenido, agentes=datos.get("agentes"), titulo=datos.get("titulo"))
        quienes = ", ".join(doc.get("agentes", []))
        return f"✅ Guardado de forma permanente (para: {quienes}): \"{contenido[:80]}{'...' if len(contenido)>80 else ''}\""
    except Exception as e:
        return f"❌ Error guardando: {e}"
