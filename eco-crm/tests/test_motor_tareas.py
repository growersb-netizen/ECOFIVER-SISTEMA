"""Motor de tareas (Fase 1): persistencia, lease, reintentos, cancelación, delegación y aprobaciones."""
import os
import sys
import threading
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import AprobacionAccion, ComandoAgente, TareaEvento, Usuario
from routers import auth, tareas
from utils import motor_tareas as motor

SECRET = "secreto-de-prueba-motor-" + "x" * 16
KEY = "clave-servicio-motor"
H = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setenv("API_KEY", KEY)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add_all([
        Usuario(id=1, nombre="Rodrigo", email="r@t", password_hash="x", roles_json='["ADMIN"]', activo=True),
        Usuario(id=2, nombre="Vendedor", email="v@t", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True),
        Usuario(id=3, nombre="Agentes IA", email="ia@t", password_hash="x", roles_json='["ADMIN"]', activo=True,
                es_agente_ia=True),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(tareas.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    tok = lambda uid: {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)})}"}
    yield c, db, tok


def _crear(c, tok, **kw):
    body = {"agente": "aurora", "instruccion": "Analizá la conversión de la semana", **kw}
    r = c.post("/api/tareas", headers=tok(1), json=body)
    assert r.status_code == 200, r.text
    return r.json()["tarea"]


def _reclamar(c, worker="w1", agentes=None):
    return c.post("/api/motor/reclamar", headers=H, json={"worker": worker, "agentes": agentes}).json()["tarea"]


# ── Creación ──────────────────────────────────────────────────────────────────

def test_idempotencia(m):
    c, _, tok = m
    a = _crear(c, tok, clave_idempotencia="orden-123")
    b = c.post("/api/tareas", headers=tok(1), json={"agente": "aurora", "instruccion": "otra cosa",
                                                     "clave_idempotencia": "orden-123"}).json()
    assert b["creada"] is False and b["tarea"]["id"] == a["id"]


@pytest.mark.parametrize("agente", ["valentin", "Dr. Valentín", "inexistente", "pablo"])
def test_agentes_fuera_de_la_empresa_no_reciben_tareas(m, agente):
    c, _, tok = m
    assert c.post("/api/tareas", headers=tok(1), json={"agente": agente, "instruccion": "x"}).status_code == 400


def test_orquestador_se_asigna_a_maximo(m):
    c, _, tok = m
    assert _crear(c, tok, agente="orquestador")["agente"] == "maximo"


def test_comandos_historicos_no_se_ejecutan(m):
    c, db, _ = m
    db.add(ComandoAgente(instruccion="orden vieja", agente_destino="aurora", estado="PENDIENTE"))
    db.add(ComandoAgente(instruccion="orden vieja 2", agente_destino="aurora", estado="ENVIADO"))
    db.commit()
    assert _reclamar(c) is None


# ── Reclamo, resultado, reintentos ────────────────────────────────────────────

def test_ciclo_completo_con_evidencia(m):
    c, db, tok = m
    t = _crear(c, tok)
    r = _reclamar(c)
    assert r["id"] == t["id"] and r["estado"] == "EN_EJECUCION" and r["lease_token"]
    assert _reclamar(c, "w2") is None                                  # nadie más la toma
    ok = c.post(f"/api/motor/tareas/{t['id']}/completar", headers=H,
                json={"lease_token": r["lease_token"], "resultado": {"texto": "Conversión 4,2%"},
                      "evidencia": {"llamadas_ia": 1, "fuentes": ["crm:/api/stats/pipeline"]}, "costo_usd": 0.0012})
    assert ok.json()["estado"] == "COMPLETADO"
    detalle = c.get(f"/api/tareas/{t['id']}", headers=tok(1)).json()
    assert detalle["resultado"]["texto"] == "Conversión 4,2%" and detalle["evidencia"]["llamadas_ia"] == 1
    assert [e["tipo"] for e in detalle["eventos"]] == ["CREADA", "RECLAMADA", "COMPLETADA"]


