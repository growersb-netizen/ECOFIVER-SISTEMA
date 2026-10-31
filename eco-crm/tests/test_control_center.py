"""
Tests del Control Center → multiagente (HTTP 401 post Etapa 0) y del catálogo de agentes.
No llaman al multiagente real: httpx usa un transporte simulado que replica su validación.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base
from database.models import ConfiguracionSistema, ComandoAgente, Usuario
from routers import control_agentes as cc

CLAVE_MULTIAGENTE = "clave-de-prueba-multiagente"
AGENTES_REALES = {"maximo", "aurora", "tomas", "valentina", "camila", "nicolas", "luciano", "mateo",
                  "franco", "ezequiel", "elena", "ignacio", "bruno", "renata", "sebastian", "daniela"}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("MULTIAGENTE_API_KEY", raising=False)
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(ConfiguracionSistema(clave="orquestador_url", valor="https://multiagente.test"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def multiagente(monkeypatch):
    """Simula /api/comando y /api/comando/ping del multiagente (X-Api-Key obligatoria)."""
    recibidos = []

    def handler(request: httpx.Request):
        recibidos.append(request)
        if request.url.path == "/health":  # público, como en el multiagente real
            return httpx.Response(200, json={"status": "ok", "agentes": 16})
        if request.headers.get("X-Api-Key") != CLAVE_MULTIAGENTE:
            return httpx.Response(401, json={"ok": False, "error": "no autorizado"})
        if request.url.path == "/api/comando":
            return httpx.Response(200, json={"ok": True, "recibido": True})
        return httpx.Response(200, json={"ok": True})

    real = httpx.AsyncClient
    monkeypatch.setattr(cc.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return recibidos


def _usuario(db):
    u = Usuario(nombre="Admin", email="admin@test", password_hash="x")
    db.add(u)
    db.commit()
    return u


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _comando(db, user, agente="aurora"):
    return asyncio.run(cc.enviar_comando(
        _Req({"instruccion": "Generar resumen del pipeline", "agente_destino": agente, "tipo": "RAPIDO"}),
        db=db, current_user=user,
    ))


# ─── Credencial ───────────────────────────────────────────────────────────────

class TestCredencial:

    def test_reproduce_401_sin_credencial(self, db, multiagente):
        """Estado de producción: orquestador_api_key vacía → sin X-Api-Key → 401."""
        res = _comando(db, _usuario(db))
        # La orden queda como tarea en cola (no "ENVIADO"); el aviso informa el 401
        assert res["estado"] == "PENDIENTE"
        assert "401" in res["aviso"]
        assert "X-Api-Key" not in multiagente[-1].headers

    def test_env_multiagente_api_key_autentica(self, db, multiagente, monkeypatch):
        monkeypatch.setenv("MULTIAGENTE_API_KEY", CLAVE_MULTIAGENTE)
        res = _comando(db, _usuario(db))
        assert res["estado"] == "PENDIENTE" and res["aviso"] == ""
        assert multiagente[-1].headers["X-Api-Key"] == CLAVE_MULTIAGENTE
        cmd = db.query(ComandoAgente).one()
        assert cmd.http_status == 200 and cmd.agente_destino == "aurora" and cmd.version_motor == 1
        assert json.loads(multiagente[-1].content)["contexto"]["tarea_id"] == cmd.id

    def test_clave_de_configuracion_cifrada_se_descifra(self, db, multiagente, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "clave-de-cifrado-de-prueba")
        from database.encryption import encrypt_value
        cifrada = encrypt_value(CLAVE_MULTIAGENTE)
        assert cifrada != CLAVE_MULTIAGENTE
        db.add(ConfiguracionSistema(clave="orquestador_api_key", valor=cifrada, es_secreto=True))
        db.commit()
        assert cc._get_orquestador_api_key(db) == CLAVE_MULTIAGENTE
        res = _comando(db, _usuario(db))
        assert res["estado"] == "PENDIENTE" and res["aviso"] == ""

    def test_env_tiene_prioridad_sobre_configuracion(self, db, monkeypatch):
        db.add(ConfiguracionSistema(clave="orquestador_api_key", valor="vieja"))
        db.commit()
        monkeypatch.setenv("MULTIAGENTE_API_KEY", "nueva")
        assert cc._get_orquestador_api_key(db) == "nueva"

    def test_credencial_incorrecta_da_mensaje_accionable(self, db, multiagente, monkeypatch):
        monkeypatch.setenv("MULTIAGENTE_API_KEY", "incorrecta")
        res = _comando(db, _usuario(db))
        assert res["estado"] == "PENDIENTE"
        assert "MULTIAGENTE_API_KEY" in res["aviso"]
        assert "incorrecta" not in json.dumps(res)  # nunca se refleja la clave

    def test_status_informa_autenticacion_sin_exponer_clave(self, db, multiagente, monkeypatch):
        user = _usuario(db)
        st = asyncio.run(cc.get_status(db=db, current_user=user))
        assert st["autenticacion_ok"] is False and st["credencial_configurada"] is False
        monkeypatch.setenv("MULTIAGENTE_API_KEY", CLAVE_MULTIAGENTE)
        st = asyncio.run(cc.get_status(db=db, current_user=user))
        assert st["autenticacion_ok"] is True
        assert CLAVE_MULTIAGENTE not in json.dumps(st)

    def test_campo_configuracion_es_secreto(self):
        from routers.configuracion import CONFIG_DEFS
        assert CONFIG_DEFS["orquestador_api_key"]["es_secreto"] is True


# ─── Catálogo ─────────────────────────────────────────────────────────────────

class TestCatalogo:

    def test_catalogo_activo_son_los_agentes_reales(self):
        assert {a["id"] for a in cc.AGENTES_CATALOGO} == AGENTES_REALES

    def test_coincide_con_el_orquestador(self):
        """Cada agente del catálogo existe en eco-multiagente/agents."""
        base = os.path.join(os.path.dirname(__file__), "..", "..", "eco-multiagente", "agents")
        if not os.path.isdir(base):
            pytest.skip("eco-multiagente no está en el checkout")
        for a in cc.AGENTES_CATALOGO:
            assert os.path.isfile(os.path.join(base, f'{a["id"]}.py')), a["id"]

    def test_agentes_anteriores_quedan_como_historicos(self):
        ids_hist = {h["id"] for h in cc.AGENTES_HISTORICOS}
        assert {"pablo", "laura", "gabriel", "carlos", "sabrina"} <= ids_hist
        assert all(h["activo"] is False for h in cc.AGENTES_HISTORICOS)
        assert not ({"pablo", "laura", "gabriel", "carlos", "sabrina"} & {a["id"] for a in cc.AGENTES_CATALOGO})
        nombres = cc._nombres_agentes()
        assert nombres["gabriel"] == "Gabriel (histórico)" and nombres["aurora"] == "Aurora"

    def test_acciones_y_objetivos_apuntan_a_agentes_reales(self):
        for area, lista in cc.ACCIONES_RAPIDAS.items():
            for acc in lista:
                assert acc["agente"] in AGENTES_REALES, (area, acc["id"], acc["agente"])
        assert next(a for a in cc.ACCIONES_RAPIDAS["VENTAS"] if a["id"] == "pipeline_ventas")["agente"] == "aurora"
        textos = json.dumps(cc.ACCIONES_RAPIDAS, ensure_ascii=False) + json.dumps(cc.OBJETIVOS_CEO, ensure_ascii=False)
        for viejo in ("Pablo", "Laura", "Gabriel", "Carlos", "Sabrina", "Marina", "Patricia", "Diego"):
            assert viejo not in textos, viejo
