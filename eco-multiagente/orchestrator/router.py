"""
Router principal del sistema multiagente Eco Módulos & Piscinas.
Recibe mensajes de cualquier canal, determina el agente correcto
y gestiona el ciclo completo de conversación con el CRM.
"""

import os
import logging
import re
from tools import crm_client
from tools.crm_actions import detectar_acciones, limpiar_acciones, ejecutar_acciones
from tools.audit_log import registrar_interaccion

logger = logging.getLogger(__name__)

# ── Número de teléfono del admin (Rodrigo) ─────────────────────────────────
ADMIN_WA_PHONES: set[str] = {"5491135164644", "549113516444"}  # sin el +

# Leads ya alertados como calientes (en memoria, evita spamear la misma alerta)
_leads_alertados_calientes: set[str] = set()


async def _evaluar_y_alertar_lead(session_id, mensaje, reply, agent_name, canal):
    """Evalúa la temperatura del lead; si es CALIENTE y es nuevo, actualiza estado y alerta a Rodrigo."""
    from tools.lead_scoring import evaluar_temperatura
    temp = evaluar_temperatura(mensaje, reply)
    if temp["temperatura"] != "caliente":
        return
    # Actualizar estado en el CRM (best-effort)
    try:
        await crm_client.update_lead(session_id, {"estado": "caliente"})
    except Exception:
        pass
    # Alertar a Rodrigo una sola vez por lead
    if session_id in _leads_alertados_calientes:
        return
    _leads_alertados_calientes.add(session_id)
    try:
        from channels.telegram_bot import send_alert
        nombre_ag = agent_name.capitalize() if agent_name else "?"
        await send_alert(
            f"🔥 LEAD CALIENTE detectado\n"
            f"Canal: {canal} · Lead: {session_id}\n"
            f"Atiende: {nombre_ag}\n"
            f"Último mensaje: \"{(mensaje or '')[:140]}\"\n"
            f"→ Priorizá el cierre."
        )
        logger.info(f"[Router] Alerta lead caliente enviada: {session_id}")
    except Exception as e:
        logger.warning(f"[Router] No se pudo enviar alerta de lead caliente: {e}")

# Mapa de nombre de agente → módulo importable
AGENTES_DISPONIBLES = {
    "valentina": "agents.valentina",
    "camila":    "agents.camila",
    "mateo":     "agents.mateo",
    "nicolas":   "agents.nicolas",
    "luciano":   "agents.luciano",
    "renata":    "agents.renata",
    "bruno":     "agents.bruno",
    "ezequiel":  "agents.ezequiel",
    "ignacio":   "agents.ignacio",
    "elena":     "agents.elena",
    "daniela":   "agents.daniela",
    "sebastian": "agents.sebastian",
    "aurora":    "agents.aurora",
    "tomas":     "agents.tomas",
    "maximo":    "agents.maximo",
    # ── Agente privado de Rodo ──────────────────────────────────────────
    "valentin":  "agents.valentin",
    # ── Canal de aliados comerciales ────────────────────────────────────
    "franco":    "agents.franco",
}

# ── Detección directa de cambio de agente en canal admin ───────────────────
# Evita que el fallback de IA (Groq/Llama) confunda nombres de agentes.
# Solo activa cuando el mensaje contiene un verbo de solicitud de cambio.
_SWITCH_REQUEST_RE = re.compile(
    r"\b(pasame|pasá|conectame|conectá|quiero hablar|llamá|llamame|"
    r"derivame|necesito hablar|poneme con|hablame con|buscame|traeme)\b",
    re.IGNORECASE,
)
_AGENTE_KEYWORDS: dict[str, list[str]] = {
    "valentin":  ["valentin", "valentín", "dr ríos", "dr rios", "dr. ríos",
                  "terapeuta", "psicólogo", "psicologo", "dr. rios"],
    "aurora":    ["aurora", "gerente comercial"],
    "tomas":     ["tomas", "tomás", "supervisor"],
    "camila":    ["camila"],
    "mateo":     ["mateo"],
    "nicolas":   ["nicolas", "nicolás"],
    "luciano":   ["luciano"],
    "renata":    ["renata", "marketing"],
    "bruno":     ["bruno", "logística", "logistica", "operaciones"],
    "ezequiel":  ["ezequiel", "administración", "administracion"],
    "ignacio":   ["ignacio", "cobrador", "cobros"],
    "elena":     ["elena", "finanzas"],
    "daniela":   ["daniela", "rrpp", "crisis"],
    "sebastian": ["sebastian", "sebastián", "postventa"],
    "valentina": ["valentina"],
}


