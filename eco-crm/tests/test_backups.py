"""Backup de PostgreSQL: ida y vuelta exacta, y acceso solo del propietario."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backup
from database.database import Base, get_db
from database.models import Usuario
from routers import auth, backups

SECRET = "secreto-de-prueba-backups-" + "x" * 16


@pytest.fixture
def m(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add_all([Usuario(id=1, nombre="Rodrigo", email="r@t", password_hash="x", roles_json='["ADMIN","PROPIETARIO"]', activo=True),
                Usuario(id=2, nombre="Socio admin", email="s@t", password_hash="x", roles_json='["ADMIN"]', activo=True,
                        aliado_codigo="AL-010")])
    db.commit()
    app = FastAPI()
    app.include_router(backups.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    tok = lambda uid: {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)})}"}
    yield TestClient(app), tok, tmp_path


def test_solo_el_propietario_lista_genera_y_descarga(m, monkeypatch):
    c, tok, d = m
    (d / "eco_crm_pg_20261031_030000.jsonl.gz").write_bytes(b"x" * 2048)

    def falso():
        (d / "eco_crm_pg_20261031_120000.jsonl.gz").write_bytes(b"y")
        return True
    monkeypatch.setattr(backup, "run_backup", falso)
    for h in (tok(2), {}):
        assert c.get("/api/propietario/backups", headers=h).status_code in (401, 403)
        assert c.post("/api/propietario/backups", headers=h).status_code in (401, 403)
        assert c.get("/api/propietario/backups/eco_crm_pg_20261031_030000.jsonl.gz", headers=h).status_code in (401, 403)
    assert [b["nombre"] for b in c.get("/api/propietario/backups", headers=tok(1)).json()["backups"]] == \
        ["eco_crm_pg_20261031_030000.jsonl.gz"]
    assert c.post("/api/propietario/backups", headers=tok(1)).json()["ultimo"] == "eco_crm_pg_20261031_120000.jsonl.gz"
    r = c.get("/api/propietario/backups/eco_crm_pg_20261031_030000.jsonl.gz", headers=tok(1))
    assert r.status_code == 200 and len(r.content) == 2048
    assert c.get("/api/propietario/backups/..%2F..%2Fmain.py", headers=tok(1)).status_code in (400, 404)


@pytest.mark.skipif(not os.getenv("PG_TEST_URL"), reason="requiere PostgreSQL (PG_TEST_URL)")
def test_ida_y_vuelta_exacta_en_postgres(tmp_path):
    """Vuelca una base con el esquema real, restaura en otra vacía y compara todas las tablas."""
    import restaurar_backup_pg as rest
    from sqlalchemy import MetaData
    base = os.environ["PG_TEST_URL"].rsplit("/", 1)[0]
    admin = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as cx:
        for n in ("bk_origen", "bk_destino"):
            cx.execute(text(f"DROP DATABASE IF EXISTS {n}"))
            cx.execute(text(f"CREATE DATABASE {n}"))
    origen = create_engine(base + "/bk_origen")
    import database.models  # noqa: F401
    Base.metadata.create_all(origen)
    with origen.begin() as cx:
        cx.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        cx.execute(text("INSERT INTO alembic_version VALUES ('0045')"))
        cx.execute(text("INSERT INTO usuarios(nombre,email,password_hash,activo,roles_json) VALUES ('Ñandú','n@t','h',true,'[\"ADMIN\"]')"))
        cx.execute(text("INSERT INTO comandos_agente(agente_destino,instruccion,estado,contexto) VALUES ('aurora','x €','PENDIENTE',NULL)"))
        cx.execute(text("INSERT INTO comandos_agente(agente_destino,instruccion,estado,contexto) VALUES ('aurora','y','PENDIENTE','{\"a\": [1]}')"))
    archivo = tmp_path / "eco_crm_pg_20261031_030000.jsonl.gz"
    conteos = backup.volcar_postgres(base + "/bk_origen", archivo)
    assert conteos["usuarios"] == 1 and conteos["comandos_agente"] == 2
    rest.restaurar(str(archivo), base + "/bk_destino", crear_esquema=True)
    with pytest.raises(SystemExit):                                  # nunca encima de datos
        rest.restaurar(str(archivo), base + "/bk_destino")
    destino = create_engine(base + "/bk_destino")
    meta = MetaData()
    meta.reflect(bind=origen)
    for t in meta.sorted_tables:
        q = text(f'SELECT md5(coalesce(string_agg(to_jsonb(x)::text, \'|\' ORDER BY to_jsonb(x)::text), \'\')) FROM "{t.name}" x')
        with origen.connect() as a, destino.connect() as b:
            assert a.execute(q).scalar() == b.execute(q).scalar(), t.name
    with destino.begin() as cx:                                       # las secuencias siguen después del máximo
        assert cx.execute(text("INSERT INTO comandos_agente(agente_destino,instruccion,estado) VALUES ('a','z','PENDIENTE') RETURNING id")).scalar() == 3
    origen.dispose(); destino.dispose()
