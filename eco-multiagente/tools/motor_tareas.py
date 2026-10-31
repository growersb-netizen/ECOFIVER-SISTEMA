"""
Worker del motor de tareas (Fase 1).

La tarea vive en el CRM (fuente de verdad). Este worker:
  1. reclama la próxima tarea ejecutable (lease atómico en el CRM),
  2. la ejecuta con una instancia nueva del agente (sin memoria de otras tareas
     ni de clientes), con tiempo límite y latido que detecta cancelaciones,
  3. procesa lo que el agente pidió:
       - acciones OPERATIVAS permitidas a ese agente → se ejecutan,
       - acciones SENSIBLES → se proponen al CRM y esperan a un humano,
       - acciones no permitidas → se registran como bloqueadas,
       - [DELEGAR:{...}] → subtarea en el CRM (el CRM valida jerarquía,
         profundidad, cantidad y presupuesto),
  4. devuelve resultado + evidencia (modelo, costo, acciones, subtareas) o falla
     con reintento.
Además ejecuta las acciones que un administrador humano aprobó.

El texto de la instrucción nunca otorga permisos: el agente solo puede lo que
tools.action_policy le permite, y lo sensible pasa por aprobación humana.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import socket
from typing import Optional

import httpx

from tools import crm_client

logger = logging.getLogger(__name__)

AGENTES_EMPRESA = {
    "maximo", "aurora", "tomas", "valentina", "camila", "nicolas", "luciano", "mateo",
    "renata", "bruno", "ezequiel", "elena", "ignacio", "sebastian", "daniela", "franco",
}
DELEGADORES = {"maximo", "aurora", "tomas"}
TIMEOUT_EJECUCION_S = int(os.getenv("MOTOR_TIMEOUT_S", "180"))
INTERVALO_S = int(os.getenv("MOTOR_INTERVALO_S", "15"))
LATIDO_S = 60
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

_DELEGAR_RE = re.compile(r"\[DELEGAR:(\{.*?\})\]", re.DOTALL)
_despertar: Optional[asyncio.Event] = None
_stats = {"ejecutadas": 0, "fallidas": 0, "aprobaciones_ejecutadas": 0, "ultima": None, "activo": False}


def stats() -> dict:
    return dict(_stats, worker=WORKER_ID)


def despertar() -> None:
    """Pide un sondeo inmediato (lo usa /api/comando al recibir el aviso del CRM)."""
    if _despertar is not None:
        _despertar.set()


# ── Llamadas al CRM ───────────────────────────────────────────────────────────

async def _crm(metodo: str, ruta: str, json_body: Optional[dict] = None) -> dict:
    async with httpx.AsyncClient(timeout=crm_client.TIMEOUT) as c:
        r = await c.request(metodo, f"{crm_client.CRM_BASE_URL}{ruta}", headers=crm_client.HEADERS, json=json_body)
    if r.status_code >= 400:
        raise RuntimeError(f"CRM {ruta} → HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def crear_tarea(agente: str, instruccion: str, **kw) -> dict:
    cuerpo = {"agente": agente, "instruccion": instruccion, **{k: v for k, v in kw.items() if v is not None}}
    return (await _crm("POST", "/api/motor/tareas", cuerpo))["tarea"]


async def _agentes_habilitados() -> Optional[list[str]]:
    """Agentes que pueden tomar tareas ahora (Fase 2: control administrativo). None = todos."""
    try:
        from tools import control_agentes
        return await control_agentes.agentes_para_tareas()
    except ImportError:
        return None


# ── Ejecución de una tarea ────────────────────────────────────────────────────

def _instanciar(agente: str):
    mod = importlib.import_module(f"agents.{agente}")
    return mod.get_agent()          # instancia nueva: sin historial de otras tareas ni clientes


def _contexto_tarea(t: dict) -> str:
    delegar = (
        "Podés delegar partes del trabajo a otros agentes de la empresa escribiendo, una vez por subtarea:\n"
        '[DELEGAR:{"agente": "<nombre>", "instruccion": "<qué necesitás>", "prioridad": "NORMAL"}]\n'
        "La subtarea se ejecuta aparte; su resultado no te llega en esta misma respuesta."
        if t["agente"] in DELEGADORES else "No podés delegar tareas a otros agentes."
    )
    extra = {k: v for k, v in (t.get("contexto") or {}).items() if k != "tarea_id"}
    return (
        f"[TAREA #{t['id']} DEL MOTOR DE EcoFiver — prioridad {t['prioridad']}]\n"
        f"Título: {t['titulo']}\n"
        "Ejecutá la tarea con los datos reales del CRM que tenés en tu contexto. No inventes resultados, "
        "ventas ni cifras: si falta un dato, decilo. Respondé con el resultado concreto.\n"
        "Las acciones sobre el CRM van como [CRM_ACTION:{...}]. Las sensibles (dinero, contratos, "
        "contactar clientes, publicar) quedan pendientes de aprobación humana: proponelas igual.\n"
        f"{delegar}\n"
        + (f"Contexto adicional: {json.dumps(extra, ensure_ascii=False)[:2000]}" if extra else "")
    )


async def _procesar_salida(t: dict, reply: str) -> tuple[str, dict]:
    from tools.action_policy import ACTION_LEVEL, CANAL_CONFIABLE, OPERATIVA, ActionContext, evaluar
    from tools.crm_actions import detectar_acciones, ejecutar_acciones, limpiar_acciones

    evidencia = {"acciones_ejecutadas": [], "acciones_propuestas": [], "acciones_bloqueadas": [], "subtareas": [],
                 "delegaciones_rechazadas": []}
    agente = t["agente"]
    ctx = ActionContext(agente=agente, canal=CANAL_CONFIABLE, origen=f"tarea:{t['id']}")
    for accion in detectar_acciones(reply):
        tipo = str(accion.get("tipo", "")).lower()
        datos = accion.get("datos") if isinstance(accion.get("datos"), dict) else {}
        decision = evaluar(tipo, datos, ctx)
        if tipo == "crear_tarea":         # dentro del motor solo se delega con [DELEGAR] (con límites)
            evidencia["acciones_bloqueadas"].append({"tipo": tipo, "motivo": "en una tarea se delega con [DELEGAR]"})
        elif not decision.permitido:
            evidencia["acciones_bloqueadas"].append({"tipo": tipo, "motivo": decision.motivo})
        elif ACTION_LEVEL.get(tipo) == OPERATIVA:
            res = await ejecutar_acciones([{"tipo": tipo, "datos": datos}], ctx)
            evidencia["acciones_ejecutadas"].append({"tipo": tipo, "resultado": res[:500]})
        else:
            prop = await _crm("POST", "/api/motor/aprobaciones", {
                "tarea_id": t["id"], "agente": agente, "tipo_accion": tipo, "datos": datos,
                "motivo": f"Propuesta en la tarea #{t['id']}: {t['titulo'][:150]}"})
            evidencia["acciones_propuestas"].append({"tipo": tipo, "aprobacion_id": prop["aprobacion"]["id"]})

    for m in _DELEGAR_RE.finditer(reply):
        try:
            d = json.loads(m.group(1))
            r = await _crm("POST", "/api/motor/delegar", {
                "padre_id": t["id"], "creado_por_agente": agente, "agente": str(d.get("agente", "")),
                "instruccion": str(d.get("instruccion", ""))[:8000], "prioridad": str(d.get("prioridad", "NORMAL")),
                "titulo": str(d.get("titulo", ""))[:200],
                "clave_idempotencia": f"t{t['id']}-i{t.get('intentos', 0)}-d{m.start()}"})
            evidencia["subtareas"].append(r["tarea"]["id"])
        except Exception as e:      # el CRM rechazó (jerarquía, profundidad, presupuesto) o JSON inválido
            evidencia["delegaciones_rechazadas"].append(str(e)[:300])

    texto = _DELEGAR_RE.sub("", limpiar_acciones(reply)).strip()
    return texto, evidencia


async def _latido(t: dict, tarea_exec: asyncio.Task) -> None:
    while not tarea_exec.done():
        await asyncio.sleep(LATIDO_S)
        try:
            r = await _crm("POST", f"/api/motor/tareas/{t['id']}/latido", {"lease_token": t["lease_token"]})
            if r.get("cancelacion_solicitada"):
                t["_cancelada_por_usuario"] = True
                tarea_exec.cancel()
                return
        except Exception as e:
            logger.warning(f"[Motor] Latido de #{t['id']} falló: {e}")


def _costo_proceso(proceso: str) -> float:
    try:
        from tools.ai_metrics import _estado
        return float(_estado.por_proceso.get(proceso, {}).get("costo_usd", 0.0))
    except Exception:
        return 0.0


async def ejecutar_tarea(t: dict) -> str:
    """Ejecuta una tarea ya reclamada. Devuelve el estado final informado por el CRM."""
    from tools.ai_metrics import proceso_actual

    agente = t["agente"]
    proceso = f"tarea:{t['id']}"
    token = proceso_actual.set(proceso)
    costo_antes = _costo_proceso(proceso)
    lease = {"lease_token": t["lease_token"]}
    try:
        if agente not in AGENTES_EMPRESA:
            return (await _crm("POST", f"/api/motor/tareas/{t['id']}/fallar",
                               {**lease, "error": f"Agente '{agente}' fuera de la empresa", "reintentable": False}))["estado"]
        instancia = _instanciar(agente)
        ejec = asyncio.ensure_future(asyncio.wait_for(
            instancia.respond(t["instruccion"], _contexto_tarea(t)), timeout=TIMEOUT_EJECUCION_S))
        vigia = asyncio.ensure_future(_latido(t, ejec))
        try:
            reply = await ejec
        except asyncio.CancelledError:
            if not t.get("_cancelada_por_usuario"):
                raise                       # apagado del proceso: el lease vence y se retoma
            return (await _crm("POST", f"/api/motor/tareas/{t['id']}/completar",
                               {**lease, "resultado": {"texto": "Cancelada antes de terminar"}, "evidencia": {}}))["estado"]
        finally:
            vigia.cancel()
        costo = max(0.0, _costo_proceso(proceso) - costo_antes)
        if not (reply or "").strip():
            raise RuntimeError("El agente no generó respuesta")
        texto, evidencia = await _procesar_salida(t, reply)
        evidencia.update({"agente": agente, "worker": WORKER_ID, "costo_usd": round(costo, 6)})
        r = await _crm("POST", f"/api/motor/tareas/{t['id']}/completar",
                       {**lease, "resultado": {"texto": texto}, "evidencia": evidencia, "costo_usd": costo})
        _stats["ejecutadas"] += 1
        return r["estado"]
    except Exception as e:
        _stats["fallidas"] += 1
        logger.warning(f"[Motor] Tarea #{t['id']} falló: {e}")
        try:
            costo = max(0.0, _costo_proceso(proceso) - costo_antes)
            return (await _crm("POST", f"/api/motor/tareas/{t['id']}/fallar",
                               {**lease, "error": str(e)[:1000], "reintentable": True, "costo_usd": costo}))["estado"]
        except Exception as e2:     # el lease vence y otra ejecución la retoma
            logger.error(f"[Motor] No se pudo informar la falla de #{t['id']}: {e2}")
            return "DESCONOCIDO"
    finally:
        proceso_actual.reset(token)


async def ejecutar_aprobada(a: dict) -> str:
    """Ejecuta una acción que un administrador humano aprobó en el CRM."""
    from tools.action_policy import CANAL_CONFIABLE, ActionContext
    from tools.crm_actions import ejecutar_acciones

    ctx = ActionContext(agente=a["agente"], canal=CANAL_CONFIABLE, origen=f"aprobacion:{a['id']}",
                        extra={"aprobado_por": a.get("decidido_por_id")})
    try:
        res = await ejecutar_acciones([{"tipo": a["tipo_accion"], "datos": a.get("datos") or {}}], ctx)
        ok = bool(res) and not res.startswith(("⛔", "❌"))
    except Exception as e:
        res, ok = f"❌ {e}", False
    r = await _crm("POST", f"/api/motor/aprobaciones/{a['id']}/resultado",
                   {"lease_token": a["lease_token"], "ok": ok, "resultado": res[:4000]})
    _stats["aprobaciones_ejecutadas"] += 1
    return r["estado"]


# ── Bucle ─────────────────────────────────────────────────────────────────────

async def un_ciclo() -> int:
    """Procesa aprobaciones listas y tareas disponibles. Devuelve cuántas tareas ejecutó."""
    while True:
        a = (await _crm("POST", "/api/motor/aprobaciones/reclamar"))["aprobacion"]
        if not a:
            break
        await ejecutar_aprobada(a)
    n = 0
    while n < 5:                    # tope por ciclo: no monopolizar el proceso
        agentes = await _agentes_habilitados()
        t = (await _crm("POST", "/api/motor/reclamar", {"worker": WORKER_ID, "agentes": agentes}))["tarea"]
        if not t:
            break
        await ejecutar_tarea(t)
        n += 1
    _stats["ultima"] = asyncio.get_running_loop().time()
    return n


async def bucle() -> None:
    global _despertar
    _despertar = asyncio.Event()
    _stats["activo"] = True
    logger.info(f"[Motor] Worker {WORKER_ID} iniciado (intervalo {INTERVALO_S}s)")
    while True:
        try:
            await un_ciclo()
        except Exception as e:
            logger.warning(f"[Motor] Ciclo con error: {e}")
        try:
            await asyncio.wait_for(_despertar.wait(), timeout=INTERVALO_S)
        except asyncio.TimeoutError:
            pass
        _despertar.clear()


def habilitado() -> bool:
    return os.getenv("MOTOR_TAREAS", "on").strip().lower() not in ("off", "0", "false", "no")
