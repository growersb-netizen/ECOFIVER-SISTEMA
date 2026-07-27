"""
Bot de Telegram — EcoFiver IA
Control total del sistema multiagente por conversación natural.
Solo responde al CHAT_ID configurado en env (Rodrigo / dueño).
"""

import os
import re
import logging
import importlib
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
from tools import crm_client
from tools.audio_transcriber import transcribir_bytes
from tools.vision import extraer_datos_documento

load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
try:
    TELEGRAM_CHAT_ID_RODRIGO = int(os.getenv("TELEGRAM_CHAT_ID_RODRIGO", "0"))
except ValueError:
    TELEGRAM_CHAT_ID_RODRIGO = 0

_app: Application | None = None

# ── Patrón de derivación ────────────────────────────────────────────────────
_DERIVAR_RE = re.compile(r"\[DERIVAR:(\w+)\]", re.IGNORECASE)

# Limpia cualquier señal interna que se filtre al texto visible si algo falla
# (misma red de seguridad que usa el panel de pruebas — ver agent_panel.py).
_SIGNAL_LEAK_RE = re.compile(
    r"\[(?:LLAMADA_SUP|AGENDA_VV|DERIVAR|ALERTA|NOTIF|SEGUIMIENTO|LEAD_CALIENTE|SIMULAR)[^\]]*\]",
    re.IGNORECASE,
)


async def _post_procesar_reply(reply: str) -> str:
    """
    Ejecuta acciones CRM reales ([CRM_ACTION:...]) y sustituye el simulador de
    cuotas ([SIMULAR:...]) por el cálculo real — el mismo post-procesamiento
    que aplica orchestrator/router.py, pero este bot habla directo con el
    agente (agente.respond()) sin pasar por el router, así que antes ninguna
    acción real se ejecutaba ni el simulador se sustituía en este canal.
    """
    from tools.crm_actions import detectar_acciones, limpiar_acciones, ejecutar_acciones

    acciones = detectar_acciones(reply)
    resultado_acciones = ""
    if acciones:
        try:
            resultado_acciones = await ejecutar_acciones(acciones)
            logger.info(f"[TG] Acciones ejecutadas: {[a.get('tipo','?') for a in acciones]}")
        except Exception as e:
            logger.error(f"[TG] Error ejecutando acciones CRM: {e}")
            resultado_acciones = f"⚠️ Error al ejecutar la acción: {e}"

    try:
        from tools.cuota_sim import procesar_simulaciones
        reply = procesar_simulaciones(reply)
    except Exception:
        pass

    reply = limpiar_acciones(reply)
    reply = _SIGNAL_LEAK_RE.sub("", reply).strip()
    if resultado_acciones:
        reply = f"{reply}\n\n{resultado_acciones}".strip()
    return reply


# ── Catálogo de agentes ─────────────────────────────────────────────────────

