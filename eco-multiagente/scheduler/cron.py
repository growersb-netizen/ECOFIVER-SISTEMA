"""
Scheduler de tareas programadas para EcoFiver.
Zona horaria: America/Argentina/Buenos_Aires (GMT-3 fijo, sin DST).
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("America/Argentina/Buenos_Aires")

_scheduler: AsyncIOScheduler | None = None


# ─────────────────────────────────────────────
# TAREAS
# ─────────────────────────────────────────────

async def tarea_reporte_diario():
    """08:00 AM — Máximo genera y envía reporte diario a Rodrigo."""
    logger.info("[CRON] Ejecutando reporte diario de Máximo")
    try:
        from channels.telegram_bot import send_daily_report
        await send_daily_report()
    except Exception as e:
        logger.error(f"[CRON] tarea_reporte_diario error: {e}")


async def tarea_reporte_aurora_manana():
    """09:00 AM — Aurora genera reporte matutino interno del pipeline."""
    logger.info("[CRON] Aurora — reporte matutino pipeline")
    try:
        from agents.aurora import get_agent
        from tools import crm_client
        aurora = get_agent()
        stats = await crm_client.get_pipeline_stats()
        await aurora.respond(
            "Generá el reporte matutino del pipeline para Máximo. "
            "Estado actual, prioridades del día y alertas.",
            f"Stats actuales: {stats}",
        )
    except Exception as e:
        logger.error(f"[CRON] tarea_reporte_aurora_manana error: {e}")


async def tarea_check_leads_sin_respuesta():
    """Cada 2hs — Chequea leads sin respuesta y alerta a Tomás."""
    logger.info("[CRON] Check leads sin respuesta >2hs")
    try:
        from tools import crm_client
        from agents.tomas import get_agent
        leads = await crm_client.get_leads_sin_respuesta(horas=2)
        if not leads:
            return
        tomas = get_agent()
        resumen = f"Hay {len(leads)} leads sin respuesta hace más de 2 horas: "
        resumen += ", ".join([
            l.get("nombre", l.get("session_id", "desconocido"))
            for l in leads[:10]
        ])
        await tomas.respond(
            f"ALERTA AUTOMÁTICA: {resumen}. "
            "Activá intervención inmediata en los leads calientes.",
        )
        logger.info(f"[CRON] Tomás alertado sobre {len(leads)} leads sin respuesta")
    except Exception as e:
        logger.error(f"[CRON] tarea_check_leads_sin_respuesta error: {e}")


async def tarea_reporte_aurora_tarde():
    """18:00 PM — Aurora genera reporte vespertino + check cuotas."""
    logger.info("[CRON] Aurora — reporte vespertino + cuotas")
    try:
        from agents.aurora import get_agent
        from tools import crm_client
        aurora = get_agent()
        stats  = await crm_client.get_pipeline_stats()
        ventas = await crm_client.get_ventas_hoy()
        cuotas = await crm_client.get_cuotas_vencidas(1)
        await aurora.respond(
            "Generá el reporte vespertino para Máximo: "
            "resultados del día, tendencias y ajustes necesarios.",
            f"Stats: {stats}\nVentas hoy: {ventas}\nCuotas vencidas: {len(cuotas)}",
        )
    except Exception as e:
        logger.error(f"[CRON] tarea_reporte_aurora_tarde error: {e}")


async def tarea_cobros_ignacio():
    """20:00 PM diario — Ignacio revisa cuotas vencidas y actúa."""
    logger.info("[CRON] Ignacio — revisión de cuotas vencidas")
    try:
        from tools import crm_client
        from agents.ignacio import get_agent
        from channels.whatsapp import send_whatsapp_message

        ignacio = get_agent()
        cuotas = await crm_client.get_cuotas_vencidas(dias=1)

        for cuota in cuotas:
            dias_vencida = cuota.get("dias_vencido", 0)
            cliente_nombre = cuota.get("cliente", "cliente")
            cliente_phone = cuota.get("telefono", "")
            mes_cuota = cuota.get("mes", "este mes")

            if dias_vencida <= 3:
                # Recordatorio cordial automático
                mensaje = await ignacio.respond(
                    f"Generar recordatorio cordial para {cliente_nombre}, "
                    f"cuota de {mes_cuota} vencida hace {dias_vencida} días.",
                )
                if cliente_phone:
                    await send_whatsapp_message(cliente_phone, mensaje)

            elif dias_vencida <= 7:
                # Consulta de situación
                mensaje = await ignacio.respond(
                    f"Generar mensaje de consulta para {cliente_nombre}, "
                    f"cuota vencida hace {dias_vencida} días.",
                )
                if cliente_phone:
                    await send_whatsapp_message(cliente_phone, mensaje)

            elif dias_vencida <= 15:
                # Propuesta refinanciación (requiere autorización Máximo)
                logger.info(
                    f"[CRON] Cuota {dias_vencida} días vencida — "
                    f"escalando a Ezequiel para {cliente_nombre}"
                )

            else:
                # Escalar a Ezequiel y Máximo
                logger.warning(
                    f"[CRON] Cuota +16 días — escalando a Máximo para {cliente_nombre}"
                )
                try:
                    from channels.telegram_bot import send_alert
                    await send_alert(
                        f"⚠️ CUOTA CRÍTICA: {cliente_nombre} lleva {dias_vencida} días "
                        f"sin pagar. Requiere decisión."
                    )
                except Exception:
                    pass

        logger.info(f"[CRON] Ignacio procesó {len(cuotas)} cuotas vencidas")
    except Exception as e:
        logger.error(f"[CRON] tarea_cobros_ignacio error: {e}")


async def tarea_seguimiento_leads_frios():
    """
    11:00 AM y 16:00 PM — Valentina hace seguimiento multitouch (3 intentos máx).
    Sistema: intento 1 (48hs), intento 2 (72hs), intento 3 (96hs) → FRIO.
    Cada intento usa un mensaje diferente. Después del 3er intento → lead pasa a FRIO.
    """
    logger.info("[CRON] Seguimiento leads fríos — multitouch 3 intentos")
    try:
        from tools import crm_client
        from agents.valentina import get_agent
        from channels.whatsapp import send_whatsapp_message
        import asyncio

        # Buscar leads sin respuesta hace +48hs
        leads = await crm_client.get_leads_sin_respuesta(horas=48)
        if not leads:
            logger.info("[CRON] No hay leads para seguimiento")
            return

        # Filtrar: solo los que tienen < 3 intentos y no están cerrados/fríos
        ESTADOS_EXCLUIR = {"CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO", "FRIO", "PERDIDO"}
        leads_elegibles = [
            l for l in leads
            if l.get("estado") not in ESTADOS_EXCLUIR
            and l.get("intentos_seguimiento", 0) < 3
        ]

        if not leads_elegibles:
            logger.info("[CRON] Todos los leads ya alcanzaron 3 intentos o están cerrados")
            return

        valentina = get_agent()
        enviados = 0

        TEMPLATES = {
            0: (
                "Generá un mensaje corto de seguimiento (1-2 oraciones, informal, sin presión) "
                "para {nombre} que consultó por {producto} hace más de 2 días y no respondió. "
                "No mencionés que sos IA. Solo preguntá si sigue con dudas o necesita más info. "
                "Firmá como Valentina de EcoFiver."
            ),
            1: (
                "Generá un segundo mensaje de seguimiento corto para {nombre} que consultó por {producto}. "
                "Esta es la segunda vez que lo contactamos. Mencioná algún beneficio clave "
                "(financiación propia, instalación incluida, o piscinas de fibra premium). "
                "Tono amigable y sin presión. Firmá como Valentina de EcoFiver."
            ),
            2: (
                "Generá el ÚLTIMO mensaje de seguimiento para {nombre} que consultó por {producto}. "
                "Es el tercer contacto. Decí que entendés que quizás no es el momento, "
                "pero que quedás disponible cuando lo necesite. Dejá la puerta abierta. "
                "Tono muy cálido. Firmá como Valentina de EcoFiver."
            ),
        }

        for lead in leads_elegibles[:12]:  # Máximo 12 por turno
            telefono = lead.get("telefono", "")
            nombre   = lead.get("nombre", "") or "vecino"
            producto = lead.get("producto_interes", "") or "nuestros productos"
            intento  = lead.get("intentos_seguimiento", 0)
            lead_id  = lead.get("id")

            if not telefono:
                continue

            template = TEMPLATES.get(intento, TEMPLATES[0])
            prompt   = template.format(nombre=nombre, producto=producto)

            mensaje = await valentina.respond(prompt)

            if mensaje and telefono:
                try:
                    await send_whatsapp_message(telefono, mensaje)
                    enviados += 1
                    logger.info(
                        f"[CRON] Seguimiento intento {intento+1}/3 enviado a {nombre} ({telefono})"
                    )
                    if lead_id:
                        await crm_client.incrementar_intentos_seguimiento(lead_id)
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.warning(f"[CRON] No se pudo enviar a {telefono}: {e}")

        logger.info(
            f"[CRON] Seguimiento multitouch: {enviados}/{len(leads_elegibles[:12])} mensajes enviados"
        )

    except Exception as e:
        logger.error(f"[CRON] tarea_seguimiento_leads_frios error: {e}")


async def tarea_contacto_leads_nuevos():
    """
    Cada 15 min — Detecta leads nuevos que llegaron por Meta Ads u otros canales
    sin haber sido contactados aún y les envía el primer mensaje por WhatsApp.
    """
    logger.info("[CRON] Contacto automático leads nuevos sin contactar")
    try:
        from tools import crm_client
        from agents.valentina import get_agent
        from channels.whatsapp import send_whatsapp_message
        import asyncio

        leads = await crm_client.get_leads_nuevos_sin_contactar(minutos=30)
        if not leads:
            return

        valentina = get_agent()
        for lead in leads[:8]:  # Máx 8 por ciclo para no saturar
            telefono = lead.get("telefono", "")
            nombre   = lead.get("nombre", "") or "vecino"
            producto = lead.get("producto_interes", "") or "nuestros productos"
            if not telefono:
                continue
            msg = await valentina.respond(
                f"Primer contacto para {nombre} que se interesó en {producto}. "
                "Mensaje cálido, breve, 1-2 oraciones. Presentate como Valentina de EcoFiver."
            )
            import re
            msg = re.sub(r"\[DERIVAR:\w+\]|\[AGENDA_VV:[^\]]+\]|\[LLAMADA_SUP:[^\]]+\]", "", msg).strip()
            if msg:
                await send_whatsapp_message(telefono, msg)
                logger.info(f"[CRON] Primer contacto enviado a {nombre} ({telefono})")
                await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"[CRON] tarea_contacto_leads_nuevos error: {e}")


async def tarea_recordatorio_videollamadas():
    """
    Cada hora — Detecta videollamadas programadas en las próximas 2 horas
    y envía recordatorio automático al cliente por WhatsApp.
    """
    logger.info("[CRON] Recordatorio de videollamadas próximas")
    try:
        from tools import crm_client
        from channels.whatsapp import send_whatsapp_message

        vvs = await crm_client.get_videollamadas_proximas(horas=2)
        if not vvs:
            return

        for vv in vvs:
            telefono = vv.get("telefono", "")
            nombre   = vv.get("nombre", "")
            hora     = vv.get("hora", "en breve")
            if not telefono:
                continue
            msg = (
                f"Hola {nombre}! Te recuerdo que en breve tenemos nuestra videollamada "
                f"a las {hora}. ¿Confirmás que vas a poder estar? "
                f"Recordá tener a todos los que van a decidir presentes. Saludos, equipo EcoFiver."
            )
            await send_whatsapp_message(telefono, msg)
            logger.info(f"[CRON] Recordatorio VV enviado a {nombre} ({telefono})")
    except Exception as e:
        logger.error(f"[CRON] tarea_recordatorio_videollamadas error: {e}")


async def tarea_nutricion_24h():
    """
    10:00 y 15:00 — Envía contenido de nutrición a leads de entre 20 y 30 horas
    que no respondieron. Muestra beneficios del producto que consultaron.
    """
    logger.info("[CRON] Nutrición 24hs de leads")
    try:
        from tools import crm_client
        from agents.valentina import get_agent
        from channels.whatsapp import send_whatsapp_message
        import asyncio, re

        leads = await crm_client.get_leads_para_nutrir(horas_desde=20, horas_hasta=30)
        if not leads:
            return

        valentina = get_agent()
        for lead in leads[:10]:
            telefono = lead.get("telefono", "")
            nombre   = lead.get("nombre", "") or "vecino"
            producto = lead.get("producto_interes", "") or "nuestros productos"
            if not telefono:
                continue
            msg = await valentina.respond(
                f"Mensaje de nutrición (educativo, no de venta) para {nombre} "
                f"que consultó por {producto} ayer. "
                "Compartí un beneficio clave o dato interesante del producto. "
                "Máx 3 oraciones. Sin presión. Firmá como Valentina de EcoFiver."
            )
            msg = re.sub(r"\[DERIVAR:\w+\]|\[AGENDA_VV:[^\]]+\]|\[LLAMADA_SUP:[^\]]+\]", "", msg).strip()
            if msg:
                await send_whatsapp_message(telefono, msg)
                logger.info(f"[CRON] Nutrición 24h enviada a {nombre} ({telefono})")
                await asyncio.sleep(3)
    except Exception as e:
        logger.error(f"[CRON] tarea_nutricion_24h error: {e}")


async def tarea_scraping_organico():
    """Cada 4hs — Scraper orgánico: MercadoLibre + OLX + clasificados web."""
    logger.info("[CRON] Scraping orgánico de leads")
    try:
        from tools.lead_scraper import ejecutar_ciclo_scraping
        resumen = await ejecutar_ciclo_scraping()
        logger.info(f"[CRON] Scraping completado: {resumen}")
    except Exception as e:
        logger.error(f"[CRON] tarea_scraping_organico error: {e}")


async def tarea_publicar_contenido():
    """10:00 AM y 19:00 PM — Renata genera y publica contenido orgánico en FB/IG."""
    logger.info("[CRON] Publicación de contenido orgánico — Renata")
    try:
        from tools.content_poster import tarea_publicar_contenido_diario
        await tarea_publicar_contenido_diario()
    except Exception as e:
        logger.error(f"[CRON] tarea_publicar_contenido error: {e}")


async def tarea_procesar_emails():
    """Cada 3hs — Procesa emails entrantes (backup al polling continuo del canal)."""
    logger.info("[CRON] Procesando emails entrantes")
    try:
        from channels.email_channel import procesar_ciclo_email_unico
        n = await procesar_ciclo_email_unico()
        if n:
            logger.info(f"[CRON] {n} emails procesados")
    except Exception as e:
        logger.error(f"[CRON] tarea_procesar_emails error: {e}")


async def tarea_calendario_contenido_semanal():
    """Lunes 09:15 — Renata planifica el calendario de contenido de la semana."""
    logger.info("[CRON] Renata — calendario de contenido semanal")
    try:
        from agents.renata import get_agent
        from datetime import datetime
        renata = get_agent()
        semana = datetime.now(TIMEZONE).strftime("Semana del %d/%m/%Y")
        await renata.respond(
            f"Planificá el calendario de contenido para {semana}: "
            "posts diarios de lunes a domingo para Facebook e Instagram. "
            "Considerá la temporada actual, los productos estrella y el funnel de ventas. "
            "Incluí tipo de post, foco, CTA y hashtags sugeridos para cada día."
        )
        logger.info("[CRON] Calendario semanal de contenido generado")
    except Exception as e:
        logger.error(f"[CRON] tarea_calendario_contenido_semanal error: {e}")


async def tarea_reactivacion_leads_frios():
    """
    Primer lunes de cada mes — Reactiva leads que llevan +30 días inactivos
    con un mensaje de oportunidad estacional.
    """
    logger.info("[CRON] Reactivación leads fríos — primer lunes del mes")
    try:
        from tools import crm_client
        from agents.valentina import get_agent
        from channels.whatsapp import send_whatsapp_message
        import asyncio, re
        from datetime import datetime

        # Solo ejecutar el primer lunes del mes
        hoy = datetime.now(TIMEZONE)
        if hoy.weekday() != 0 or hoy.day > 7:
            return

        leads = await crm_client.get_leads_frios_para_reactivar(dias_inactivo=30)
        if not leads:
            return

        valentina = get_agent()
        for lead in leads[:15]:
            telefono = lead.get("telefono", "")
            nombre   = lead.get("nombre", "") or "vecino"
            producto = lead.get("producto_interes", "") or "nuestros productos"
            if not telefono:
                continue
            msg = await valentina.respond(
                f"Mensaje de reactivación estacional para {nombre} que consultó "
                f"por {producto} hace más de 30 días y no respondió más. "
                "Contexto de temporada actual. Mencioná una novedad o beneficio. "
                "Tono muy cálido, sin presión, dejá la puerta abierta. "
                "Firmá como Valentina de EcoFiver."
            )
            msg = re.sub(r"\[DERIVAR:\w+\]|\[AGENDA_VV:[^\]]+\]|\[LLAMADA_SUP:[^\]]+\]", "", msg).strip()
            if msg:
                await send_whatsapp_message(telefono, msg)
                logger.info(f"[CRON] Reactivación enviada a {nombre} ({telefono})")
                await asyncio.sleep(4)
    except Exception as e:
        logger.error(f"[CRON] tarea_reactivacion_leads_frios error: {e}")


async def tarea_llamada_supervisora_pendiente():
    """
    Cada 2hs — Verifica llamadas de supervisora pendientes y envía recordatorio
    al cliente si no se concretó la llamada.
    """
    logger.info("[CRON] Check llamadas supervisora pendientes")
    try:
        from tools import crm_client
        from channels.whatsapp import send_whatsapp_message

        pendientes = await crm_client.get_llamadas_supervisora_pendientes()
        if not pendientes:
            return

        for llamada in pendientes:
            telefono = llamada.get("telefono", "")
            nombre   = llamada.get("nombre", "")
            hora     = llamada.get("hora_pactada", "")
            if not telefono:
                continue
            msg = (
                f"Hola {nombre}! Te escribimos del equipo de EcoFiver. "
                f"Quedamos en hablar{' a las ' + hora if hora else ''} y no pudimos conectar. "
                "¿Podemos reagendar? Decinos qué horario te viene mejor. Gracias!"
            )
            await send_whatsapp_message(telefono, msg)
            logger.info(f"[CRON] Recordatorio llamada sup enviado a {nombre} ({telefono})")
    except Exception as e:
        logger.error(f"[CRON] tarea_llamada_supervisora_pendiente error: {e}")


async def tarea_semanal_lunes():
    """Lunes 09:00 AM — Elena reporte semanal + Renata calendario de contenido."""
    logger.info("[CRON] Lunes — reporte semanal Elena + calendario Renata")
    try:
        from agents.elena import get_agent as get_elena
        from agents.renata import get_agent as get_renata
        from tools import crm_client

        stats = await crm_client.get_pipeline_stats()

        elena = get_elena()
        await elena.respond(
            "Generá el reporte semanal completo de pipeline y finanzas para Ezequiel.",
            f"Stats semanales: {stats}",
        )

        renata = get_renata()
        await renata.respond(
            "Proponé el calendario de contenido para esta semana: "
            "posts, stories, campañas. Considerá la temporada actual.",
        )

        logger.info("[CRON] Reporte semanal y calendario generados")
    except Exception as e:
        logger.error(f"[CRON] tarea_semanal_lunes error: {e}")


# ─────────────────────────────────────────────
# TAREAS FRANCO — CANAL DE ALIADOS
# ─────────────────────────────────────────────

async def tarea_franco_onboarding_postulantes():
    """Cada 30 min entre 9 y 20 — Detecta nuevos postulantes en CRM y arranca el quiz por WA."""
    logger.info("[CRON] Franco — check nuevos postulantes")
    try:
        import os
        from tools.crm_aliados import get_aliados_inactivos
        from tools.franco_quiz import iniciar_quiz, esta_en_quiz, MENSAJE_BIENVENIDA, PREGUNTAS
        from channels.whatsapp import enviar_mensaje_wa

        FRANCO_WA = os.getenv("FRANCO_WHATSAPP_NUMBER", "")
        if not FRANCO_WA:
            return

        from tools import crm_client
        postulantes = []
        try:
            import httpx
            from tools.crm_client import CRM_BASE_URL, HEADERS, TIMEOUT
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.get(
                    f"{CRM_BASE_URL}/api/aliados",
                    headers=HEADERS,
                    params={"estado": "postulante"},
                )
                r.raise_for_status()
                postulantes = r.json()
        except Exception as e:
            logger.warning(f"[CRON] Franco — no se pudieron obtener postulantes: {e}")
            return

        for p in postulantes:
            telefono = p.get("telefono", "")
            nombre = p.get("nombre", "")
            codigo = p.get("codigo", telefono)
            if not telefono or esta_en_quiz(telefono):
                continue

            iniciar_quiz(telefono, nombre, codigo)

            bienvenida = MENSAJE_BIENVENIDA.format(nombre=nombre)
            primera_pregunta = f"\n*Pregunta 1 de 10:* {PREGUNTAS[0]['texto']}"

            try:
                await enviar_mensaje_wa(telefono, bienvenida + primera_pregunta, phone_id=FRANCO_WA)
                logger.info(f"[CRON] Franco — quiz iniciado para {codigo} ({telefono})")
            except Exception as we:
                logger.warning(f"[CRON] Franco — WA falló para {telefono}: {we}")

    except Exception as e:
        logger.error(f"[CRON] tarea_franco_onboarding_postulantes error: {e}")


async def tarea_franco_timeout_postulantes():
    """08:00 AM diario — Marca como inactivos postulantes sin respuesta hace 5+ días."""
    logger.info("[CRON] Franco — timeout postulantes")
    try:
        import os
        from tools.franco_quiz import postulantes_con_timeout, estado_quiz, limpiar_estado, MENSAJE_TIMEOUT
        from channels.whatsapp import enviar_mensaje_wa

        FRANCO_WA = os.getenv("FRANCO_WHATSAPP_NUMBER", "")
        con_timeout = postulantes_con_timeout()
        if not con_timeout:
            return

        import httpx
        from tools.crm_client import CRM_BASE_URL, HEADERS, TIMEOUT

        for telefono in con_timeout:
            est = estado_quiz(telefono)
            nombre = est.get("nombre", "") if est else ""
            codigo = est.get("codigo_postulante", "") if est else ""

            # Marcar inactivo en CRM
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    await client.put(
                        f"{CRM_BASE_URL}/api/aliados/{codigo}",
                        headers=HEADERS,
                        json={"estado": "inactivo"},
                    )
            except Exception as ce:
                logger.warning(f"[CRON] Franco — CRM inactivo falló para {codigo}: {ce}")

            # Mensaje de cierre amable
            if FRANCO_WA and nombre:
                try:
                    await enviar_mensaje_wa(
                        telefono,
                        MENSAJE_TIMEOUT.format(nombre=nombre),
                        phone_id=FRANCO_WA,
                    )
                except Exception:
                    pass

            limpiar_estado(telefono)
            logger.info(f"[CRON] Franco — postulante {codigo} marcado inactivo por timeout")

        logger.info(f"[CRON] Franco — {len(con_timeout)} postulantes con timeout procesados")
    except Exception as e:
        logger.error(f"[CRON] tarea_franco_timeout_postulantes error: {e}")


async def tarea_franco_material_lunes():
    """Lunes 08:00 — Franco envía pieza gráfica + copy comercial al grupo de aliados."""
    logger.info("[CRON] Franco — material lunes")
    try:
        import os
        from agents.franco import get_agent
        from channels.telegram_bot import send_to_aliados_wa
        from tools.asset_library import get_asset_of_week

        franco = get_agent()
        asset = await get_asset_of_week() if callable(getattr(__builtins__, '__import__', None)) else {}
        copy_msg = await franco.respond(
            "Hoy es lunes. Generá el mensaje semanal de apertura para el grupo de aliados: "
            "saludá, motivá y adjuntá el material de esta semana. "
            f"Material disponible: {asset}",
        )
        await send_to_aliados_wa(copy_msg)
        logger.info("[CRON] Franco — material lunes enviado")
    except Exception as e:
        logger.error(f"[CRON] tarea_franco_material_lunes error: {e}")


async def tarea_franco_caso_ganado_miercoles():
    """Miércoles 08:00 — Franco envía caso ganado de la semana al grupo de aliados."""
    logger.info("[CRON] Franco — caso ganado miércoles")
    try:
        from agents.franco import get_agent
        from channels.telegram_bot import send_to_aliados_wa
        from tools import crm_client

        franco = get_agent()
        ventas_semana = await crm_client.get_ventas_semana() if hasattr(crm_client, "get_ventas_semana") else []
        msg = await franco.respond(
            "Hoy es miércoles. Compartí el caso ganado de la semana para inspirar al equipo de aliados. "
            "Mencioná el producto, la localidad (sin datos del cliente) y un detalle que motive. "
            f"Ventas de esta semana: {ventas_semana}",
        )
        await send_to_aliados_wa(msg)
        logger.info("[CRON] Franco — caso ganado enviado")
    except Exception as e:
        logger.error(f"[CRON] tarea_franco_caso_ganado_miercoles error: {e}")


async def tarea_franco_ranking_viernes():
    """Viernes 08:00 — Franco envía ranking semanal + recordatorio de comisiones liquidadas."""
    logger.info("[CRON] Franco — ranking viernes")
    try:
        from agents.franco import get_agent
        from channels.telegram_bot import send_to_aliados_wa
        from tools.crm_aliados import get_ranking_aliados

        franco = get_agent()
        ranking = await get_ranking_aliados(periodo="semana")
        msg = await franco.respond(
            "Hoy es viernes. Publicá el ranking semanal de aliados y recordá las comisiones "
            "liquidadas esta semana. Motivá para cerrar fuerte el fin de semana. "
            f"Ranking: {ranking}",
        )
        await send_to_aliados_wa(msg)
        logger.info("[CRON] Franco — ranking viernes enviado")
    except Exception as e:
        logger.error(f"[CRON] tarea_franco_ranking_viernes error: {e}")


async def tarea_franco_reenganche_aliados():
    """10:30 AM diario — Re-enganche de aliados inactivos hace 14+ días."""
    logger.info("[CRON] Franco — check aliados inactivos")
    try:
        import os
        from tools.crm_aliados import get_aliados_inactivos

        FRANCO_WA_NUMBER = os.getenv("FRANCO_WHATSAPP_NUMBER", "")
        if not FRANCO_WA_NUMBER:
            return

        inactivos = await get_aliados_inactivos(dias=14)
        if not inactivos:
            return

        from channels.whatsapp import enviar_mensaje_wa
        from agents.franco import get_agent
        franco = get_agent()

        for aliado in inactivos:
            telefono = aliado.get("telefono", "")
            nombre = aliado.get("nombre", "")
            if not telefono:
                continue
            msg = await franco.respond(
                f"Re-enganche suave para aliado inactivo 14+ días. "
                f"Nombre: {nombre}. Mandá el mensaje de re-enganche indicado en tu rol.",
            )
            try:
                await enviar_mensaje_wa(telefono, msg, phone_id=FRANCO_WA_NUMBER)
            except Exception as we:
                logger.warning(f"[CRON] Franco re-enganche WA falló para {telefono}: {we}")

        logger.info(f"[CRON] Franco — re-enganche enviado a {len(inactivos)} aliados")
    except Exception as e:
        logger.error(f"[CRON] tarea_franco_reenganche_aliados error: {e}")


async def tarea_franco_resumen_mensual():
    """Primer día hábil del mes 09:00 — Resumen mensual personalizado a cada aliado activo."""
    logger.info("[CRON] Franco — resumen mensual aliados")
    try:
        import os
        from datetime import datetime
        import pytz

        tz = pytz.timezone("America/Argentina/Buenos_Aires")
        hoy = datetime.now(tz)

        # Solo ejecutar si es el primer día hábil del mes (día <= 7, no domingo)
        if hoy.day > 7 or hoy.weekday() == 6:
            return

        FRANCO_WA_NUMBER = os.getenv("FRANCO_WHATSAPP_NUMBER", "")
        if not FRANCO_WA_NUMBER:
            return

        from tools.crm_aliados import get_aliados_activos, get_aliado_ventas, get_aliado_comisiones
        from channels.whatsapp import enviar_mensaje_wa
        from agents.franco import get_agent

        franco = get_agent()
        aliados = await get_aliados_activos()

        for aliado in aliados:
            codigo = aliado.get("codigo", "")
            telefono = aliado.get("telefono", "")
            nombre = aliado.get("nombre", "")
            if not telefono or not codigo:
                continue

            ventas = await get_aliado_ventas(codigo)
            comisiones = await get_aliado_comisiones(codigo)

            msg = await franco.respond(
                f"Resumen mensual para aliado activo. "
                f"Nombre: {nombre}, código: {codigo}. "
                f"Ventas del mes: {ventas}. "
                f"Comisiones: {comisiones}. "
                "Generá el resumen mensual personalizado según tu rol.",
            )
            try:
                await enviar_mensaje_wa(telefono, msg, phone_id=FRANCO_WA_NUMBER)
            except Exception as we:
                logger.warning(f"[CRON] Franco resumen mensual WA falló para {telefono}: {we}")

        logger.info(f"[CRON] Franco — resumen mensual enviado a {len(aliados)} aliados")
    except Exception as e:
        logger.error(f"[CRON] tarea_franco_resumen_mensual error: {e}")


# ─────────────────────────────────────────────
# INICIALIZACIÓN DEL SCHEDULER
# ─────────────────────────────────────────────

def start_scheduler():
    """
    Configura e inicia el scheduler con todas las tareas programadas.
    Llamado desde main.py en el evento de startup.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # 08:00 AM — Reporte diario de Máximo a Rodrigo
    _scheduler.add_job(
        tarea_reporte_diario,
        CronTrigger(hour=8, minute=0, timezone=TIMEZONE),
        id="reporte_diario_maximo",
        name="Reporte diario Máximo → Rodrigo",
        replace_existing=True,
    )

    # 09:00 AM — Reporte matutino de Aurora
    _scheduler.add_job(
        tarea_reporte_aurora_manana,
        CronTrigger(hour=9, minute=0, timezone=TIMEZONE),
        id="reporte_aurora_manana",
        name="Reporte matutino Aurora",
        replace_existing=True,
    )

    # Cada hora entre 8 y 22 — Check leads sin respuesta (más seguido = menos leads perdidos)
    _scheduler.add_job(
        tarea_check_leads_sin_respuesta,
        CronTrigger(minute=0, hour="8-22", timezone=TIMEZONE),
        id="check_leads_sin_respuesta",
        name="Check leads sin respuesta >2hs",
        replace_existing=True,
    )

    # 18:00 PM — Reporte vespertino Aurora + check cuotas
    _scheduler.add_job(
        tarea_reporte_aurora_tarde,
        CronTrigger(hour=18, minute=0, timezone=TIMEZONE),
        id="reporte_aurora_tarde",
        name="Reporte vespertino Aurora",
        replace_existing=True,
    )

    # 20:00 PM — Cobros Ignacio
    _scheduler.add_job(
        tarea_cobros_ignacio,
        CronTrigger(hour=20, minute=0, timezone=TIMEZONE),
        id="cobros_ignacio",
        name="Cobros Ignacio — revisión cuotas vencidas",
        replace_existing=True,
    )

    # Lunes 09:00 AM — Reporte semanal
    _scheduler.add_job(
        tarea_semanal_lunes,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=TIMEZONE),
        id="reporte_semanal_lunes",
        name="Reporte semanal Elena + Calendario Renata",
        replace_existing=True,
    )

    # 11:00 AM y 16:00 PM — Seguimiento leads fríos (Valentina)
    _scheduler.add_job(
        tarea_seguimiento_leads_frios,
        CronTrigger(hour="11,16", minute=0, timezone=TIMEZONE),
        id="seguimiento_leads_frios",
        name="Seguimiento leads fríos — Valentina",
        replace_existing=True,
    )

    # Cada 8 min entre 8 y 22 — Contacto automático leads nuevos (respuesta casi inmediata)
    _scheduler.add_job(
        tarea_contacto_leads_nuevos,
        CronTrigger(minute="*/8", hour="8-22", timezone=TIMEZONE),
        id="contacto_leads_nuevos",
        name="Contacto leads nuevos sin contactar",
        replace_existing=True,
    )

    # Cada hora entre 9 y 20 — Recordatorio videollamadas próximas
    _scheduler.add_job(
        tarea_recordatorio_videollamadas,
        CronTrigger(minute=0, hour="9-20", timezone=TIMEZONE),
        id="recordatorio_videollamadas",
        name="Recordatorio videollamadas próximas 2hs",
        replace_existing=True,
    )

    # 10:00, 15:00 y 19:00 — Nutrición 24hs de leads (3 toques/día)
    _scheduler.add_job(
        tarea_nutricion_24h,
        CronTrigger(hour="10,15,19", minute=0, timezone=TIMEZONE),
        id="nutricion_24h",
        name="Nutrición 24hs — contenido educativo",
        replace_existing=True,
    )

    # Cada 2hs entre 9 y 19 — Llamadas supervisora pendientes
    _scheduler.add_job(
        tarea_llamada_supervisora_pendiente,
        CronTrigger(hour="9,11,13,15,17,19", minute=30, timezone=TIMEZONE),
        id="llamada_supervisora_pendiente",
        name="Check llamadas supervisora pendientes",
        replace_existing=True,
    )

    # Primer lunes de mes 09:30 — Reactivación leads fríos
    _scheduler.add_job(
        tarea_reactivacion_leads_frios,
        CronTrigger(day_of_week="mon", hour=9, minute=30, timezone=TIMEZONE),
        id="reactivacion_leads_frios",
        name="Reactivación leads fríos — mensual",
        replace_existing=True,
    )

    # ── NUEVAS TAREAS: Generación orgánica de leads ──────────────────────────

    # Cada 2hs entre 6 y 22 — Scraping orgánico de leads (MLA, OLX, clasificados)
    _scheduler.add_job(
        tarea_scraping_organico,
        CronTrigger(hour="6,8,10,12,14,16,18,20,22", minute=15, timezone=TIMEZONE),
        id="scraping_organico",
        name="Scraping orgánico de leads — MLA + OLX + clasificados",
        replace_existing=True,
    )

    # 4 veces por día — Renata publica contenido orgánico en FB/IG (más alcance = más inbound)
    _scheduler.add_job(
        tarea_publicar_contenido,
        CronTrigger(hour="9,13,17,20", minute=0, timezone=TIMEZONE),
        id="publicar_contenido_renata",
        name="Renata — publicación orgánica FB + IG",
        replace_existing=True,
    )

    # Cada 3hs — Procesar emails entrantes (backup al polling continuo)
    _scheduler.add_job(
        tarea_procesar_emails,
        CronTrigger(hour="7,10,13,16,19,22", minute=45, timezone=TIMEZONE),
        id="procesar_emails",
        name="Procesar emails entrantes",
        replace_existing=True,
    )

    # 09:00 AM — Renata propone y planifica calendario semanal de contenido
    _scheduler.add_job(
        tarea_calendario_contenido_semanal,
        CronTrigger(day_of_week="mon", hour=9, minute=15, timezone=TIMEZONE),
        id="calendario_contenido_semanal",
        name="Renata — calendario de contenido semanal",
        replace_existing=True,
    )

    # ── TAREAS FRANCO — CANAL DE ALIADOS ────────────────────────────────────

    # Cada 30 min entre 9 y 20 — Detecta nuevos postulantes e inicia quiz
    _scheduler.add_job(
        tarea_franco_onboarding_postulantes,
        CronTrigger(minute="0,30", hour="9-20", timezone=TIMEZONE),
        id="franco_onboarding_postulantes",
        name="Franco — onboarding quiz nuevos postulantes",
        replace_existing=True,
    )

    # 08:00 AM diario — Timeout postulantes sin respuesta 5+ días
    _scheduler.add_job(
        tarea_franco_timeout_postulantes,
        CronTrigger(hour=8, minute=15, timezone=TIMEZONE),
        id="franco_timeout_postulantes",
        name="Franco — timeout postulantes inactivos",
        replace_existing=True,
    )

    # Lunes 08:00 — Material semanal + copy comercial
    _scheduler.add_job(
        tarea_franco_material_lunes,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=TIMEZONE),
        id="franco_material_lunes",
        name="Franco — material lunes aliados",
        replace_existing=True,
    )

    # Miércoles 08:00 — Caso ganado de la semana
    _scheduler.add_job(
        tarea_franco_caso_ganado_miercoles,
        CronTrigger(day_of_week="wed", hour=8, minute=0, timezone=TIMEZONE),
        id="franco_caso_ganado_miercoles",
        name="Franco — caso ganado miércoles",
        replace_existing=True,
    )

    # Viernes 08:00 — Ranking semanal + recordatorio comisiones
    _scheduler.add_job(
        tarea_franco_ranking_viernes,
        CronTrigger(day_of_week="fri", hour=8, minute=0, timezone=TIMEZONE),
        id="franco_ranking_viernes",
        name="Franco — ranking viernes aliados",
        replace_existing=True,
    )

    # 10:30 AM diario — Re-enganche aliados inactivos 14+ días
    _scheduler.add_job(
        tarea_franco_reenganche_aliados,
        CronTrigger(hour=10, minute=30, timezone=TIMEZONE),
        id="franco_reenganche_aliados",
        name="Franco — re-enganche aliados inactivos",
        replace_existing=True,
    )

    # 09:00 — Resumen mensual (se auto-filtra al primer día hábil del mes)
    _scheduler.add_job(
        tarea_franco_resumen_mensual,
        CronTrigger(day="1-7", hour=9, minute=0, timezone=TIMEZONE),
        id="franco_resumen_mensual",
        name="Franco — resumen mensual aliados",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        f"[CRON] Scheduler iniciado con {len(_scheduler.get_jobs())} tareas programadas"
    )


def stop_scheduler():
    """Detiene el scheduler de forma limpia."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[CRON] Scheduler detenido.")