def _detectar_switch_agente(msg_lower: str) -> str | None:
    """
    Detecta si Rodrigo pide cambiar de agente en el canal admin.
    Solo actúa cuando hay un verbo de solicitud explícito.
    Retorna el nombre del agente o None.
    """
    if not _SWITCH_REQUEST_RE.search(msg_lower):
        return None
    for agente, keywords in _AGENTE_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            return agente
    return None

# Caché de instancias de agentes por sesión
# Clave: lead_id, Valor: instancia del agente
_agent_cache: dict = {}

# ── Cache local de asignación de agente por sesión ─────────────────────────
# Fuente primaria de verdad para routing. El CRM es respaldo persistente.
# Evita que fallas transitorias del CRM rompan la derivación.
_agent_assignments: dict[str, str] = {}  # session_id → agent_name

# Señales de derivación que Valentina incluye en su respuesta
DERIVACION_PATTERN = re.compile(r"\[DERIVAR:\s*(\w+)\s*\]", re.IGNORECASE)

# Señales de agenda — generadas por agentes de ventas
_AGENDA_VV_PATTERN   = re.compile(r"\[AGENDA_VV:([^\]:]+):([^\]]+)\]", re.IGNORECASE)
_LLAMADA_SUP_PATTERN = re.compile(r"\[LLAMADA_SUP:([^\]:]+):([^\]]+)\]", re.IGNORECASE)


def _get_agent_instance(lead_id: str, agent_name: str):
    """
    Obtiene o crea instancia del agente para esta sesión.
    Usa caché para mantener historial de conversación.
    """
    cache_key = f"{lead_id}:{agent_name}"
    if cache_key not in _agent_cache:
        import importlib
        module_path = AGENTES_DISPONIBLES.get(agent_name, "agents.valentina")
        try:
            mod = importlib.import_module(module_path)
            _agent_cache[cache_key] = mod.get_agent()
            logger.info(f"[Router] Agente '{agent_name}' instanciado para lead {lead_id}")
        except Exception as e:
            logger.error(f"[Router] Error instanciando '{agent_name}': {e}")
            # Fallback a Valentina
            from agents.valentina import get_agent
            _agent_cache[cache_key] = get_agent()
    return _agent_cache[cache_key]


def _detectar_derivacion(reply: str) -> str | None:
    """
    Detecta si Valentina indica una derivación en su respuesta.
    Retorna el nombre del nuevo agente o None.
    """
    match = DERIVACION_PATTERN.search(reply)
    if match:
        return match.group(1).lower()
    return None


def _limpiar_señales(reply: str) -> str:
    """Elimina todas las marcas internas de la respuesta final."""
    reply = DERIVACION_PATTERN.sub("", reply)
    reply = _AGENDA_VV_PATTERN.sub("", reply)
    reply = _LLAMADA_SUP_PATTERN.sub("", reply)
    return reply.strip()


