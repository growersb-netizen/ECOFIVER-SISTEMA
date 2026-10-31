"""
Modelo de IA por agente — todo vía OpenRouter.

Cada agente pertenece a un rol (ventas, dirección, análisis…) y cada rol tiene
modelo principal, respaldos, temperatura y largo máximo de respuesta.

Perfiles (AI_PERFIL_MODELOS):
  base         (default) — idéntico al comportamiento anterior: todos los agentes
               con OPENROUTER_MODEL, respaldo OPENROUTER_FALLBACK_MODELS,
               temperatura 0.7, 700 tokens. Cambiar de perfil es una decisión
               de costo/calidad que toma el administrador.
  recomendado  — modelo según la función del agente (ver PERFIL_RECOMENDADO).
               Es una propuesta: validar con /health/ia/modelos, que estima el
               costo de cada perfil con el uso real del día.

Ajuste fino sin redeploy de código (se aplica sobre el perfil):
  AI_MODELOS_JSON='{"maximo": {"modelo": "anthropic/claude-sonnet-4.5"},
                    "rol:ventas": {"temperatura": 0.5}}'

Validación: si el catálogo de OpenRouter está disponible y el modelo no existe
o no acepta la entrada que el rol necesita (audio para transcribir, imagen para
visión), se usa el primer respaldo válido y queda el aviso en /health/ia/modelos.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ROL_POR_AGENTE: dict[str, str] = {
    "valentina": "ventas", "camila": "ventas", "nicolas": "ventas", "luciano": "ventas", "mateo": "ventas",
    "sebastian": "postventa",
    "franco": "socios",
    "maximo": "direccion",
    "aurora": "analisis", "tomas": "analisis", "elena": "analisis", "ezequiel": "analisis",
    "ignacio": "analisis", "bruno": "analisis",
    "renata": "contenido",
    "daniela": "reputacion",
    "valentin": "privado",
    "transcripcion": "audio",
    "vision": "vision",
}

# Entrada que el modelo debe aceptar según el rol
CAPACIDAD_POR_ROL: dict[str, str] = {"audio": "audio", "vision": "image"}

# Propuesta (hipótesis a validar con costos reales):
# - ventas/postventa/socios: alto volumen, respuesta rápida → modelo económico ya probado.
# - dirección y reputación: poco volumen, decisiones y textos sensibles → modelo más capaz.
# - análisis/contenido: contexto largo (datos del CRM), poco volumen → contexto amplio y económico.
PERFIL_RECOMENDADO: dict[str, dict] = {
    "ventas":     {"modelo": "openai/gpt-4o-mini", "respaldo": ["google/gemini-2.5-flash"], "temperatura": 0.6, "max_tokens": 600},
    "postventa":  {"modelo": "openai/gpt-4o-mini", "respaldo": ["google/gemini-2.5-flash"], "temperatura": 0.4, "max_tokens": 700},
    "socios":     {"modelo": "openai/gpt-4o-mini", "respaldo": ["google/gemini-2.5-flash"], "temperatura": 0.6, "max_tokens": 700},
    "direccion":  {"modelo": "anthropic/claude-sonnet-4.5", "respaldo": ["google/gemini-2.5-flash", "openai/gpt-4o-mini"], "temperatura": 0.3, "max_tokens": 1500},
    "analisis":   {"modelo": "google/gemini-2.5-flash", "respaldo": ["openai/gpt-4o-mini"], "temperatura": 0.3, "max_tokens": 1200},
    "contenido":  {"modelo": "google/gemini-2.5-flash", "respaldo": ["openai/gpt-4o-mini"], "temperatura": 0.8, "max_tokens": 1200},
    "reputacion": {"modelo": "anthropic/claude-sonnet-4.5", "respaldo": ["openai/gpt-4o-mini"], "temperatura": 0.3, "max_tokens": 800},
    "privado":    {},  # lo decide el administrador; usa la base
    "audio":      {"modelo": "google/gemini-2.5-flash", "respaldo": ["google/gemini-2.5-flash-lite"], "temperatura": 0.0, "max_tokens": 1000},
    "vision":     {"modelo": "openai/gpt-4o-mini", "respaldo": ["google/gemini-2.5-flash"], "temperatura": 0.0, "max_tokens": 800},
}


@dataclass
class ConfigModelo:
    agente: str
    rol: str
    modelo: str
    respaldo: list[str]
    temperatura: float
    max_tokens: int
    configurado: str = ""                 # modelo pedido antes de validar
    avisos: list[str] = field(default_factory=list)


def _norm(name: str) -> str:
    n = (name or "").strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("dr. ", ""), (" rios", "")):
        n = n.replace(a, b)
    return n


def _lista(raw: str) -> list[str]:
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def _base(rol: str) -> dict:
    principal = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    if rol == "audio":
        modelos = _lista(os.getenv("AUDIO_OPENROUTER_MODELS", "google/gemini-2.5-flash,google/gemini-2.5-flash-lite"))
        return {"modelo": modelos[0], "respaldo": modelos[1:], "temperatura": 0.0, "max_tokens": 1000}
    if rol == "vision":
        return {"modelo": os.getenv("OPENROUTER_VISION_MODEL", "openai/gpt-4o-mini"), "respaldo": [],
                "temperatura": 0.0, "max_tokens": 800}
    respaldo = _lista(os.getenv("OPENROUTER_FALLBACK_MODELS", "openai/gpt-4o-mini,google/gemini-2.5-flash"))
    return {"modelo": principal, "respaldo": respaldo, "temperatura": 0.7, "max_tokens": 700}


def perfil_activo() -> str:
    p = os.getenv("AI_PERFIL_MODELOS", "base").strip().lower()
    return p if p in ("base", "recomendado") else "base"


def _overrides() -> dict:
    raw = os.getenv("AI_MODELOS_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"[ModelPolicy] AI_MODELOS_JSON inválido: {e}")
        return {}


def _cruda(agente: str, perfil: str) -> tuple[str, dict]:
    a = _norm(agente)
    rol = ROL_POR_AGENTE.get(a, "ventas" if a else "ventas")
    cfg = dict(_base(rol))
    if perfil == "recomendado":
        cfg.update({k: v for k, v in PERFIL_RECOMENDADO.get(rol, {}).items()})
    ov = _overrides()
    for clave in (f"rol:{rol}", a):
        if isinstance(ov.get(clave), dict):
            cfg.update(ov[clave])
    return rol, cfg


def _valido(modelo: str, capacidad: str | None) -> str | None:
    """None si es válido; si no, el motivo. Sin catálogo no se puede validar → válido."""
    from tools import openrouter_catalog as cat
    if not cat.disponible():
        return None
    info = cat.info(modelo)
    if not info:
        return "no existe en el catálogo de OpenRouter"
    if capacidad and info["entradas"] and capacidad not in info["entradas"]:
        return f"no acepta entrada '{capacidad}'"
    return None


def resolver(agente: str, perfil: str | None = None) -> ConfigModelo:
    perfil = perfil or perfil_activo()
    rol, cfg = _cruda(agente, perfil)
    capacidad = CAPACIDAD_POR_ROL.get(rol)
    pedido = str(cfg.get("modelo") or "")
    respaldo = [m for m in (cfg.get("respaldo") or []) if m and m != pedido]
    avisos: list[str] = []

    candidatos = [pedido] + respaldo + [_base(rol)["modelo"]]
    elegido = None
    for m in candidatos:
        motivo = _valido(m, capacidad)
        if motivo is None:
            elegido = m
            break
        avisos.append(f"{m}: {motivo}")
    if elegido is None:
        elegido = pedido or _base(rol)["modelo"]
        avisos.append("ningún modelo validó; se usa el configurado")
    from tools import openrouter_catalog as cat
    if not cat.disponible():
        avisos.append("catálogo de OpenRouter no disponible: modelos sin validar")

    return ConfigModelo(
        agente=agente, rol=rol, modelo=elegido,
        respaldo=[m for m in respaldo if m != elegido and _valido(m, capacidad) is None],
        temperatura=float(cfg.get("temperatura", 0.7)), max_tokens=int(cfg.get("max_tokens", 700)),
        configurado=pedido, avisos=avisos,
    )


AGENTES = ["maximo", "aurora", "tomas", "valentina", "camila", "nicolas", "luciano", "mateo",
           "renata", "bruno", "ezequiel", "elena", "ignacio", "sebastian", "daniela", "franco",
           "valentin", "transcripcion", "vision"]


def tabla() -> list[dict]:
    """Configuración efectiva por agente con precios del catálogo."""
    from tools import openrouter_catalog as cat
    filas = []
    for a in AGENTES:
        c = resolver(a)
        precio = cat.precio_por_millon(c.modelo)
        info = cat.info(c.modelo) or {}
        filas.append({
            "agente": a, "rol": c.rol, "modelo": c.modelo, "configurado": c.configurado,
            "respaldo": c.respaldo, "temperatura": c.temperatura, "max_tokens": c.max_tokens,
            "usd_por_millon_in_out": [round(precio[0], 4), round(precio[1], 4)] if precio else None,
            "contexto": info.get("contexto"), "avisos": c.avisos,
        })
    return filas


def comparar_perfiles(uso_por_agente: dict[str, dict]) -> dict:
    """
    Costo del día si los mismos tokens consumidos hoy se hubieran procesado con cada perfil.
    Usa precios del catálogo; los modelos sin precio se informan aparte.
    """
    from tools import openrouter_catalog as cat
    out = {}
    for perfil in ("base", "recomendado"):
        total, sin_precio = 0.0, set()
        for agente, u in (uso_por_agente or {}).items():
            modelo = resolver(agente, perfil).modelo
            precio = cat.precio_por_millon(modelo)
            if not precio:
                sin_precio.add(modelo)
                continue
            total += (u.get("tokens_in", 0) * precio[0] + u.get("tokens_out", 0) * precio[1]) / 1_000_000
        out[perfil] = {"usd_dia_estimado": round(total, 4), "modelos_sin_precio": sorted(sin_precio)}
    return out
