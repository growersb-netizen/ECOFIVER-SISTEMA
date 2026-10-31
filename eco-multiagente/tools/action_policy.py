"""
Política de acciones CRM — validación del lado servidor (Etapa 0).

Las acciones [CRM_ACTION:{...}] las escribe un modelo de IA. El texto del modelo
NO es una autorización: cada acción se valida acá antes de ejecutarse, según
  1. el nivel de la acción (OPERATIVA / SENSIBLE / PROHIBIDA),
  2. el agente que la emitió (lista blanca por agente),
  3. el canal (CONFIABLE = Rodrigo/panel admin; CLIENTE = cualquier conversación
     con un tercero: WhatsApp de clientes, web, email, Instagram).

Reglas duras:
  - PROHIBIDA: nunca se ejecuta.
  - SENSIBLE: nunca se ejecuta desde un canal CLIENTE. En canal CONFIABLE se
    ejecuta solo si el agente la tiene permitida (la ordena el administrador).
  - CLIENTE: solo se permiten las acciones de CLIENT_CHANNEL_ACTIONS, acotadas
    al lead de la propia conversación y a campos seguros.
  - Contexto desconocido → se trata como CLIENTE (falla cerrado).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

OPERATIVA = "OPERATIVA"
SENSIBLE = "SENSIBLE"
PROHIBIDA = "PROHIBIDA"

ACTION_LEVEL: dict[str, str] = {
    # Registro operativo en el CRM
    "update_lead": OPERATIVA,
    "cambiar_estado_lead": OPERATIVA,
    "reasignar_lead": OPERATIVA,
    "agendar_videollamada": OPERATIVA,
    "gestion_cobranza": OPERATIVA,
    "recordar": OPERATIVA,
    # Circuito comercial (reglas del propietario): la IA cierra contado con precio
    # de catálogo validado en el CRM y abre financiaciones hasta Admisión.
    "cerrar_venta_contado": OPERATIVA,
    "abrir_financiacion": OPERATIVA,
    # Reservado a personas (Admisión, cobranzas, administración): la IA no registra
    # ventas financiadas, pagos ni contratos, ni siquiera con aprobación.
    "venta_contado": PROHIBIDA,
    "venta_financiada": PROHIBIDA,
    "pagar_cuota": PROHIBIDA,
    "emitir_contrato": PROHIBIDA,
    "stock_piscina_add": SENSIBLE,
    "stock_material_add": SENSIBLE,
    "stock_material_salida": SENSIBLE,
    # Contacto saliente y publicación (efecto externo)
    "contactar_lead": SENSIBLE,
    "contactar_leads_sin_respuesta": SENSIBLE,
    "reactivar_leads_frios": SENSIBLE,
    "recordatorio_cobranza": SENSIBLE,
    "publicar_contenido": SENSIBLE,
    # Contacto a personas sin consentimiento (scraping) — fuera de política
    "disparar_scraping": PROHIBIDA,
}

_MOTIVO_PROHIBIDA = {
    "disparar_scraping": "'disparar_scraping' está prohibida por política (requiere consentimiento del contacto)",
    "venta_contado": "Registrar ventas es de personas; la IA usa 'cerrar_venta_contado' (precio de catálogo validado)",
    "venta_financiada": "Las financiaciones las aprueba y cierra Admisión (personas), nunca la IA",
    "pagar_cuota": "Los pagos los registra una persona con evidencia, nunca la IA",
    "emitir_contrato": "Los contratos financiados los formaliza Admisión (personas), nunca la IA",
}
_TODAS_NO_PROHIBIDAS = {k for k, v in ACTION_LEVEL.items() if v != PROHIBIDA}
_SOLO_ESPECIALISTAS = {"cerrar_venta_contado", "abrir_financiacion"}
_VENDEDOR = {"update_lead", "cambiar_estado_lead", "agendar_videollamada"}

# Lista blanca por agente (matriz de permisos del diagnóstico, §10).
AGENT_ALLOWED: dict[str, set[str]] = {
    "maximo": set(_TODAS_NO_PROHIBIDAS) - _SOLO_ESPECIALISTAS,
    "aurora": {"update_lead", "cambiar_estado_lead", "reasignar_lead", "recordar"},
    "tomas": {"update_lead", "cambiar_estado_lead", "reasignar_lead", "agendar_videollamada",
              "contactar_lead", "contactar_leads_sin_respuesta", "reactivar_leads_frios"},
    "valentina": set(_VENDEDOR) | {"abrir_financiacion"},      # solo abre la consulta
    "camila": set(_VENDEDOR) | {"cerrar_venta_contado"},       # piscinas de contado
    "nicolas": set(_VENDEDOR) | {"abrir_financiacion"},        # financiación de piscinas
    "luciano": set(_VENDEDOR) | {"cerrar_venta_contado"},      # viviendas y módulos de contado
    "mateo": set(_VENDEDOR) | {"abrir_financiacion"},          # financiación de viviendas y módulos
    "sebastian": {"update_lead", "cambiar_estado_lead", "gestion_cobranza"},
    "ignacio": {"update_lead", "gestion_cobranza", "recordatorio_cobranza"},
    "ezequiel": {"gestion_cobranza"},          # control documental: registra gestiones, no pagos ni contratos
    "elena": {"update_lead"},
    "bruno": {"stock_piscina_add", "stock_material_add", "stock_material_salida"},
    "renata": {"publicar_contenido"},
    "daniela": {"update_lead"},
    "franco": {"update_lead"},
    "valentin": set(),
}

# Acciones admitidas en conversaciones con terceros, y campos seguros de update_lead.
CLIENT_CHANNEL_ACTIONS = {"update_lead", "agendar_videollamada", "cerrar_venta_contado", "abrir_financiacion"}
CLIENT_SAFE_LEAD_FIELDS = {
    "notas", "nombre", "email", "localidad", "provincia",
    "producto_interes", "forma_pago", "modelo_interes", "modelo_especifico",
}

CANAL_CONFIABLE = "confiable"
CANAL_CLIENTE = "cliente"


@dataclass
class ActionContext:
    agente: str
    canal: str = CANAL_CLIENTE           # "confiable" | "cliente"
    lead_id: int | None = None           # lead de la conversación (solo canal cliente)
    origen: str = ""                     # descripción para auditoría (whatsapp, web, telegram, panel…)
    extra: dict = field(default_factory=dict)


@dataclass
class Decision:
    permitido: bool
    motivo: str = ""


def _norm_agent(name: str) -> str:
    n = (name or "").strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        n = n.replace(a, b)
    return n


def evaluar(tipo: str, datos: dict, ctx: ActionContext | None) -> Decision:
    tipo = (tipo or "").strip().lower()
    nivel = ACTION_LEVEL.get(tipo)
    if nivel is None:
        return Decision(False, f"acción desconocida '{tipo}'")
    if nivel == PROHIBIDA:
        return Decision(False, _MOTIVO_PROHIBIDA.get(tipo, f"'{tipo}' está prohibida por política"))

    if ctx is None:
        ctx = ActionContext(agente="", canal=CANAL_CLIENTE, origen="desconocido")

    agente = _norm_agent(ctx.agente)
    if tipo not in AGENT_ALLOWED.get(agente, set()):
        return Decision(False, f"el agente '{agente or '?'}' no tiene permiso para '{tipo}'")

    if ctx.canal == CANAL_CONFIABLE:
        return Decision(True)

    # ── Canal cliente (o desconocido): reglas estrictas ──────────────────────
    if nivel == SENSIBLE:
        return Decision(False, f"'{tipo}' es sensible y no se ejecuta desde una conversación con clientes")
    if tipo not in CLIENT_CHANNEL_ACTIONS:
        return Decision(False, f"'{tipo}' no está habilitada en conversaciones con clientes")

    datos = datos or {}
    lead_accion = datos.get("lead_id")
    try:
        lead_accion = int(lead_accion) if lead_accion not in (None, "", "null") else None
    except (TypeError, ValueError):
        return Decision(False, "lead_id inválido")
    if ctx.lead_id is None or lead_accion != int(ctx.lead_id):
        return Decision(False, "solo se puede modificar el lead de la propia conversación")

    if tipo == "update_lead":
        campos = datos.get("campos") or {}
        if not isinstance(campos, dict) or not campos:
            return Decision(False, "update_lead sin campos")
        no_permitidos = set(campos) - CLIENT_SAFE_LEAD_FIELDS
        if no_permitidos:
            return Decision(False, f"campos no permitidos desde canal cliente: {sorted(no_permitidos)}")

    return Decision(True)


def registrar_bloqueo(tipo: str, ctx: ActionContext | None, motivo: str) -> None:
    """Deja rastro de cada acción bloqueada (log + auditoría persistente)."""
    agente = ctx.agente if ctx else "?"
    origen = ctx.origen if ctx else "desconocido"
    logger.warning(f"[ActionPolicy] BLOQUEADA tipo={tipo} agente={agente} origen={origen} motivo={motivo}")
    _bloqueos["total"] += 1
    _bloqueos["por_tipo"][tipo] = _bloqueos["por_tipo"].get(tipo, 0) + 1
    try:
        from tools.audit_log import registrar_interaccion
        registrar_interaccion(
            canal=f"policy:{origen}",
            session_id=f"policy-{agente}",
            agente=agente,
            mensaje_usuario=f"[ACCION BLOQUEADA] {tipo}",
            respuesta_agente=motivo,
        )
    except Exception:
        pass


_bloqueos: dict = {"total": 0, "por_tipo": {}}


def stats() -> dict:
    return {"bloqueadas_total": _bloqueos["total"], "bloqueadas_por_tipo": dict(_bloqueos["por_tipo"])}