async def _procesar_señales_agenda(reply: str, session_id: str, agent_name: str) -> None:
    """
    Detecta [AGENDA_VV:dia:hora] y [LLAMADA_SUP:dia:hora] en la respuesta
    del agente y los registra automáticamente en el CRM.
    """
    from tools import crm_client

    # Videollamada de admisión (financiados)
    m_vv = _AGENDA_VV_PATTERN.search(reply)
    if m_vv:
        dia  = m_vv.group(1).strip()
        hora = m_vv.group(2).strip()
        try:
            lead = await crm_client.get_lead(session_id)
            lead_id = (lead or {}).get("id", session_id)
            result = await crm_client.agendar_videollamada(
                lead_id=lead_id,
                fecha_hora=f"{dia} {hora}",
                tipo="videollamada",
                agente=agent_name,
            )
            logger.info(
                f"[Router] Videollamada agendada para {session_id} "
                f"el {dia} a las {hora} → {result}"
            )
        except Exception as e:
            logger.error(f"[Router] Error agendando VV para {session_id}: {e}")

    # Llamada supervisora (contado)
    m_sup = _LLAMADA_SUP_PATTERN.search(reply)
    if m_sup:
        dia  = m_sup.group(1).strip()
        hora = m_sup.group(2).strip()
        try:
            lead = await crm_client.get_lead(session_id)
            lead_id = (lead or {}).get("id", session_id)
            result = await crm_client.agendar_videollamada(
                lead_id=lead_id,
                fecha_hora=f"{dia} {hora}",
                tipo="llamada_supervisora",
                agente=agent_name,
            )
            logger.info(
                f"[Router] Llamada supervisora agendada para {session_id} "
                f"el {dia} a las {hora} → {result}"
            )
        except Exception as e:
            logger.error(f"[Router] Error agendando llamada sup para {session_id}: {e}")


async def _route_aliados(session_id: str, mensaje: str, msg_type: str) -> dict:
    """
    Maneja todos los mensajes del canal de aliados.
    Si el emisor está en medio del quiz de postulación, procesa la respuesta.
    Caso contrario, Franco atiende la consulta normalmente.
    """
    from tools.franco_quiz import (
        esta_en_quiz, pregunta_actual, registrar_respuesta, marcar_video_recibido,
        calcular_puntaje, armar_resumen_para_rodrigo, limpiar_estado,
        PREGUNTAS, GUION_VIDEO,
    )
    from agents.franco import get_agent as get_franco
    franco = _get_agent_instance(f"aliados:{session_id}", "franco")

    # ── FLUJO QUIZ ──────────────────────────────────────────────────────────
    if esta_en_quiz(session_id):
        preg = pregunta_actual(session_id)

        # El candidato mandó un video/imagen mientras estaba en quiz
        if msg_type == "image" or "video" in mensaje.lower():
            marcar_video_recibido(session_id)
            # Si el quiz ya estaba completo (pregunta_actual > 10) → armar paquete
            from tools.franco_quiz import estado_quiz
            est = estado_quiz(session_id)
            if est and est.get("pregunta_actual", 0) > len(PREGUNTAS):
                return await _finalizar_quiz(session_id, franco)
            return {
                "reply": "¡Video recibido! ✅ Guardame el video, te confirmo cuando tengamos todo.",
                "agent": "franco",
            }

        if preg is None:
            # Quiz completo, esperando video
            if "video" not in mensaje.lower():
                return {
                    "reply": f"Ya respondiste todas las preguntas 🙌 Solo falta el video. "
                             f"{GUION_VIDEO}",
                    "agent": "franco",
                }
            return await _finalizar_quiz(session_id, franco)

        # Registrar respuesta y avanzar
        resultado = registrar_respuesta(session_id, mensaje)
        if resultado["completo"]:
            # Terminó el quiz, pedir video
            return {
                "reply": (
                    "¡Excelente, terminaste el cuestionario! 🎉\n\n"
                    "Ahora solo falta el video de 60 segundos. "
                    "Acordate de la guía que te mandé al principio. "
                    "Cuando lo tengas, mandalo por acá 👇"
                ),
                "agent": "franco",
            }

        # Siguiente pregunta
        siguiente = pregunta_actual(session_id)
        if siguiente:
            return {
                "reply": f"*Pregunta {siguiente['num']} de 10:* {siguiente['texto']}",
                "agent": "franco",
            }

    # ── FRANCO NORMAL ────────────────────────────────────────────────────────
    historial = await crm_client.get_conversation_history(session_id, limit=10)
    contexto = f"Historial previo:\n{historial}" if historial else ""
    reply = await franco.respond(mensaje, contexto)

    await registrar_interaccion(
        session_id=session_id,
        canal="aliados_wa",
        mensaje=mensaje,
        respuesta=reply,
        agente="franco",
    )
    return {"reply": reply, "agent": "franco"}


