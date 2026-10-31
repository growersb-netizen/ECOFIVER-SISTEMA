"""Profesionalización: manual del puesto de los 16 agentes de la empresa (capa 3)."""
import importlib
import re

import pytest

from tools import capas

EMPRESA = ["maximo", "aurora", "tomas", "valentina", "camila", "nicolas", "luciano", "mateo",
           "renata", "bruno", "ezequiel", "elena", "ignacio", "sebastian", "daniela", "franco"]
SECCIONES = ["MISIÓN:", "DOMINIO:", "MODELO DE DECISIÓN", "COLABORACIÓN:", "AUTONOMÍA:", "NO PODÉS:",
             "INDICADORES:", "MEJORA CONTINUA:"]


@pytest.mark.parametrize("agente", EMPRESA)
def test_cada_puesto_tiene_manual_completo_y_acotado(agente):
    capas._reset_para_tests()
    m = capas.manual(agente)
    assert m.startswith("# MANUAL DEL PUESTO —"), agente
    faltan = [s for s in SECCIONES if s not in m]
    assert not faltan, f"{agente}: faltan {faltan}"
    assert len(m) < 3500                                  # costo de tokens acotado por mensaje
    assert not re.search(r"\$\s?\d", m)                   # ningún precio fijo en el manual: precios solo del sistema


def test_valentin_no_tiene_manual_de_empresa():
    assert capas.manual("valentin") == ""
    assert capas.manual("../agents/maximo") == ""          # sin rutas arbitrarias


@pytest.mark.asyncio
@pytest.mark.parametrize("modulo,clase", [("agents.maximo", "Máximo"), ("agents.nicolas", "Nicolás"),
                                          ("agents.sebastian", "Sebastián"), ("agents.tomas", "Tomás")])
async def test_el_manual_entra_en_la_capa_3_debajo_de_seguridad(modulo, clase):
    capas._reset_para_tests()
    texto = await capas.componer(clase, "PROMPT DEL PUESTO")
    i1, i3, ip, im = (texto.index("[CAPA 1"), texto.index("[CAPA 3"), texto.index("PROMPT DEL PUESTO"),
                      texto.index("# MANUAL DEL PUESTO"))
    assert i1 < i3 < ip < im


@pytest.mark.asyncio
async def test_valentin_sigue_sin_capas():
    assert await capas.componer("Valentín", "privado") == "privado"


@pytest.mark.parametrize("agente", EMPRESA + ["valentin"])
def test_todos_los_prompts_compilan(agente):
    """Los prompts f-string fallan al importar si una señal JSON no escapa llaves."""
    importlib.import_module(f"agents.{agente}")


@pytest.mark.parametrize("agente,accion", [("nicolas", "abrir_financiacion"), ("mateo", "abrir_financiacion"),
                                           ("luciano", "cerrar_venta_contado"), ("camila", "cerrar_venta_contado")])
def test_especialistas_conocen_su_accion_de_circuito(agente, accion):
    mod = importlib.import_module(f"agents.{agente}")
    assert f'"tipo":"{accion}"' in mod._SYSTEM_PROMPT