def test_resultado_con_lease_ajeno_o_vencido_se_rechaza(m):
    c, db, tok = m
    t = _crear(c, tok)
    _reclamar(c)
    r = c.post(f"/api/motor/tareas/{t['id']}/completar", headers=H, json={"lease_token": "otro", "resultado": {}})
    assert r.status_code == 409


def test_reintentos_con_espera_y_luego_fallido(m):
    c, db, tok = m
    t = _crear(c, tok)
    for intento in (1, 2):
        r = _reclamar(c)
        res = c.post(f"/api/motor/tareas/{t['id']}/fallar", headers=H,
                     json={"lease_token": r["lease_token"], "error": "OpenRouter 502"}).json()
        assert res["estado"] == "ERROR"
        assert _reclamar(c) is None                                    # respeta la espera
        db.query(ComandoAgente).filter_by(id=t["id"]).update({"proximo_intento": datetime.utcnow()})
        db.commit()
    r = _reclamar(c)
    res = c.post(f"/api/motor/tareas/{t['id']}/fallar", headers=H,
                 json={"lease_token": r["lease_token"], "error": "OpenRouter 502"}).json()
    assert res["estado"] == "FALLIDO" and _reclamar(c) is None


def test_error_no_reintentable_falla_de_una(m):
    c, _, tok = m
    t = _crear(c, tok)
    r = _reclamar(c)
    res = c.post(f"/api/motor/tareas/{t['id']}/fallar", headers=H,
                 json={"lease_token": r["lease_token"], "error": "agente pausado", "reintentable": False}).json()
    assert res["estado"] == "FALLIDO"


def test_recuperacion_tras_reinicio(m):
    """El proceso murió durante la ejecución: el lease vence y otra ejecución la retoma."""
    c, db, tok = m
    t = _crear(c, tok)
    primero = _reclamar(c, "w-que-murio")
    db.query(ComandoAgente).filter_by(id=t["id"]).update({"lease_hasta": datetime.utcnow() - timedelta(seconds=1)})
    db.commit()
    segundo = _reclamar(c, "w-nuevo")
    assert segundo["id"] == t["id"] and segundo["lease_token"] != primero["lease_token"]
    # El worker viejo ya no puede escribir un resultado
    assert c.post(f"/api/motor/tareas/{t['id']}/completar", headers=H,
                  json={"lease_token": primero["lease_token"], "resultado": {}}).status_code == 409
    eventos = [e.tipo for e in db.query(TareaEvento).filter_by(tarea_id=t["id"])]
    assert "RECUPERADA" in eventos


def test_lease_vencido_sin_intentos_queda_fallido(m):
    c, db, tok = m
    t = _crear(c, tok)
    for _ in range(3):
        _reclamar(c)
        db.query(ComandoAgente).filter_by(id=t["id"]).update({"lease_hasta": datetime.utcnow() - timedelta(seconds=1)})
        db.commit()
    assert _reclamar(c) is None
    db.expire_all()
    assert db.get(ComandoAgente, t["id"]).estado == "FALLIDO"


def test_prioridad_y_filtro_por_agentes_activos(m):
    c, _, tok = m
    normal = _crear(c, tok, agente="aurora")
    urgente = _crear(c, tok, agente="bruno", prioridad="URGENTE")
    assert _reclamar(c, agentes=["aurora"])["id"] == normal["id"]     # bruno pausado: no se toma
    assert _reclamar(c, agentes=[]) is None
    assert _reclamar(c)["id"] == urgente["id"]


# ── Cancelación ───────────────────────────────────────────────────────────────

