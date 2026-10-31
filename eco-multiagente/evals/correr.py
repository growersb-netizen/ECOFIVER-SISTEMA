"""
Runner de evaluaciones por puesto.

    python -m evals.correr                 # solo valida los casos (sin modelo, gratis)
    python -m evals.correr --ejecutar      # llama al modelo real: TIENE COSTO

--ejecutar exige OPENROUTER_API_KEY y nunca se corre en CI ni en tests. Los
agentes se instancian sin CRM: las acciones [CRM_ACTION] NO se ejecutan, solo se
inspecciona el texto de la respuesta.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys

from evals.casos import CASOS
from evals.verificar import verificar


async def _responder(caso: dict) -> str:
    mod = importlib.import_module(f"agents.{caso['agente']}")
    agente = mod.get_agent()
    return await agente.respond(caso["mensaje"], caso.get("contexto", ""))


async def principal(ejecutar: bool, solo: str | None) -> int:
    casos = [c for c in CASOS if not solo or c["agente"] == solo]
    if not ejecutar:
        print(f"{len(casos)} casos válidos. Usá --ejecutar para correrlos contra el modelo (tiene costo).")
        return 0
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Falta OPENROUTER_API_KEY: no se ejecuta nada.")
        return 2
    resultados = []
    for c in casos:
        try:
            r = await _responder(c)
            fallas = verificar(c, r)
        except Exception as e:                      # el error del modelo es un resultado, no un crash
            r, fallas = "", [f"error: {e}"]
        resultados.append({"id": c["id"], "agente": c["agente"], "ok": not fallas, "fallas": fallas})
        print(("✅" if not fallas else "❌"), c["id"], *fallas)
    ok = sum(x["ok"] for x in resultados)
    print(f"\n{ok}/{len(resultados)} casos OK")
    print(json.dumps(resultados, ensure_ascii=False, indent=1), file=sys.stderr)
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ejecutar", action="store_true")
    ap.add_argument("--agente")
    a = ap.parse_args()
    sys.exit(asyncio.run(principal(a.ejecutar, a.agente)))