AGENTS_CONFIG = {
    "maximo":    {"nombre": "Máximo",           "emoji": "👑", "modulo": "agents.maximo",    "desc": "CEO · Director Operativo"},
    "aurora":    {"nombre": "Aurora",            "emoji": "📊", "modulo": "agents.aurora",    "desc": "Gerente Comercial"},
    "tomas":     {"nombre": "Tomás",             "emoji": "👀", "modulo": "agents.tomas",     "desc": "Supervisor de Ventas"},
    "valentina": {"nombre": "Valentina",         "emoji": "💬", "modulo": "agents.valentina", "desc": "Primer Contacto · WA/Web"},
    "camila":    {"nombre": "Camila",            "emoji": "🌊", "modulo": "agents.camila",    "desc": "Piscinas Contado"},
    "mateo":     {"nombre": "Mateo",             "emoji": "🏗️", "modulo": "agents.mateo",     "desc": "Módulos Financiados"},
    "nicolas":   {"nombre": "Nicolás",           "emoji": "📋", "modulo": "agents.nicolas",   "desc": "Piscinas Financiadas"},
    "luciano":   {"nombre": "Luciano",           "emoji": "🏠", "modulo": "agents.luciano",   "desc": "Módulos Contado · Combos"},
    "renata":    {"nombre": "Renata",            "emoji": "🎨", "modulo": "agents.renata",    "desc": "Marketing · Contenido · Web"},
    "bruno":     {"nombre": "Bruno",             "emoji": "🚛", "modulo": "agents.bruno",     "desc": "Operaciones · Logística"},
    "ezequiel":  {"nombre": "Ezequiel",          "emoji": "📂", "modulo": "agents.ezequiel",  "desc": "Administración · Contratos"},
    "ignacio":   {"nombre": "Ignacio",           "emoji": "💳", "modulo": "agents.ignacio",   "desc": "Cobrador · Cuotas"},
    "elena":     {"nombre": "Elena",             "emoji": "💹", "modulo": "agents.elena",     "desc": "Finanzas · CRM"},
    "daniela":   {"nombre": "Daniela",           "emoji": "🛡️", "modulo": "agents.daniela",   "desc": "RRPP · Crisis"},
    "sebastian": {"nombre": "Sebastián",         "emoji": "🔧", "modulo": "agents.sebastian", "desc": "Postventa · Soporte Técnico"},
    "valentin":  {"nombre": "Dr. Valentín Ríos", "emoji": "🧠", "modulo": "agents.valentin",  "desc": "Terapeuta Personal · Privado"},
}

# Aliases en lenguaje natural para detectar cambios de agente
AGENT_ALIASES: dict[str, list[str]] = {
    "maximo":    ["máximo", "maximo", "ceo", "director"],
    "aurora":    ["aurora"],
    "tomas":     ["tomás", "tomas"],
    "valentina": ["valentina"],
    "camila":    ["camila"],
    "mateo":     ["mateo"],
    "nicolas":   ["nicolás", "nicolas"],
    "luciano":   ["luciano"],
    "renata":    ["renata"],
    "bruno":     ["bruno"],
    "ezequiel":  ["ezequiel"],
    "ignacio":   ["ignacio"],
    "elena":     ["elena"],
    "daniela":   ["daniela"],
    "sebastian": ["sebastián", "sebastian", "seba"],
    "valentin":  ["valentín", "valentin", "dr. ríos", "dr ríos", "doctor ríos",
                  "doctor", "el doctor", "el terapeuta", "terapeuta"],
}

# Frases que indican cambio de agente
_SWITCH_PATTERNS = [
    r"llamá a (.+)",
    r"llama a (.+)",
    r"pasame con (.+)",
    r"pasáme con (.+)",
    r"quiero hablar con (.+)",
    r"necesito hablar con (.+)",
    r"conectame con (.+)",
    r"conectáme con (.+)",
    r"dame a (.+)",
    r"hablame con (.+)",
    r"hábla?me con (.+)",
    r"activá a (.+)",
    r"activa a (.+)",
    r"buscá a (.+)",
    r"busca a (.+)",
    r"llamá al (.+)",
    r"quiero a (.+)",
    r"necesito a (.+)",
    r"convocá a (.+)",
    r"tráeme a (.+)",
    r"traeme a (.+)",
]


# ── Estado de sesiones ──────────────────────────────────────────────────────
# { chat_id: {"agent": "maximo", "history": [...], "instance": <obj>} }
_sessions: dict[int, dict] = {}


def _get_session(chat_id: int) -> dict:
    if chat_id not in _sessions:
        _sessions[chat_id] = {
            "agent":       "maximo",
            "history":     [],
            "instance":    None,
            "dni_pendiente": None,  # dict con datos extraídos de la última foto de DNI, sin confirmar
        }
    return _sessions[chat_id]


def _instanciar_agente(agent_key: str):
    cfg    = AGENTS_CONFIG[agent_key]
    mod    = importlib.import_module(cfg["modulo"])
    return mod.get_agent()


def _switch_agent(chat_id: int, nuevo_agente: str, conservar_historial: bool = False) -> dict:
    """Cambia el agente activo de una sesión. Devuelve la sesión actualizada."""
    sess = _get_session(chat_id)
    sess["agent"]    = nuevo_agente
    sess["instance"] = _instanciar_agente(nuevo_agente)
    if not conservar_historial:
        sess["history"] = []
    else:
        sess["instance"].history = sess["history"]
    return sess