def test_cancelar_pendiente_y_en_ejecucion(m):
    c, _, tok = m
    a = _crear(c, tok)
    assert c.post(f"/api/tareas/{a['id']}/cancelar", headers=tok(1)).json()["estado"] == "CANCELADO"
    b = _crear(c, tok)
    r = _reclamar(c)
    assert r["id"] == b["id"]
    res = c.post(f"/api/tareas/{b['id']}/cancelar", headers=tok(1)).json()
    assert res["estado"] == "EN_EJECUCION" and res["cancelacion_solicitada"]
    lat = c.post(f"/api/motor/tareas/{b['id']}/latido", headers=H, json={"lease_token": r["lease_token"]}).json()
    assert lat["cancelacion_solicitada"] is True
    fin = c.post(f"/api/motor/tareas/{b['id']}/completar", headers=H,
                 json={"lease_token": r["lease_token"], "resultado": {"texto": "tarde"}}).json()
    assert fin["estado"] == "CANCELADO"


# ── Delegación ────────────────────────────────────────────────────────────────

def _delegar(c, padre, agente, desde, **kw):
    return c.post("/api/motor/delegar", headers=H, json={"padre_id": padre, "agente": agente, "creado_por_agente": desde,
                                                          "instruccion": f"subtarea para {agente}", **kw})


def test_delegacion_valida_y_cancelacion_en_cascada(m):
    c, db, tok = m
    raiz = _crear(c, tok, agente="maximo", instruccion="Mejorar el cierre de contado")
    _reclamar(c)
    hija = _delegar(c, raiz["id"], "aurora", "maximo").json()["tarea"]
    assert (hija["profundidad"], hija["raiz_id"], hija["creado_por"]) == (1, raiz["id"], "maximo")
    assert c.post(f"/api/tareas/{raiz['id']}/cancelar", headers=tok(1)).status_code == 200
    db.expire_all()
    assert db.get(ComandoAgente, hija["id"]).estado == "CANCELADO"


@pytest.mark.parametrize("desde,destino,codigo", [
    ("camila", "luciano", 403),     # una vendedora no delega
    ("aurora", "luciano", 403),     # solo delega quien ejecuta la tarea padre (Máximo)
    ("maximo", "maximo", 400),      # a sí mismo
    ("maximo", "valentin", 400),    # Valentín no es de la empresa
])
def test_delegaciones_no_permitidas(m, desde, destino, codigo):
    c, _, tok = m
    raiz = _crear(c, tok, agente="maximo")
    _reclamar(c)
    assert _delegar(c, raiz["id"], destino, desde).status_code == codigo


def test_no_se_delega_desde_tarea_que_no_esta_en_ejecucion(m):
    c, _, tok = m
    raiz = _crear(c, tok, agente="maximo")
    assert _delegar(c, raiz["id"], "aurora", "maximo").status_code == 409


def test_profundidad_maxima(m):
    c, db, tok = m
    raiz = _crear(c, tok, agente="maximo")
    _reclamar(c)
    n1 = _delegar(c, raiz["id"], "aurora", "maximo").json()["tarea"]
    _reclamar(c, agentes=["aurora"])
    n2 = _delegar(c, n1["id"], "tomas", "aurora").json()["tarea"]
    _reclamar(c, agentes=["tomas"])
    assert _delegar(c, n2["id"], "camila", "tomas").status_code == 409     # profundidad 3


def test_tope_de_subtareas_y_presupuesto(m, monkeypatch):
    c, db, tok = m
    raiz = _crear(c, tok, agente="maximo")
    _reclamar(c)
    for i in range(motor.MAX_TAREAS_POR_RAIZ):
        assert _delegar(c, raiz["id"], "aurora", "maximo", clave_idempotencia=f"k{i}").status_code == 200
    assert _delegar(c, raiz["id"], "aurora", "maximo").status_code == 409
    raiz2 = _crear(c, tok, agente="maximo")
    db.query(ComandoAgente).filter_by(id=raiz2["id"]).update({"costo_usd": 0.6})
    db.commit()
    _reclamar(c, agentes=["maximo"])
    assert _delegar(c, raiz2["id"], "aurora", "maximo").status_code == 409


# ── Aprobaciones ──────────────────────────────────────────────────────────────

