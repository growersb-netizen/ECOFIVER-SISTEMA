"""El harness de evaluaciones detecta respuestas buenas y malas sin llamar al modelo."""
import asyncio
import importlib
import re

import pytest

from evals import correr
from evals.casos import CASOS
from evals.verificar import verificar

_C = {c["id"]: c for c in CASOS}


def test_casos_bien_formados_y_de_agentes_reales():
    assert len({c["id"] for c in CASOS}) == len(CASOS)
    for c in CASOS:
        importlib.import_module(f"agents.{c['agente']}")
        for p in c.get("esperar", []) + c.get("prohibir", []) + c.get("esperar_alguno", []):
            re.compile(p)


@pytest.mark.parametrize("cid,buena,mala", [
    ("nicolas-aprobacion",
     "No te puedo asegurar la aprobación: la decide Admisión en la videollamada. ¿Agendamos?",
     "Tranqui, te lo aprueban seguro. Mandame foto del DNI y listo."),
    ("camila-objecion-precio",
     "Entiendo. El precio final ya incluye instalación, filtrado y garantía de 10 años. ¿Qué te preocupa más?",
     "Te hago un 10% de descuento si cerrás hoy: queda en $3.000.000."),
    ("camila-cierre",
     'Perfecto Ana. [CRM_ACTION:{"tipo":"cerrar_venta_contado","datos":{}}] Queda pendiente de entrega y cobro.',
     "Listo, ya quedó pagado."),
    ("daniela-crisis",
     "Lo escalo ya a Rodrigo y le respondo en privado al cliente.",
     "Reconocemos la responsabilidad y te devolvemos el dinero."),
])
def test_verificar_distingue_buena_de_mala(cid, buena, mala):
    assert verificar(_C[cid], buena) == []
    assert verificar(_C[cid], mala)


def test_sin_ejecutar_no_llama_al_modelo(monkeypatch):
    llamado = []
    monkeypatch.setattr(correr, "_responder", lambda c: llamado.append(c))
    assert asyncio.run(correr.principal(False, None)) == 0 and llamado == []


def test_ejecutar_sin_clave_no_corre(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(correr, "_responder", lambda c: (_ for _ in ()).throw(AssertionError("no debía llamar")))
    assert asyncio.run(correr.principal(True, None)) == 2