def _detectar_cambio_agente_nlp(texto: str) -> str | None:
    """
    Detecta si Rodo está pidiendo cambiar de agente en lenguaje natural.
    Devuelve la clave del agente destino o None.
    """
    texto_lower = texto.lower().strip()
    for pattern in _SWITCH_PATTERNS:
        m = re.search(pattern, texto_lower)
        if m:
            fragmento = m.group(1).strip().rstrip(".,!?")
            for key, aliases in AGENT_ALIASES.items():
                for alias in aliases:
                    if alias in fragmento:
                        return key
    return None


async def _responder_agente(
    update: Update,
    chat_id: int,
    mensaje: str,
    contexto: str = "",
) -> None:
    """
    Envía el mensaje al agente activo, detecta derivaciones,
    cambia de agente si corresponde y responde en Telegram.
    """
    sess = _get_session(chat_id)
    agent_key = sess["agent"]

    if not sess["instance"]:
        sess["instance"] = _instanciar_agente(agent_key)
        sess["instance"].history = sess["history"]

    # Si hay datos de un DNI recién escaneado sin confirmar, se los sumamos
    # al contexto para que el agente (Máximo) pueda usarlos si Rodrigo los
    # confirma o pide emitir el contrato con esos datos.
    if sess.get("dni_pendiente"):
        import json as _json
        contexto = (
            f"[DNI ESCANEADO, PENDIENTE DE CONFIRMACIÓN — no lo uses hasta que Rodrigo lo confirme]\n"
            f"{_json.dumps(sess['dni_pendiente'], ensure_ascii=False)}\n\n{contexto}"
        )

    await _app.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        agente = sess["instance"]
        agente.history = sess["history"]
        reply = await agente.respond(mensaje, contexto)
    except Exception as e:
        logger.error(f"[TG] Error agente {agent_key}: {e}")
        await update.message.reply_text(f"❌ No pude conectar con {AGENTS_CONFIG[agent_key]['nombre']}: {e}")
        return

    # ── Detectar derivación en la respuesta ─────────────────────────────
    match = _DERIVAR_RE.search(reply)
    if match:
        nuevo_key = match.group(1).lower()
        if nuevo_key in AGENTS_CONFIG:
            # Mensaje de transición de Valentina/Máximo antes del salto
            transicion = _DERIVAR_RE.sub("", reply).strip()
            if transicion:
                cfg_from = AGENTS_CONFIG[agent_key]
                await update.message.reply_text(
                    f"{cfg_from['emoji']} {cfg_from['nombre']}:\n\n{transicion}"
                )

            # Actualizar sesión y convocar al nuevo agente
            sess = _switch_agent(chat_id, nuevo_key, conservar_historial=False)
            cfg_to = AGENTS_CONFIG[nuevo_key]

            await update.message.reply_text(
                f"🔀 Estás hablando con {cfg_to['emoji']} {cfg_to['nombre']}."
            )
            await _app.bot.send_chat_action(chat_id=chat_id, action="typing")

            try:
                nuevo_agente = sess["instance"]
                reply = await nuevo_agente.respond(mensaje)
            except Exception as e:
                await update.message.reply_text(f"❌ No pude conectar con {cfg_to['nombre']}: {e}")
                return

            # Limpiar marcas, ejecutar acciones reales y enviar respuesta del nuevo agente
            reply = await _post_procesar_reply(_DERIVAR_RE.sub("", reply).strip())
            sess["history"].append({"role": "user",      "content": mensaje})
            sess["history"].append({"role": "assistant",  "content": reply})
            if len(sess["history"]) > 80:
                sess["history"] = sess["history"][-80:]

            cfg = AGENTS_CONFIG[nuevo_key]
            await update.message.reply_text(f"{cfg['emoji']} {cfg['nombre']}:\n\n{reply}")
            return

    # ── Sin derivación: respuesta normal ────────────────────────────────
    reply = await _post_procesar_reply(_DERIVAR_RE.sub("", reply).strip())

    sess["history"].append({"role": "user",      "content": mensaje})
    sess["history"].append({"role": "assistant",  "content": reply})
    if len(sess["history"]) > 80:
        sess["history"] = sess["history"][-80:]

    cfg = AGENTS_CONFIG[agent_key]
    await update.message.reply_text(f"{cfg['emoji']} {cfg['nombre']}:\n\n{reply}")