async def _finalizar_quiz(session_id: str, franco) -> dict:
    """Arma el paquete 🟡 y lo envía a Rodrigo."""
    from tools.franco_quiz import armar_resumen_para_rodrigo, limpiar_estado
    from tools.crm_aliados import log_paquete_auditoria
    from datetime import datetime, timezone

    resumen = armar_resumen_para_rodrigo(session_id)

    # Enviar a Rodrigo por Telegram
    try:
        from channels.telegram_bot import send_alert
        await send_alert(resumen)
    except Exception as e:
        logger.warning(f"[Router] Franco — no se pudo enviar paquete quiz a Rodrigo: {e}")

    # Log de auditoría (sección 8.3)
    await log_paquete_auditoria({
        "tipo": "quiz_postulante",
        "session_id": session_id,
        "contenido": resumen,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resultado": "pendiente",
    })

    limpiar_estado(session_id)

    return {
        "reply": (
            "¡Listo! 🙌 Recibimos tu cuestionario y tu video. "
            "En las próximas 48hs te confirmamos si avanzamos. ¡Gracias!"
        ),
        "agent": "franco",
    }


async def route_message(
    canal: str,
    session_id: str,
    mensaje: str,
    msg_type: str = "text",
) -> dict:
    """
    Punto de entrada principal del router.

    Args:
        canal: "whatsapp" | "whatsapp_admin" | "web" | "telegram"
        session_id: phone_number (WA) o UUID (web widget)
        mensaje: texto del mensaje del cliente
        msg_type: "text" | "audio_transcripto" | "image"

    Returns:
        dict con "reply" (str) y "agent" (str)
    """

    # ── Canal admin: Rodrigo → siempre Máximo ──────────────────────────────
    if canal == "whatsapp_admin" or session_id in ADMIN_WA_PHONES:
        return await _route_admin(session_id, mensaje, msg_type)

    # ── Canal aliados: mensajes del grupo de aliados → Franco ───────────────
    if canal == "aliados_wa":
        return await _route_aliados(session_id, mensaje, msg_type)

    # ── 1. Determinar agente: cache local primero, luego CRM ───────────────
    lead = None
    if session_id in _agent_assignments:
        # Cache hit: ya sabemos qué agente atiende esta sesión
        agent_name = _agent_assignments[session_id]
        # Aun así buscamos el lead para contexto (sin bloqueante si falla)
        try:
            lead = await crm_client.get_lead(session_id)
        except Exception:
            lead = {}
    else:
        # Primera vez: buscar o crear en CRM
        lead = await crm_client.get_lead(session_id)
        if not lead:
            lead = await crm_client.create_lead({
                "session_id": session_id,
                "lead_id": session_id,
                "canal_origen": canal,
                "agente_asignado": "valentina",
                "estado": "nuevo",
            })
            logger.info(f"[Router] Nuevo lead creado: {session_id} via {canal}")
        agent_name = (lead or {}).get("agente_asignado", "valentina").lower()
        _agent_assignments[session_id] = agent_name

    # 2. Obtener historial de los últimos 10 mensajes para contexto
    historial = await crm_client.get_conversation_history(session_id, limit=10)
    contexto = f"Historial previo:\n{historial}" if historial else ""

    # 3. Instanciar agente y generar respuesta
    agente = _get_agent_instance(session_id, agent_name)
    reply = await agente.respond(mensaje, contexto)

    # 4. Detectar señales de derivación (solo aplica cuando hay [DERIVAR:x])
    nuevo_agente = _detectar_derivacion(reply)
    if nuevo_agente and nuevo_agente in AGENTES_DISPONIBLES:
        logger.info(
            f"[Router] Derivación: {agent_name} → {nuevo_agente} para {session_id}"
        )
        # Actualizar cache local PRIMERO (fuente primaria)
        _agent_assignments[session_id] = nuevo_agente
        # Persistir en CRM (best-effort)
        ok = await crm_client.update_lead(session_id, {"agente_asignado": nuevo_agente})
        if not ok:
            logger.warning(f"[Router] CRM update falló para {session_id}, pero cache local OK")

        agent_name = nuevo_agente
        # El nuevo agente responde con el mismo mensaje para tomar el hilo
        nuevo_agente_inst = _get_agent_instance(session_id, nuevo_agente)
        reply = await nuevo_agente_inst.respond(mensaje, contexto)

    # 4b. Procesar señales de agenda (VV y llamada supervisora)
    señales_detectadas = []
    if _AGENDA_VV_PATTERN.search(reply):
        señales_detectadas.append("AGENDA_VV")
    if _LLAMADA_SUP_PATTERN.search(reply):
        señales_detectadas.append("LLAMADA_SUP")
    if nuevo_agente:
        señales_detectadas.append(f"DERIVAR:{nuevo_agente}")
    await _procesar_señales_agenda(reply, session_id, agent_name)

    # Simulador de cuotas exacto: [SIMULAR:tipo:precio] → cálculo real
    try:
        from tools.cuota_sim import procesar_simulaciones
        reply = procesar_simulaciones(reply)
    except Exception:
        pass

    # 4c. Scoring de temperatura + alerta de lead caliente en tiempo real
    try:
        await _evaluar_y_alertar_lead(session_id, mensaje, reply, agent_name, canal)
    except Exception as e:
        logger.warning(f"[Router] scoring lead falló: {e}")

    # Limpiar marcas internas de la respuesta final
    from tools.lead_scoring import limpiar_signal as _limpiar_lead_signal
    reply = _limpiar_lead_signal(reply)
    reply = _limpiar_señales(reply)

    # 5. Guardar conversación en CRM
    await crm_client.save_message(
        lead_id=session_id,
        user_msg=mensaje,
        agent_reply=reply,
        agent_name=agent_name,
        msg_type=msg_type,
    )

    # 5b. Registro de auditoría
    registrar_interaccion(
        canal=canal,
        session_id=session_id,
        agente=agent_name,
        mensaje_usuario=mensaje,
        respuesta_agente=reply,
        señales=señales_detectadas if señales_detectadas else None,
        derivacion_a=nuevo_agente,
        msg_type=msg_type,
    )

    # 6. Notificar a Tomás — solo si está explícitamente habilitado
    # (deshabilitado por defecto para no duplicar llamadas a la API en producción)
    if os.getenv("TOMAS_SUPERVISION", "off").lower() == "on":
        if canal in ("whatsapp", "web") and agent_name in (
            "valentina", "camila", "mateo", "nicolas", "luciano"
        ):
            await _notificar_tomas(session_id, agent_name, mensaje, reply)

    return {
        "reply": reply,
        "agent": agent_name,
        "lead_id": session_id,
    }


