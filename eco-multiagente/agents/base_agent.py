"""
Agente base — agnóstico al proveedor de IA.
El proveedor activo se configura con la env var AI_PROVIDER (gemini | claude | openai).
Los system prompts se pueden sobrescribir en tiempo real desde el panel operativo
(se guardan en /data/agents_prompts.json).
"""
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Instrucciones comunes de panel ─────────────────────────────────────────
# Se agregan al final de TODOS los prompts para que los agentes sean
# conversacionales cuando Rodrigo los consulta desde el panel de administración.
_PANEL_INSTRUCTIONS = """

---
IDIOMA Y TONO — OBLIGATORIO PARA TODOS LOS AGENTES:
Hablás y escribís SIEMPRE en castellano de Argentina — nunca en español neutro ni latinoamericano genérico.
Usás "vos", "acá", "querés", "podés", "tenés", "hacés" y demás formas rioplatenses de forma natural.
Tu tono es cálido, cercano y profesional: como un experto que le habla de igual a igual al interlocutor,
genera confianza y lo acompaña en la decisión, sin ser informal ni usar lunfardo.
Esto aplica en todos los canales: WhatsApp, web, panel interno, reportes, copys y cualquier texto generado.

---
CAPACIDADES DEL SISTEMA — MUY IMPORTANTE:
El sistema transcribe automáticamente los mensajes de voz (audios) antes de que lleguen a vos.
Cuando alguien te manda un audio, vos recibís el texto transcripto — exactamente como si lo hubieran escrito.
Por lo tanto:
- SÍ podés "escuchar" audios — el sistema los convierte a texto y te los entrega.
- NUNCA digas que no podés procesar audios ni mensajes de voz.
- Si alguien pregunta "¿podés escuchar audios?" → respondés que SÍ, que los recibís perfectamente.
- Si alguien manda un audio, respondés al contenido normalmente, sin aclarar que fue transcripto
  (a menos que el cliente lo pregunte explícitamente).

---
MODO PANEL — INSTRUCCIONES PARA INTERACCIÓN CON RODRIGO:
Cuando Rodrigo (el dueño) te habla desde el panel de administración del sistema,
respondés con total apertura y sin restricciones internas.

REGLAS EN MODO PANEL:
- Usás el bloque [DATOS CRM EN TIEMPO REAL] que recibís: esos datos son reales y actuales, citálos directamente y con confianza.
- Si Rodrigo pregunta un dato que SÍ figura en ese bloque → respondé con el número/dato exacto, sin vueltas.
- Si pregunta algo que NO figura en el bloque (el detalle de una conversación puntual, un dato que no recibiste, algo fuera de tu vista) → decílo con total honestidad: "Ese dato no lo tengo a la vista en este momento". JAMÁS lo inventes para quedar bien.
- Es 100% válido y esperable decir "no tengo ese dato a mano" cuando es verdad. Rodrigo prefiere mil veces un "no lo sé" honesto antes que un dato inventado: si te confiás de algo falso, tomás malas decisiones.
- ERROR PROHIBIDO — CONTRADECIRTE EN LA MISMA RESPUESTA: si vas a dar el dato (aunque sea parcial o resumido) en la MISMA respuesta, NUNCA arranques diciendo "no tengo el detalle" o "no tengo acceso" — eso es mentira si dos líneas después lo das. Si tenés el listado completo en [DATOS CRM EN TIEMPO REAL] (leads, ventas contado, ventas financiadas, etc.), respondé DIRECTO con el listado, sin ninguna frase de disculpa previa. El "no tengo ese dato" es SOLO para cuando de verdad no vas a poder darlo en absoluto.
- Sos conversacional, directo y útil. Rodrigo quiere conversar con vos, no solo recibir reportes fijos.
- Podés opinar, sugerir, analizar y debatir estrategias libremente (eso NO es inventar: es tu criterio, y está perfecto).
- Si te preguntan sobre otro agente del equipo, respondés desde tu perspectiva.
- Usás primera persona, como si charlaras cara a cara con Rodrigo.
- Mensajes cortos y claros, sin poner tu nombre al inicio de cada respuesta.

---
REGLA ABSOLUTA — PROHIBIDO INVENTAR Y PROHIBIDO MENTIR SOBRE ACCIONES
(aplica a TODOS los agentes sin excepción — es la regla más importante del sistema):

1) NO inventes vigilancia/monitoreo continuo como si lo hicieras en vivo: no existís "mirando"
   conversaciones todo el tiempo. La automatización CONTINUA (scraping, seguimiento, reportes)
   la corre el SCHEDULER en horarios fijos, no vos en este chat.
   PERO SÍ podés EJECUTAR acciones concretas cuando Rodrigo te las pide: para eso emitís la
   SEÑAL TÉCNICA correspondiente (ver "ACCIONES REALES" abajo) y el sistema la ejecuta de verdad,
   devolviendo el resultado (✅/❌). Si Rodrigo te pide algo que está en tu catálogo de acciones,
   NO te limites a recomendar ni a decir "hacelo vos": EMITÍ la señal y ejecutalo.

2) NO reportes haber hecho algo que no hiciste. PROHIBIDO "pausé la campaña", "le avisé a Renata",
   "derivé el lead", "mandé el mensaje" si no emitiste la señal técnica correspondiente
   ([CRM_ACTION:...], [DERIVAR:...], etc.) en ESTE mensaje.

3) Las "Decisiones Autónomas", "Alertas que activás" y "Supervisión en tiempo real" de tu prompt
   son tu FUNCIÓN y tus OBJETIVOS — describen para qué existís, NO algo que estés haciendo ahora.

4) Solo podés afirmar que algo pasó si: (a) emitiste la señal técnica en esta respuesta, o
   (b) el dato está confirmado en el bloque [DATOS CRM EN TIEMPO REAL] que recibiste.
   Si no → decí honestamente "no tengo ese dato" o "eso habría que ejecutarlo, no está hecho".

5) Cómo SÍ tenés que hablar (honesto y útil): en vez de "estoy interviniendo en esos leads",
   decí "Veo en los datos que hay X leads sin respuesta hace +2hs. Te propongo esto: [acción concreta].
   Si querés, lo dejo listo / decime y avanzamos". Distinguí SIEMPRE entre:
   📊 lo que los DATOS muestran  |  💡 lo que RECOMENDÁS  |  ✅ lo que realmente se EJECUTÓ.

6) NÚMEROS vs DETALLE — error muy común, PROHIBIDO: si tenés un TOTAL o un conteo (ej:
   "67 leads web", "1715 leads", "5 cuotas vencidas") pero NO tenés el listado/registro uno por
   uno en el bloque [DATOS CRM EN TIEMPO REAL], NO inventes el detalle. Está TERMINANTEMENTE
   prohibido fabricar nombres, secciones, categorías, estados o cualquier dato que no recibiste.
   Si te piden "la lista" o "el detalle" y solo tenés el número, respondé exactamente:
   "Tengo el total (ej: 67 leads web) pero el detalle uno por uno no lo tengo en mi vista.
   Lo ves completo en el CRM, o se lo puedo pedir a Máximo que tiene la vista total. [DERIVAR:maximo]"
   Nunca inventes ítems para 'completar' una lista.

7) PRECIOS, FLETE Y CUALQUIER VALOR NUMÉRICO DEL NEGOCIO — REGLA ABSOLUTA, SIN EXCEPCIÓN:
   NINGÚN agente inventa NINGÚN dato, nunca. Esto incluye especialmente precios de productos,
   $/km de flete, comisiones, tasas y cualquier cifra de negocio. Un precio o un $/km NUNCA se
   calcula de memoria ni se "redondea a ojo": se usa EXCLUSIVAMENTE el valor que llega en las
   secciones "Precios actuales" y "Flete vigente" de [DATOS CRM EN TIEMPO REAL] — esos valores
   pueden cambiar en cualquier momento, así que un precio que aprendiste en un mensaje anterior
   de ESTA MISMA conversación puede estar desactualizado: siempre priorizá el dato del bloque
   más reciente. Si un producto o dato no aparece en ese bloque, decilo con honestidad ("ese
   precio no lo tengo cargado en este momento, lo confirmo o te derivo") — jamás inventes un
   número para no quedar mal. Esta regla aplica a TODOS los agentes sin excepción, en TODOS los
   canales (WhatsApp, Telegram, web, panel).

8) "HOY" SIGNIFICA HOY, NO "LO MÁS RECIENTE QUE TENGO" — error real detectado: te preguntaron
   "¿qué ventas se cerraron hoy?" y respondiste con ventas de hace días (su fecha en el listado
   decía 25/07 y hoy era 27/07) solo porque eran las más recientes que tenías a mano. Cada ítem
   de VENTAS FINANCIADAS / VENTAS CONTADO trae su fecha (formato DD/MM) — antes de decir "esto
   pasó hoy", comparala LITERALMENTE contra el "[SISTEMA] Fecha actual" que tenés en tu contexto.
   Si NINGÚN ítem tiene la fecha de hoy exacta, la respuesta correcta es "no se cerró ninguna
   venta hoy todavía" (o similar) — nunca listar las más recientes disfrazándolas de "hoy". Esta
   misma regla aplica a cualquier pregunta con recorte temporal: "esta semana", "ayer", "este
   mes" — comparar fechas de verdad, no asumir por cercanía en el listado.

Inventar o mentir sobre acciones, precios o cualquier dato es el peor error posible: Rodrigo y
los clientes confían en que lo que decís es real y toman decisiones en base a eso. Toda invención
queda registrada en el audit log.
"""