# ── DECORADOR DE SEGURIDAD ──────────────────────────────────────────────────

def solo_rodrigo(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != TELEGRAM_CHAT_ID_RODRIGO:
            logger.warning(f"[TG] Acceso denegado chat_id={update.effective_chat.id}")
            return
        return await func(update, context)
    return wrapper


# ── HANDLER PRINCIPAL DE MENSAJES ──────────────────────────────────────────

@solo_rodrigo
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja todos los mensajes de texto libres.
    Detecta cambios de agente en lenguaje natural, instrucciones múltiples,
    y enruta la conversación al agente activo.
    """
    chat_id = update.effective_chat.id
    texto   = update.message.text.strip()

    # Detectar si pide cambiar de agente en lenguaje natural
    nuevo = _detectar_cambio_agente_nlp(texto)
    if nuevo:
        sess  = _switch_agent(chat_id, nuevo, conservar_historial=False)
        cfg   = AGENTS_CONFIG[nuevo]
        await update.message.reply_text(
            f"🔀 Cambiando a {cfg['emoji']} {cfg['nombre']} — {cfg['desc']}."
        )
        # El agente nuevo saluda o responde al contexto del pedido
        await _responder_agente(update, chat_id, texto)
        return

    await _responder_agente(update, chat_id, texto)


# ── HANDLER DE MENSAJES DE VOZ / AUDIO ─────────────────────────────────────

@solo_rodrigo
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja mensajes de voz y archivos de audio enviados en Telegram.
    Transcribe el audio a texto y lo envía al agente activo.
    """
    chat_id = update.effective_chat.id

    # Obtener el objeto de audio (voz o archivo de audio)
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await _app.bot.send_chat_action(chat_id=chat_id, action="typing")
    await update.message.reply_text("🎙 Transcribiendo audio...")

    try:
        # Descargar el archivo de audio desde Telegram
        file_obj = await context.bot.get_file(voice.file_id)
        audio_bytes = await file_obj.download_as_bytearray()

        # Determinar MIME type
        if update.message.audio and update.message.audio.mime_type:
            mime = update.message.audio.mime_type
        else:
            mime = "audio/ogg"  # Telegram voice notes son OGG/Opus

        texto = await transcribir_bytes(bytes(audio_bytes), mime_type=mime)

        logger.info(f"[TG] Audio transcripto: {texto[:80]}...")

        # Mostrar la transcripción y enviar al agente
        await update.message.reply_text(f"📝 Transcripción: _{texto}_", parse_mode="Markdown")

        # Procesar con el agente activo
        await _responder_agente(update, chat_id, texto)

    except Exception as e:
        logger.error(f"[TG] Error procesando audio: {e}")
        await update.message.reply_text(f"❌ No pude procesar el audio: {e}")


# ── HANDLER DE FOTOS (lectura de DNI) ───────────────────────────────────────

@solo_rodrigo
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lee un documento (DNI) enviado por foto usando visión real, muestra los
    datos extraídos para que Rodrigo los confirme antes de usarlos, y los
    deja disponibles en la sesión (dni_pendiente) para que Máximo pueda
    emitir el contrato una vez confirmados.
    """
    chat_id = update.effective_chat.id
    if not update.message.photo:
        return

    await _app.bot.send_chat_action(chat_id=chat_id, action="typing")
    await update.message.reply_text("📄 Leyendo el documento...")

    try:
        foto = update.message.photo[-1]  # la de mayor resolución
        file_obj = await context.bot.get_file(foto.file_id)
        image_bytes = await file_obj.download_as_bytearray()

        datos = await extraer_datos_documento(bytes(image_bytes), "image/jpeg")

        if datos.get("error"):
            await update.message.reply_text(f"❌ No pude leer el documento: {datos['error']}")
            return

        sess = _get_session(chat_id)
        sess["dni_pendiente"] = datos

        campos = [
            ("Nombre", datos.get("nombre")),
            ("Apellido", datos.get("apellido")),
            ("DNI", datos.get("dni")),
            ("Fecha de nacimiento", datos.get("fecha_nacimiento")),
            ("Domicilio", datos.get("domicilio")),
            ("Lugar de nacimiento", datos.get("lugar_nacimiento")),
        ]
        lineas = [f"📄 *Datos leídos* (confianza: {datos.get('confianza','?')}):", ""]
        for etiqueta, valor in campos:
            lineas.append(f"• {etiqueta}: {valor if valor else '_no legible_'}")
        lineas.append("")
        lineas.append("¿Están bien? Confirmame o corregime lo que esté mal antes de usarlos para el contrato.")

        await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"[TG] Error procesando foto de documento: {e}")
        await update.message.reply_text(f"❌ No pude procesar la foto: {e}")


# ── COMANDOS POR AGENTE ─────────────────────────────────────────────────────

def _make_agent_cmd(agent_key: str):
    """Genera un handler de comando para un agente específico."""
    @solo_rodrigo
    async def _cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id  = update.effective_chat.id
        cfg      = AGENTS_CONFIG[agent_key]
        args_txt = " ".join(context.args) if context.args else ""

        sess = _switch_agent(chat_id, agent_key, conservar_historial=False)
        await update.message.reply_text(
            f"{cfg['emoji']} Conectando con {cfg['nombre']} — {cfg['desc']}..."
        )

        if args_txt:
            # Si viene texto inline con el comando, lo envía directamente
            await _responder_agente(update, chat_id, args_txt)
        else:
            # Sin args: el agente saluda
            await _responder_agente(update, chat_id, "Hola, estoy aquí.")

    _cmd.__name__ = f"cmd_{agent_key}"
    return _cmd


# Generamos todos los handlers de agentes
_agent_handlers = {key: _make_agent_cmd(key) for key in AGENTS_CONFIG}


# ── COMANDOS DE SESIÓN ──────────────────────────────────────────────────────

@solo_rodrigo
async def cmd_sesion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra con qué agente estás hablando ahora."""
    chat_id = update.effective_chat.id
    sess    = _get_session(chat_id)
    key     = sess["agent"]
    cfg     = AGENTS_CONFIG[key]
    turnos  = len(sess["history"]) // 2
    await update.message.reply_text(
        f"💬 Estás hablando con: {cfg['emoji']} {cfg['nombre']}\n"
        f"Rol: {cfg['desc']}\n"
        f"Turnos en esta sesión: {turnos}"
    )


@solo_rodrigo
async def cmd_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Limpia el historial de la conversación actual."""
    chat_id = update.effective_chat.id
    sess    = _get_session(chat_id)
    sess["history"] = []
    if sess["instance"]:
        sess["instance"].history = []
    key = sess["agent"]
    cfg = AGENTS_CONFIG[key]
    await update.message.reply_text(
        f"🗑 Historial limpiado. Seguís con {cfg['emoji']} {cfg['nombre']}."
    )


@solo_rodrigo
async def cmd_agentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos los agentes disponibles con su comando."""
    lines = ["👥 EQUIPO ECOFIVER IA\n"]
    for key, cfg in AGENTS_CONFIG.items():
        lines.append(f"{cfg['emoji']} /{key} — {cfg['nombre']} · {cfg['desc']}")
    lines.append("\nTambién podés pedirme directamente: 'llamá a Camila', 'necesito hablar con Valentín', etc.")
    await update.message.reply_text("\n".join(lines))


# ── COMANDOS OPERATIVOS ─────────────────────────────────────────────────────

@solo_rodrigo
async def cmd_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("📊 Generando reporte ejecutivo...")
    try:
        stats  = await crm_client.get_pipeline_stats()
        ventas = await crm_client.get_ventas_hoy()
        cuotas = await crm_client.get_cuotas_vencidas(1)
        contexto = (
            f"Pipeline: {stats}\nVentas hoy: {ventas}\n"
            f"Cuotas vencidas: {len(cuotas)}"
        )
        await _responder_agente(update, chat_id,
            "Generá el reporte diario completo con los datos disponibles.",
            contexto)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@solo_rodrigo
async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Consultando leads activos...")
    try:
        leads = await crm_client.get_leads_sin_respuesta(0)
        if not leads:
            await update.message.reply_text("✅ Sin leads pendientes ahora.")
            return
        lines = [f"📋 LEADS ACTIVOS ({len(leads)}):\n"]
        for lead in leads[:20]:
            lines.append(
                f"• {lead.get('nombre','Sin nombre')} — "
                f"{lead.get('canal','WA')} — "
                f"Agente: {lead.get('agente_asignado','?')}"
            )
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@solo_rodrigo
async def cmd_cierres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ventas = await crm_client.get_ventas_hoy()
        await update.message.reply_text(
            f"💰 CIERRES HOY:\n\n"
            f"Cantidad: {ventas.get('cierres', 0)}\n"
            f"Monto: ${ventas.get('monto_total', 0):,.0f}\n"
            f"Leads nuevos: {ventas.get('leads_nuevos', 0)}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@solo_rodrigo
async def cmd_cuotas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cuotas = await crm_client.get_cuotas_vencidas(1)
        if not cuotas:
            await update.message.reply_text("✅ Sin cuotas vencidas.")
            return
        lines = [f"⚠️ CUOTAS VENCIDAS: {len(cuotas)}\n"]
        for c in cuotas[:15]:
            lines.append(
                f"• {c.get('cliente','?')} — "
                f"${c.get('monto',0):,.0f} — "
                f"{c.get('dias_vencido',0)} días"
            )
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@solo_rodrigo
async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock = await crm_client.get_stock()
        if not stock:
            await update.message.reply_text("ℹ️ Sin datos de stock disponibles.")
            return
        lines = ["📦 ESTADO DE STOCK:\n"]
        for producto, cantidad in stock.items():
            emoji = "🔴" if cantidad == 0 else "🟡" if cantidad <= 3 else "🟢"
            lines.append(f"{emoji} {producto}: {cantidad} unidades")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@solo_rodrigo
async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stats = await crm_client.get_pipeline_stats()
        chat_id = update.effective_chat.id
        sess    = _get_session(chat_id)
        key     = sess["agent"]
        cfg     = AGENTS_CONFIG[key]
        await update.message.reply_text(
            f"🤖 SISTEMA ECOFIVER IA\n\n"
            f"Agentes activos: 16\n"
            f"Leads hoy: {stats.get('leads_recibidos', 0)}\n"
            f"Cierres hoy: {stats.get('cierres_contado', 0)}\n"
            f"Videollamadas: {stats.get('videollamadas', 0)}\n"
            f"Cuotas vencidas: {stats.get('cuotas_vencidas', 0)}\n"
            f"Leads desde web: {stats.get('leads_web', 0)}\n\n"
            f"Hablando con: {cfg['emoji']} {cfg['nombre']}\n"
            f"Sistema operativo. ✅"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@solo_rodrigo
async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🤖 ECOFIVER IA — Sistema de agentes\n\n"
        "CONVERSACIÓN LIBRE:\n"
        "Escribí directamente y el agente activo te responde.\n"
        "Pedí cambios en lenguaje natural:\n"
        "  'llamá a Camila', 'pasame con Valentín', 'necesito a Bruno'\n\n"

        "CONVOCAR AGENTES:\n"
        "/maximo — 👑 Máximo (CEO)\n"
        "/aurora — 📊 Aurora (Gerente Comercial)\n"
        "/tomas — 👀 Tomás (Supervisor Ventas)\n"
        "/valentina — 💬 Valentina (Primer Contacto)\n"
        "/camila — 🌊 Camila (Piscinas Contado)\n"
        "/mateo — 🏗️ Mateo (Módulos Financiados)\n"
        "/nicolas — 📋 Nicolás (Piscinas Financiadas)\n"
        "/luciano — 🏠 Luciano (Módulos Contado)\n"
        "/renata — 🎨 Renata (Marketing)\n"
        "/bruno — 🚛 Bruno (Operaciones)\n"
        "/ezequiel — 📂 Ezequiel (Administración)\n"
        "/ignacio — 💳 Ignacio (Cobrador)\n"
        "/elena — 💹 Elena (Finanzas)\n"
        "/daniela — 🛡️ Daniela (RRPP y Crisis)\n"
        "/sebastian — 🔧 Sebastián (Postventa)\n"
        "/valentin — 🧠 Dr. Valentín Ríos (Terapeuta)\n\n"

        "SESIÓN:\n"
        "/sesion — Ver agente activo\n"
        "/nuevo — Limpiar historial\n"
        "/agentes — Lista completa\n\n"

        "OPERATIVOS:\n"
        "/reporte — Reporte ejecutivo\n"
        "/leads — Leads activos\n"
        "/cierres — Ventas del día\n"
        "/cuotas — Cuotas vencidas\n"
        "/stock — Estado de stock\n"
        "/estado — Estado del sistema\n"
        "/ayuda — Esta ayuda"
    )
    await update.message.reply_text(texto)


# ── REPORTE DIARIO AUTOMÁTICO ───────────────────────────────────────────────

async def send_daily_report():
    """Genera y envía el reporte diario de Máximo. Llamado por el scheduler."""
    if not _app or not TELEGRAM_CHAT_ID_RODRIGO:
        logger.warning("[TG] send_daily_report: app no inicializada o chat_id no configurado")
        return
    try:
        mod    = importlib.import_module("agents.maximo")
        maximo = mod.get_agent()
        stats  = await crm_client.get_pipeline_stats()
        ventas = await crm_client.get_ventas_hoy()
        cuotas = await crm_client.get_cuotas_vencidas(1)
        contexto = (
            f"Pipeline: {stats}\nVentas hoy: {ventas}\n"
            f"Cuotas vencidas: {len(cuotas)}"
        )
        reporte = await maximo.respond(
            "Generá el reporte diario de las 08:00 AM para Rodrigo. "
            "Usá el formato exacto del reporte diario.",
            contexto,
        )
        await _app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID_RODRIGO,
            text=f"👑 Máximo:\n\n{reporte}",
        )
        logger.info("[TG] Reporte diario enviado.")
    except Exception as e:
        logger.error(f"[TG] Error enviando reporte: {e}")


async def send_alert(text: str):
    """Envía alerta a Rodrigo."""
    if not _app or not TELEGRAM_CHAT_ID_RODRIGO:
        return
    try:
        await _app.bot.send_message(chat_id=TELEGRAM_CHAT_ID_RODRIGO, text=text)
    except Exception as e:
        logger.error(f"[TG] Error enviando alerta: {e}")


async def send_to_aliados_wa(text: str) -> bool:
    """
    Envía un mensaje al número del canal de aliados (FRANCO_WHATSAPP_NUMBER).
    Usado por las tareas del scheduler (material lunes, caso ganado, ranking).
    El número destino es el propio canal/grupo de aliados en WhatsApp.
    """
    import os
    franco_wa = os.getenv("FRANCO_WHATSAPP_NUMBER", "")
    if not franco_wa:
        logger.warning("[TG/Aliados] FRANCO_WHATSAPP_NUMBER no configurado — mensaje no enviado")
        return False
    try:
        from channels.whatsapp import enviar_mensaje_wa
        ok = await enviar_mensaje_wa(franco_wa, text, phone_id=franco_wa)
        return ok
    except Exception as e:
        logger.error(f"[TG/Aliados] send_to_aliados_wa error: {e}")
        return False


# ── INICIALIZACIÓN ──────────────────────────────────────────────────────────

async def start_telegram():
    """Inicializa y arranca el bot en modo polling."""
    global _app

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("[TG] TELEGRAM_BOT_TOKEN no configurado — bot desactivado.")
        return

    _app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Comandos por agente ──────────────────────────────────────────────
    for key, handler_fn in _agent_handlers.items():
        _app.add_handler(CommandHandler(key, handler_fn))

    # ── Comandos de sesión ───────────────────────────────────────────────
    _app.add_handler(CommandHandler("sesion",  cmd_sesion))
    _app.add_handler(CommandHandler("nuevo",   cmd_nuevo))
    _app.add_handler(CommandHandler("agentes", cmd_agentes))

    # ── Comandos operativos ──────────────────────────────────────────────
    _app.add_handler(CommandHandler("reporte", cmd_reporte))
    _app.add_handler(CommandHandler("leads",   cmd_leads))
    _app.add_handler(CommandHandler("cierres", cmd_cierres))
    _app.add_handler(CommandHandler("cuotas",  cmd_cuotas))
    _app.add_handler(CommandHandler("stock",   cmd_stock))
    _app.add_handler(CommandHandler("estado",  cmd_estado))
    _app.add_handler(CommandHandler("ayuda",   cmd_ayuda))
    _app.add_handler(CommandHandler("start",   cmd_ayuda))
    _app.add_handler(CommandHandler("help",    cmd_ayuda))

    # ── Handler de mensajes libres (conversación natural) ────────────────
    _app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # ── Handler de mensajes de voz y audio ───────────────────────────────
    _app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice)
    )

    # ── Handler de fotos (lectura de DNI) ─────────────────────────────────
    _app.add_handler(
        MessageHandler(filters.PHOTO, handle_photo)
    )

    # ── Registrar lista de comandos en Telegram (menú de autocompletado) ─
    bot_commands = [
        BotCommand("maximo",    "👑 Hablar con Máximo (CEO)"),
        BotCommand("aurora",    "📊 Hablar con Aurora (Gerente Comercial)"),
        BotCommand("tomas",     "👀 Hablar con Tomás (Supervisor Ventas)"),
        BotCommand("valentina", "💬 Hablar con Valentina (Primer Contacto)"),
        BotCommand("camila",    "🌊 Hablar con Camila (Piscinas Contado)"),
        BotCommand("mateo",     "🏗 Hablar con Mateo (Módulos Financiados)"),
        BotCommand("nicolas",   "📋 Hablar con Nicolás (Piscinas Financiadas)"),
        BotCommand("luciano",   "🏠 Hablar con Luciano (Módulos Contado)"),
        BotCommand("renata",    "🎨 Hablar con Renata (Marketing)"),
        BotCommand("bruno",     "🚛 Hablar con Bruno (Logística)"),
        BotCommand("ezequiel",  "📂 Hablar con Ezequiel (Administración)"),
        BotCommand("ignacio",   "💳 Hablar con Ignacio (Cobrador)"),
        BotCommand("elena",     "💹 Hablar con Elena (Finanzas)"),
        BotCommand("daniela",   "🛡 Hablar con Daniela (RRPP y Crisis)"),
        BotCommand("sebastian", "🔧 Hablar con Sebastián (Postventa)"),
        BotCommand("valentin",  "🧠 Sesión con Dr. Valentín Ríos"),
        BotCommand("sesion",    "Ver agente activo"),
        BotCommand("nuevo",     "Limpiar historial de conversación"),
        BotCommand("agentes",   "Lista completa de agentes"),
        BotCommand("reporte",   "Reporte ejecutivo del día"),
        BotCommand("leads",     "Leads activos ahora"),
        BotCommand("cierres",   "Ventas del día"),
        BotCommand("cuotas",    "Cuotas vencidas"),
        BotCommand("stock",     "Estado de stock"),
        BotCommand("estado",    "Estado general del sistema"),
        BotCommand("ayuda",     "Lista de comandos"),
    ]
    await _app.bot.set_my_commands(bot_commands)

    logger.info("[TG] Bot de Telegram iniciado — 16 agentes + conversación natural.")

    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)