async def _route_admin(session_id: str, mensaje: str, msg_type: str) -> dict:
    """
    Canal privado de Rodrigo (admin).
    Por defecto atiende Máximo, pero Rodrigo puede hablar con CUALQUIER agente.
    El agente activo se persiste en _agent_assignments["admin_rodrigo"].
    Para volver a Máximo: "pasame con Máximo" / "volvé a Máximo".
    """
    msg_lower = mensaje.lower().strip()

    # ── 1. Volver a Máximo ───────────────────────────────────────────────────
    _VOLVER_MAXIMO = ["volvé a máximo", "pasame con máximo", "quiero hablar con máximo",
                      "llamá a máximo", "volver a maximo", "maximo por favor"]
    if any(k in msg_lower for k in _VOLVER_MAXIMO):
        _agent_assignments["admin_rodrigo"] = "maximo"

    # ── 2. Cambio explícito a otro agente (detección directa del texto) ──────
    # Esto evita que el modelo de IA (Groq/Llama en fallback) confunda nombres.
    else:
        switch_target = _detectar_switch_agente(msg_lower)
        if switch_target:
            logger.info(f"[Router/Admin] Switch directo detectado → {switch_target}")
            _agent_assignments["admin_rodrigo"] = switch_target

    agente_actual = _agent_assignments.get("admin_rodrigo", "maximo")

    historial = await crm_client.get_conversation_history("admin_rodrigo", limit=15)
    contexto = f"Historial:\n{historial}" if historial else ""

    agente_inst = _get_agent_instance("admin_rodrigo", agente_actual)
    reply = await agente_inst.respond(mensaje, contexto)

    # Detectar si el agente activo quiere derivar a otro
    nuevo_agente = _detectar_derivacion(reply)
    if nuevo_agente and nuevo_agente in AGENTES_DISPONIBLES:
        transicion = _limpiar_señales(reply).strip()
        transicion = limpiar_acciones(transicion)
        _agent_assignments["admin_rodrigo"] = nuevo_agente

        nuevo_inst = _get_agent_instance("admin_rodrigo", nuevo_agente)
        reply_nuevo = await nuevo_inst.respond(mensaje, contexto)
        reply_nuevo = _limpiar_señales(reply_nuevo)

        # Detectar acciones CRM en la respuesta de transición (improbable pero posible)
        acciones_transicion = detectar_acciones(reply)
        if acciones_transicion:
            resultados = await ejecutar_acciones(acciones_transicion)
            if resultados:
                transicion = f"{transicion}\n\n{resultados}".strip()

        # Mostrar mensaje de transición + respuesta del nuevo agente
        reply_final = f"{transicion}\n\n{reply_nuevo}".strip() if transicion else reply_nuevo

        await crm_client.save_message(
            lead_id="admin_rodrigo",
            user_msg=mensaje,
            agent_reply=reply_final,
            agent_name=nuevo_agente,
            msg_type=msg_type,
        )
        registrar_interaccion(
            canal="whatsapp_admin",
            session_id="admin_rodrigo",
            agente=nuevo_agente,
            mensaje_usuario=mensaje,
            respuesta_agente=reply_final,
            señales=[f"DERIVAR:{nuevo_agente}"],
            derivacion_a=nuevo_agente,
            msg_type=msg_type,
        )
        return {"reply": reply_final, "agent": nuevo_agente, "lead_id": "admin_rodrigo"}

    reply = _limpiar_señales(reply)

    # ── Detectar y ejecutar acciones CRM (solo canal admin) ──────────────────
    acciones = detectar_acciones(reply)
    reply = limpiar_acciones(reply)
    acciones_nombres = [a.get("tipo", "crm_action") for a in acciones] if acciones else []
    if acciones:
        resultados = await ejecutar_acciones(acciones)
        if resultados:
            reply = f"{reply}\n\n{resultados}".strip()

    await crm_client.save_message(
        lead_id="admin_rodrigo",
        user_msg=mensaje,
        agent_reply=reply,
        agent_name=agente_actual,
        msg_type=msg_type,
    )
    registrar_interaccion(
        canal="whatsapp_admin",
        session_id="admin_rodrigo",
        agente=agente_actual,
        mensaje_usuario=mensaje,
        respuesta_agente=reply,
        acciones_crm=acciones_nombres if acciones_nombres else None,
        msg_type=msg_type,
    )
    return {"reply": reply, "agent": agente_actual, "lead_id": "admin_rodrigo"}


async def _notificar_tomas(
    lead_id: str, agent_name: str, user_msg: str, reply: str
):
    """
    Envía contexto de la conversación a Tomás para supervisión.
    No bloquea el flujo si falla.
    """
    try:
        tomas = _get_agent_instance("tomas_supervisor", "tomas")
        resumen = (
            f"Conversación activa — Lead {lead_id} con {agent_name}.\n"
            f"Cliente: {user_msg[:200]}\n"
            f"Agente: {reply[:200]}"
        )
        await tomas.respond(
            f"MONITOREO: {resumen}",
            "Sos el supervisor. Registrá esta interacción y alertá si es necesario.",
        )
    except Exception as e:
        logger.warning(f"[Router] No se pudo notificar a Tomás: {e}")


def clear_agent_cache(lead_id: str | None = None):
    """
    Limpia la caché de agentes.
    Si se pasa lead_id, solo limpia ese lead.
    """
    global _agent_cache, _agent_assignments
    if lead_id:
        keys_to_remove = [k for k in _agent_cache if k.startswith(f"{lead_id}:")]
        for k in keys_to_remove:
            del _agent_cache[k]
        _agent_assignments.pop(lead_id, None)
    else:
        _agent_cache.clear()
        _agent_assignments.clear()