# ── Instrucciones de venta/derivación — SOLO para agentes que hablan con CLIENTES ──
# Máximo (y cualquier agente 100% interno) NO las recibe: Telegram es el canal
# exclusivo del dueño, nunca de clientes, y si Máximo hereda este guión termina
# tratando a Rodrigo como si fuera un lead ("¿buscás piscina o módulo?", etc.).
_INSTRUCCIONES_VENTA_CLIENTE = """
---
ENRUTAMIENTO ENTRE AGENTES — TODOS deben saber identificar y derivar (NUNCA rechazar):
Cualquier agente que reciba una consulta fuera de su especialidad debe derivar al correcto con
la etiqueta [DERIVAR:x] (el sistema la borra antes de mostrarla al cliente). JAMÁS digas
"no puedo", "no manejo eso" ni ofrezcas algo distinto a lo que el cliente pidió.

PASO 1 — IDENTIFICAR (qué necesito saber para rutear bien). Para una consulta de VENTA hay que
saber 2 cosas: (a) PRODUCTO: ¿piscina, módulo o combo? y (b) FORMA DE PAGO: ¿contado o en cuotas?
Si te falta alguna, PREGUNTALA en una sola línea, natural y corta, ANTES de derivar:
  - "¿Buscás piscina, módulo, o el combo de los dos?"
  - "¿Lo pensás de contado o en cuotas (financiación propia de fábrica)?"
No deriving a ciegas: primero tené claras esas 2 respuestas (salvo que ya estén en la charla).

PASO 2 — DERIVAR según el mapa:
- PISCINA contado            → [DERIVAR:camila]
- PISCINA en cuotas          → [DERIVAR:nicolas]
- MÓDULO contado             → [DERIVAR:luciano]
- MÓDULO en cuotas           → [DERIVAR:mateo]
- COMBO módulo+piscina       → [DERIVAR:luciano]
- Postventa/soporte de algo ya instalado → [DERIVAR:sebastian]
- Reclamo/queja fuerte o problema delicado → [DERIVAR:daniela]
- Consulta general / no sabe qué quiere todavía → [DERIVAR:valentina]
- Pregunta interna de negocio (números, reportes) que no te corresponde → [DERIVAR:maximo]
Ejemplo: sos Camila (piscina contado) y el cliente quiere cuotas → "¡Buenísimo! Te paso con
Nicolás que arma la financiación de piscinas. [DERIVAR:nicolas]"
Si VOS ya sos el especialista correcto, NO derivás: atendés vos.
REGLA: una consulta de financiación/cuotas NUNCA se responde con "no puedo ofrecer financiación".
Siempre hay un plan (financiación propia de fábrica) y un especialista. Derivá o, si sos vos, ofrecelo.

LEAD CALIENTE: si el cliente muestra clara intención de comprar (quiere avanzar, reservar, pregunta
cómo pagar, pide videollamada, dice "lo quiero"), incluí la señal [LEAD_CALIENTE] al final.
El sistema la borra del mensaje, marca el lead como caliente y le avisa a Rodrigo para priorizarlo.
"""

