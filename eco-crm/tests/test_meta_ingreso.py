"""Formularios Meta: persistencia real en SQLite sin contactar clientes."""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Base
from database.models import Aliado, ConfiguracionSistema, Interaccion, Lead, Usuario
from utils.meta_ingreso import registrar_formulario_meta


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def asesor(db, activo=True):
    user = Usuario(nombre="Asesor", email=f"{db.query(Usuario).count()}@test.invalid",
                   password_hash="test", roles_json='["ASESOR_APERTURA"]', activo=activo)
    db.add(user)
    db.commit()
    return user


def test_distribuye_y_conserva_formulario(db):
    user = asesor(db)
    db.add(Aliado(codigo="AL-1", nombre="Aliado", estado="activo",
                 contrato_firmado=True, password_hash="test"))
    db.commit()
    data = {"meta_lead_id": "123", "telefono": "+549 111", "nombre": "Prueba",
            "form_id": "plan18", "field_data": [{"name": "plan", "values": ["18 pasos"]}]}
    first = registrar_formulario_meta(db, data)
    second = registrar_formulario_meta(db, {**data, "meta_lead_id": "124", "telefono": "222"})
    assert {first.asesor_apertura_id, second.asesor_apertura_id} == {None, user.id}
    assert {first.aliado_codigo, second.aliado_codigo} == {None, "AL-1"}
    assert first.origen == "META_ADS"
    assert "plan18" in first.notas and "18 pasos" in first.notas
    first.notas = "Gestión del asesor"
    first.estado = "CONTACTADO"
    db.commit()
    retry = registrar_formulario_meta(db, {**data, "telefono": "otro"})
    assert retry.id == first.id and retry.estado == "CONTACTADO"
    assert db.query(Lead).count() == 2
    assert db.query(Interaccion).count() == 2


def test_sin_telefono_no_se_pierde_y_no_mezcla_leads(db):
    first = registrar_formulario_meta(db, {"meta_lead_id": "a", "email": "a@test.invalid"})
    second = registrar_formulario_meta(db, {"meta_lead_id": "b"})
    assert first.id != second.id
    assert first.session_id == "meta:a" and first.telefono == ""
    assert "SIN RESPONSABLE" in first.interacciones[0].notas


def test_excluye_inactivos_y_aliados_sin_acceso_o_contrato(db):
    asesor(db, activo=False)
    for codigo, contrato, password in [("AL-1", False, "x"), ("AL-2", True, None)]:
        db.add(Aliado(codigo=codigo, nombre=codigo, estado="activo",
                     contrato_firmado=contrato, password_hash=password))
    db.commit()
    lead = registrar_formulario_meta(db, {"meta_lead_id": "x"})
    assert lead.asesor_apertura_id is None and lead.aliado_codigo is None


def test_respeta_pool_vacio(db):
    asesor(db)
    db.add(ConfiguracionSistema(clave="leads_rr_asesores", valor="[]"))
    db.commit()
    lead = registrar_formulario_meta(db, {"meta_lead_id": "x"})
    assert lead.asesor_apertura_id is None


def test_formulario_de_telefono_existente_asigna_sin_perder_gestion(db):
    user = asesor(db)
    legacy = Lead(nombre="Existente", telefono="549111", session_id="549111",
                  estado="CONTACTADO", notas="Gestión previa")
    db.add(legacy)
    db.commit()
    payload = {"meta_lead_id": "nuevo", "telefono": "549111", "form_id": "plan18",
               "field_data": [{"name": "paso", "values": ["18"]}]}
    lead = registrar_formulario_meta(db, payload)
    assert lead.id == legacy.id and not lead.meta_created
    assert lead.asesor_apertura_id == user.id
    assert lead.notas == "Gestión previa" and lead.estado == "CONTACTADO"
    assert "plan18" in lead.interacciones[0].notas
    # El formulario queda identificado aunque cambien luego ambos teléfonos.
    lead.telefono = "999"
    db.commit()
    retry = registrar_formulario_meta(db, {**payload, "telefono": "888"})
    assert retry.id == lead.id and retry.meta_duplicate_event
    assert db.query(Lead).count() == 1 and db.query(Interaccion).count() == 1


def test_no_cambia_responsable_y_registra_otro_formulario(db):
    user = asesor(db)
    first = registrar_formulario_meta(db, {"meta_lead_id": "1", "telefono": "111"})
    db.add(Aliado(codigo="AL-1", nombre="Aliado", estado="activo",
                 contrato_firmado=True, password_hash="test"))
    db.commit()
    again = registrar_formulario_meta(db, {"meta_lead_id": "2", "telefono": "111"})
    assert again.id == first.id and again.asesor_apertura_id == user.id
    assert db.query(Interaccion).count() == 2
    assert not again.meta_created and not again.meta_duplicate_event


def test_validacion_sin_identidad_y_pool_malformado(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        registrar_formulario_meta(db, {})
    assert exc.value.status_code == 422
    asesor(db)
    db.add(ConfiguracionSistema(clave="leads_rr_asesores", valor='{"1":true}'))
    db.commit()
    lead = registrar_formulario_meta(db, {"meta_lead_id": "x"})
    assert lead.asesor_apertura_id is None


def test_reenvios_simultaneos_no_duplican(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}",
                           connect_args={"timeout": 10, "check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    barrier = Barrier(2)

    def enviar():
        with sessions() as session:
            barrier.wait()
            lead = registrar_formulario_meta(session, {"meta_lead_id": "same", "telefono": "111"})
            return lead.id, lead.meta_created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: enviar(), range(2)))
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    with sessions() as session:
        assert session.query(Lead).count() == 1
        assert session.query(Interaccion).count() == 1
    engine.dispose()


def test_telefono_historico_formateado_conserva_responsable_y_gestion(db):
    user = asesor(db)
    original = Lead(nombre="Existente", telefono="+549 (11) 1234-5678",
                    session_id="legacy", estado="EN_SEGUIMIENTO",
                    asesor_apertura_id=user.id, notas="Llamar el martes")
    db.add(original)
    db.commit()
    lead = registrar_formulario_meta(db, {"meta_lead_id": "historico", "telefono": "5491112345678"})
    assert lead.id == original.id and not lead.meta_created
    assert lead.telefono == "+549 (11) 1234-5678" and lead.session_id == "legacy"
    assert lead.asesor_apertura_id == user.id and lead.estado == "EN_SEGUIMIENTO"
    assert lead.notas == "Llamar el martes" and db.query(Lead).count() == 1
    # No se inventa equivalencia entre los prefijos 54 y 549.
    otro = registrar_formulario_meta(db, {"meta_lead_id": "otro", "telefono": "541112345678"})
    assert otro.id != original.id