def test_accion_sensible_requiere_humano(m):
    c, db, tok = m
    t = _crear(c, tok, agente="maximo")
    _reclamar(c)
    prop = c.post("/api/motor/aprobaciones", headers=H, json={
        "tarea_id": t["id"], "agente": "maximo", "tipo_accion": "contactar_leads_sin_respuesta",
        "datos": {"limite": 10}, "motivo": "12 leads sin respuesta hace 48 h"}).json()["aprobacion"]
    assert prop["estado"] == "PENDIENTE"
    # Ni la API key, ni el usuario técnico de IA, ni un vendedor deciden
    url = f"/api/aprobaciones/{prop['id']}/decidir"
    assert c.post(url, headers=H, json={"aprobar": True}).status_code == 401
    assert c.post(url, headers=tok(3), json={"aprobar": True}).status_code == 403
    assert c.post(url, headers=tok(2), json={"aprobar": True}).status_code == 403
    assert c.post("/api/motor/aprobaciones/reclamar", headers=H).json()["aprobacion"] is None
    assert c.post(url, headers=tok(1), json={"aprobar": True, "comentario": "ok"}).json()["aprobacion"]["estado"] == "APROBADA"
    assert c.post(url, headers=tok(1), json={"aprobar": False}).status_code == 409   # ya decidida
    ap = c.post("/api/motor/aprobaciones/reclamar", headers=H).json()["aprobacion"]
    assert ap["id"] == prop["id"]
    assert c.post("/api/motor/aprobaciones/reclamar", headers=H).json()["aprobacion"] is None   # una sola vez
    fin = c.post(f"/api/motor/aprobaciones/{ap['id']}/resultado", headers=H,
                 json={"lease_token": ap["lease_token"], "ok": True, "resultado": "Contacté 10 leads"}).json()
    assert fin["estado"] == "EJECUTADA"
    tipos = [e.tipo for e in db.query(TareaEvento).filter_by(tarea_id=t["id"])]
    assert {"ACCION_PROPUESTA", "APROBADA", "ACCION_EJECUTADA"} <= set(tipos)


def test_permisos_de_endpoints(m):
    c, _, tok = m
    assert c.post("/api/tareas", headers=H, json={"agente": "aurora", "instruccion": "x"}).status_code == 401
    assert c.post("/api/tareas", headers=tok(2), json={"agente": "aurora", "instruccion": "x"}).status_code == 403
    assert c.post("/api/tareas", headers=tok(3), json={"agente": "aurora", "instruccion": "x"}).status_code == 403
    assert c.post("/api/motor/reclamar", headers=tok(1), json={"worker": "w"}).status_code == 401
    assert c.get("/api/tareas").status_code == 401


PG = os.getenv("PG_TEST_URL")


@pytest.mark.skipif(not PG, reason="requiere PG_TEST_URL (PostgreSQL local, nunca productivo)")
def test_reclamo_concurrente_real_postgres():
    eng = create_engine(PG)
    for t in (ComandoAgente.__table__, TareaEvento.__table__):
        t.drop(eng, checkfirst=True)
    Usuario.__table__.create(eng, checkfirst=True)
    ComandoAgente.__table__.create(eng)
    TareaEvento.__table__.create(eng)
    S = sessionmaker(bind=eng)
    with S() as s:
        for i in range(5):
            motor.crear_tarea(s, agente="aurora", instruccion=f"t{i}")
    barrera, tomadas = threading.Barrier(12), []

    def worker(n):
        with S() as s:
            barrera.wait()
            while True:
                t = motor.reclamar(s, f"w{n}")
                if not t:
                    break
                tomadas.append(t.id)
    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    [h.start() for h in hilos]; [h.join() for h in hilos]
    assert sorted(tomadas) == sorted(set(tomadas)) and len(tomadas) == 5
    for t in (TareaEvento.__table__, ComandoAgente.__table__):
        t.drop(eng)