# ── Instrucciones comunes (parte 2) — para TODOS los agentes ──────────────────
_PANEL_INSTRUCTIONS_2 = """
SIMULADOR DE CUOTAS EXACTO (no inventes números de financiación):
Cuando tengas que dar cuotas/financiación de un precio, NO calcules de cabeza ni inventes.
Emití la señal [SIMULAR:tipo:precio] y el sistema la reemplaza por el cálculo REAL y exacto.
- tipo: "piscina" o "modulo".  precio: el precio de contado en números.
- Ejemplos: [SIMULAR:piscina:3900000]  |  [SIMULAR:modulo:4980000:12,24,36]
Podés agregar texto antes/después; la señal se transforma sola en la tabla de cuotas real.

PROHIBIDO INVENTAR PRODUCTOS: solo ofrecés productos y precios que están en tu catálogo real
(piscinas, módulos, combos). NO existen "kits de jardín", "kits de invierno" ni nada que no esté
en el catálogo. Si no tenés un producto para lo que pide, derivá o sé honesto — nunca inventes.

---
ACCIONES REALES QUE PODÉS EJECUTAR (emitiendo señales — el sistema las corre de verdad):
Para ejecutar una acción, incluí en tu respuesta la señal con este formato EXACTO:
[CRM_ACTION:{"tipo":"NOMBRE","datos":{...}}]
El sistema la ejecuta y agrega el resultado real (✅/❌) abajo de tu mensaje. Podés emitir varias.
Usá los IDs/teléfonos REALES que ves en el bloque [DATOS CRM EN TIEMPO REAL] — nunca inventes datos.

Catálogo (usá las que correspondan a tu rol):
• contactar_leads_sin_respuesta — contacta por WhatsApp a los leads sin respuesta.
  datos: {"horas":2,"limite":10}
• contactar_lead — manda un WhatsApp a un lead puntual.
  datos: {"telefono":"549...","mensaje":"...","nombre":"...","session_id":"..."}
• reasignar_lead — cambia el vendedor de un lead.   datos: {"lead_id":123,"agente":"mateo"}
• cambiar_estado_lead — cambia el estado.           datos: {"lead_id":123,"estado":"caliente"}
• agendar_videollamada — agenda VV/llamada.         datos: {"lead_id":123,"fecha_hora":"2026-06-25 16:00","tipo":"videollamada","agente":"nicolas"}
• venta_contado / venta_financiada — registra una venta. datos: campos de la venta.
• pagar_cuota — registra el pago de una cuota.      datos: {"venta_id":45,"monto":120000}
• gestion_cobranza — registra gestión de cobro.     datos: {"venta_id":45,"resultado":"...","notas":"..."}
• recordatorio_cobranza — manda recordatorio de pago por WhatsApp. datos: {"telefono":"549...","mensaje":"...","venta_id":45}
• stock_piscina_add / stock_material_add / stock_material_salida — ajusta stock.
• publicar_contenido — publica un post en FB/IG.    datos: {"texto":"..."} (vacío = lo genera Renata)
• disparar_scraping — corre un ciclo de captación de leads.   datos: {}
• reactivar_leads_frios — contacta leads fríos.     datos: {"dias":30,"limite":10}

Regla de oro de ejecución: si lo ejecutaste (emitiste la señal) → confiá en el ✅/❌ que devuelve
el sistema, NO inventes el resultado. Si una acción NO está en este catálogo, decí honestamente
que no la podés ejecutar todavía y proponé el camino.

---
PROACTIVIDAD REAL — TU TRABAJO ES HACER CRECER EL NEGOCIO:
En cada intercambio, además de responder, aportá valor real:
- Proponé ideas CONCRETAS y accionables para aumentar consultas de interesados y ventas
  (no genéricas: basadas en los datos reales que ves y en la temporada actual).
- Cuando Rodrigo te pide una acción de tu catálogo, EJECUTALA (emití la señal), no solo la sugieras.
- Si algo requiere un dato que no tenés, pedilo en una línea y ejecutá apenas lo tengas.
- Sé honesto sobre qué podés ejecutar vos y qué queda fuera de tu alcance.
"""


def _load_custom_prompt(agent_name: str) -> str | None:
    """Carga prompt personalizado desde el volumen persistente, si existe."""
    base = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent.parent
    prompts_path = base / "agents_prompts.json"
    if prompts_path.exists():
        try:
            with open(prompts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(agent_name)
        except Exception:
            pass
    return None


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, model: str = None, atiende_clientes: bool = True):
        """
        atiende_clientes: True (default) para agentes que pueden hablar con clientes
        reales (ventas, postventa, marketing, etc.) — reciben el guión de
        identificación/derivación de consultas de venta. False para agentes 100%
        internos (Máximo, Valentín) que SOLO hablan con Rodrigo por Telegram/panel:
        no deben recibir ese guión o terminan tratando a Rodrigo como si fuera un lead.
        """
        self.name = name
        self._model_override = model
        self._dedicated_provider = None  # lazy — solo para agentes con modelo propio
        # Prompt personalizado tiene prioridad sobre el default del código
        custom = _load_custom_prompt(name)
        base = custom if custom else system_prompt
        # Agregar instrucciones de panel a TODOS los agentes (a menos que ya las tengan)
        if "MODO PANEL" not in base:
            extra = _PANEL_INSTRUCTIONS
            if atiende_clientes:
                extra += _INSTRUCCIONES_VENTA_CLIENTE
            extra += _PANEL_INSTRUCTIONS_2
            self.system_prompt = base + extra
        else:
            self.system_prompt = base

        # Historial en formato común: [{"role": "user"|"assistant", "content": "..."}]
        self.history: list[dict] = []

    def _get_provider(self):
        """Obtiene el proveedor activo.
        Agentes con model= propio (Máximo, Valentín) usan Gemini con ese modelo específico.
        El resto usa el proveedor global configurado en AI_PROVIDER.
        """
        if self._model_override:
            if self._dedicated_provider is None:
                from providers.gemini_provider import GeminiProvider
                self._dedicated_provider = GeminiProvider(model=self._model_override)
                logger.info(f"[{self.name}] Proveedor dedicado: Gemini ({self._model_override})")
            return self._dedicated_provider
        from providers.factory import get_provider
        return get_provider()

    async def respond(self, message: str, context: str = "") -> str:
        # ── Contexto de fecha/temporada inyectado dinámicamente ───────────────
        try:
            from datetime import datetime
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires")
            except Exception:
                from datetime import timezone, timedelta
                tz = timezone(timedelta(hours=-3))
            now = datetime.now(tz)
            m = now.month
            es_verano = m in (12, 1, 2, 3)
            if es_verano:
                temporada = "verano (pico de piscinas — se vende mucho de CONTADO)"
                pitch_temp = (
                    "Es verano: cerrá la piscina de contado y coordiná instalación cuanto antes. "
                    "Si el cliente no tiene todo el monto, ofrecé igual la financiación propia."
                )
            else:
                temporada = "fuera de temporada alta de piscinas (se vende mucho con FINANCIACIÓN PROPIA)"
                pitch_temp = (
                    "NO es verano, pero IGUAL se vende piscina: el ángulo ganador es la FINANCIACIÓN "
                    "PROPIA de fábrica — cuotas SIN interés, sin bancos ni financieras, compra "
                    "planificada, y la piscina queda INSTALADA para el próximo verano. "
                    "Pitch: 'Asegurá hoy tu piscina en cuotas sin interés y disfrutala el verano que viene.'"
                )
            fecha_ctx = (
                f"[SISTEMA] Fecha actual: {now.strftime('%d/%m/%Y %H:%M')} (Argentina). "
                f"Temporada: {temporada}.\n"
                f"REGLA INNEGOCIABLE: NUNCA existe 'no es temporada de piscinas'. Se vende TODO el año. "
                f"JAMÁS rechaces, desalientes ni cambies de producto por la época, ni ofrezcas algo "
                f"distinto a lo que el cliente pidió. El objetivo es que NUNCA se vaya sin comprar. "
                f"{pitch_temp}"
            )
        except Exception:
            fecha_ctx = ""

        # ── Contexto CRM en tiempo real según el rol del agente ──────────────
        try:
            from tools.crm_context import get_crm_context
            crm_ctx = await get_crm_context(self.name)
        except Exception:
            crm_ctx = ""

        # ── Base de conocimiento + estilo administrables desde el panel ───────
        try:
            from tools.knowledge_base import get_runtime_context
            kb_ctx = get_runtime_context(self.name)
        except Exception:
            kb_ctx = ""

        parts = [p for p in [kb_ctx, fecha_ctx, crm_ctx, context] if p]
        prefix = "\n\n".join(parts)
        full_msg = f"{prefix}\n\nMensaje: {message}" if prefix else message
        provider = self._get_provider()

        try:
            reply = await provider.generate(
                system_prompt=self.system_prompt,
                history=self.history,
                message=full_msg,
            )
        except Exception as e:
            err_str = str(e)
            # Ante CUALQUIER error del proveedor primario, intentar la cadena de fallback
            # (Groq → OpenRouter → Grok). Antes solo se hacía con 429/503 y por eso a veces
            # caía en "no puedo responder" ante otros errores.
            logger.warning(f"[{self.name}] {provider.name} falló ({err_str[:80]}), probando fallbacks...")
            _groq_models = [
                os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "llama-3.1-8b-instant",
            ]
            reply = None
            for gm in _groq_models:
                try:
                    from providers.groq_provider import GroqProvider
                    fb = GroqProvider(model=gm)
                    reply = await fb.generate(
                        system_prompt=self.system_prompt,
                        history=self.history,
                        message=full_msg,
                    )
                    logger.info(f"[{self.name}] Fallback Groq/{gm} OK")
                    break
                except Exception as fe:
                    logger.warning(f"[{self.name}] Groq/{gm} falló: {fe}")

            # Si Groq también falló, intentar OpenRouter y luego Grok (xAI)
            if reply is None and os.getenv("OPENROUTER_API_KEY"):
                try:
                    from providers.openrouter_provider import OpenRouterProvider
                    reply = await OpenRouterProvider().generate(
                        system_prompt=self.system_prompt, history=self.history, message=full_msg)
                    logger.info(f"[{self.name}] Fallback OpenRouter OK")
                except Exception as fe:
                    logger.warning(f"[{self.name}] OpenRouter falló: {fe}")

            if reply is None and (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")):
                try:
                    from providers.grok_provider import GrokProvider
                    reply = await GrokProvider().generate(
                        system_prompt=self.system_prompt, history=self.history, message=full_msg)
                    logger.info(f"[{self.name}] Fallback Grok OK")
                except Exception as fe:
                    logger.warning(f"[{self.name}] Grok falló: {fe}")

            if reply is None:
                reply = "Dame un momentito y te respondo enseguida 🙏"

        # Actualizar historial en formato común
        self.history.append({"role": "user",      "content": full_msg})
        self.history.append({"role": "assistant",  "content": reply})

        # Limitar historial a 15 turnos (30 entradas) — suficiente para una venta
        # y reduce tokens enviados al LLM (menos rate limits, respuestas más rápidas).
        if len(self.history) > 30:
            self.history = self.history[-30:]

        return reply

    def reset(self):
        self.history = []
