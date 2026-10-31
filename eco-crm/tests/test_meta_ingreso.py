"""Recepción Meta durable y reparto round robin con controles comerciales."""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Base
from database.models import (Aliado, ConfiguracionSistema, Interaccion, Lead, Usuario,
    MetaLeadCampana, MetaLeadDestino, MetaLeadOrganizacion, MetaLeadRecepcion)
from utils.meta_ingreso import registrar_formulario_meta, repartir_pendientes, seed_campanas_meta


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as session:
        yield session
    engine.dispose()


def campaign(db, form="plan18", producto="MODULO", activa=True):
    item = MetaLeadCampana(form_id=form, page_id="page1", nombre=form, producto=producto, activa=activa)
    db.add(item)
    db.commit()
    return item


def advisor(db, *, activo=True, enable=True, modulos=True, piscinas=False):
    user = Usuario(nombre="Asesor", email=f"{db.query(Usuario).count()}@test.invalid", activo=activo,
                   password_hash="test", roles_json='["ASESOR_APERTURA"]')
    db.add(user)
    db.flush()
    if enable:
        db.add(MetaLeadDestino(clave=f"asesor:{user.id}", habilitado=True, modulos=modulos, piscinas=piscinas))
    db.commit()
    return user


def partner(db, codigo="AL-1", *, org=None, organizer=False, enable=True, modulos=True,
            piscinas=False, estado="activo", password="test", contrato=False):
    item = Aliado(codigo=codigo, nombre=codigo, estado=estado, password_hash=password,
                  contrato_firmado=contrato, organizacion_codigo=org, es_organizador=organizer)
    db.add(item)
    if enable:
        db.add(MetaLeadDestino(clave=f"aliado:{codigo}", habilitado=True, modulos=modulos, piscinas=piscinas))
    db.commit()
    return item


def incoming(db, numero, *, form="plan18", telefono=None, **kwargs):
    return registrar_formulario_meta(db, {"meta_lead_id": str(numero), "form_id": form,
        "telefono": telefono if telefono is not None else f"54911{numero}", **kwargs})


def test_round_robin_real_ciclo_aunque_carga_es_desigual(db):
    campaign(db)
    a, b = advisor(db), advisor(db)
    # La carga histórica no cambia turnos: un round robin no elige menor carga.
    db.add_all([Lead(nombre="Histórico", telefono=f"old-{i}", estado="CONTACTADO", asesor_apertura_id=a.id)
                for i in range(10)])
    db.commit()
    ids = [incoming(db, i).asesor_apertura_id for i in range(1, 7)]
    assert ids == [a.id, b.id, a.id, b.id, a.id, b.id]


def test_cada_producto_y_campana_tiene_su_pool_y_cursor(db):
    campaign(db)
    campaign(db, "pool", "PISCINA")
    a = advisor(db)
    b = advisor(db)
    piscina = partner(db, modulos=False, piscinas=True)
    assert incoming(db, 1).asesor_apertura_id == a.id
    assert incoming(db, 2, form="pool").aliado_codigo == piscina.codigo
    assert incoming(db, 3).asesor_apertura_id == b.id
    assert incoming(db, 4, form="pool").aliado_codigo == piscina.codigo
    assert incoming(db, 5).producto_interes == "MODULO"


def test_off_inactivo_sin_cuenta_y_usuario_duplicado_no_reciben(db):
    campaign(db)
    advisor(db, enable=False)
    advisor(db, activo=False)
    partner(db, "AL-1", enable=False)
    partner(db, "AL-2", estado="suspendido")
    partner(db, "AL-3", password=None)
    member = partner(db, "AL-4", enable=False)
    user = advisor(db)
    user.aliado_codigo = member.codigo
    db.commit()
    lead = incoming(db, 1)
    assert lead.asesor_apertura_id is None and lead.aliado_codigo is None
    assert "SIN RESPONSABLE" in lead.interacciones[-1].notas
    assert db.query(MetaLeadRecepcion).count() == 1


def test_activo_sin_contrato_puede_trabajar_leads_sin_cambiar_contrato(db):
    campaign(db)
    p = partner(db, contrato=False)
    assert incoming(db, 1).aliado_codigo == p.codigo
    assert not p.contrato_firmado


def test_org_gate_afecta_miembros_y_organizador_sin_afectar_otras_orgs(db):
    c = campaign(db)
    org = partner(db, "AL-010", organizer=True)
    member = partner(db, "AL-011", org=org.codigo)
    other = partner(db, "AL-020", organizer=True)
    partner(db, "AL-021", org=other.codigo)
    db.add(MetaLeadOrganizacion(form_id=c.form_id, organizacion_codigo=org.codigo, habilitada=True))
    db.commit()
    assigned = [incoming(db, i).aliado_codigo for i in range(1, 5)]
    assert assigned == [org.codigo, member.codigo, org.codigo, member.codigo]
    db.get(MetaLeadOrganizacion, (c.form_id, org.codigo)).habilitada = False
    db.commit()
    assert incoming(db, 5).aliado_codigo is None
    # Las gestiones anteriores siguen asignadas tras pausar la organización.
    assert db.query(Lead).filter(Lead.aliado_codigo == member.codigo).count() == 2


def test_campaign_unknown_inactiva_page_incorrecta_guardan_pendiente(db):
    campaign(db, activa=False)
    advisor(db)
    for num, kwargs in [(1, {}), (2, {"form": "unknown"}), (3, {"page_id": "otra"})]:
        lead = incoming(db, num, **kwargs)
        assert lead.asesor_apertura_id is None
    db.get(MetaLeadCampana, "plan18").activa = True
    db.commit()
    result = repartir_pendientes(db)
    assert result["asignados"] == 1  # sólo el evento con página/formulario válidos
    assert result["pendientes"] == 2


def test_toggle_on_drena_pendientes_y_pausa_no_reasigna_existentes(db):
    campaign(db)
    a, b = advisor(db, enable=False), advisor(db, enable=False)
    first, second, third = [incoming(db, i) for i in range(1, 4)]
    db.add_all([MetaLeadDestino(clave=f"asesor:{u.id}", habilitado=True, modulos=True) for u in (a,b)])
    db.commit()
    result = repartir_pendientes(db, "plan18")
    assert result["asignados"] == 3
    assert [db.get(Lead, x.id).asesor_apertura_id for x in (first, second, third)] == [a.id, b.id, a.id]
    db.get(MetaLeadDestino, f"asesor:{a.id}").habilitado = False
    db.commit()
    assert incoming(db, 4).asesor_apertura_id == b.id
    assert first.asesor_apertura_id == a.id
    assert repartir_pendientes(db)["asignados"] == 0


def test_reenvio_tras_gestion_conserva_responsable_y_no_consume_turno(db):
    campaign(db)
    a,b = advisor(db),advisor(db)
    first = incoming(db, 1, field_data=[{"name":"plan","values":["18 pasos"]}])
    first.notas = "Gestión del asesor"
    first.estado = "CONTACTADO"
    first.telefono = "editado"
    db.commit()
    count = db.query(Interaccion).count()
    retry = incoming(db, 1, telefono="otro")
    assert retry.id == first.id and retry.meta_duplicate_event and not retry.meta_created
    assert retry.estado == "CONTACTADO" and retry.notas == "Gestión del asesor"
    assert db.query(Interaccion).count() == count
    assert incoming(db, 2).asesor_apertura_id == b.id


def test_nuevo_formulario_mismo_telefono_preserva_gestion_y_guarda_evidencia(db):
    campaign(db)
    a = advisor(db)
    original = Lead(nombre="Histórico", telefono="+549 (11) 1234-5678", session_id="legacy",
                    estado="EN_SEGUIMIENTO", asesor_apertura_id=a.id, notas="Llamar martes")
    db.add(original)
    db.commit()
    lead = incoming(db, 1, telefono="5491112345678", field_data=[{"name":"plan","values":["18"]}])
    assert lead.id == original.id and not lead.meta_created
    assert lead.telefono == "+549 (11) 1234-5678" and lead.notas == "Llamar martes"
    assert lead.estado == "EN_SEGUIMIENTO" and lead.asesor_apertura_id == a.id
    assert db.query(MetaLeadRecepcion).count() == 1
    assert '"18"' in db.query(MetaLeadRecepcion).first().datos_json


def test_no_reparte_historia_gestionada_sin_responsable(db):
    campaign(db)
    advisor(db)
    legacy = Lead(nombre="Existente", telefono="54911", estado="CONTACTADO", notas="Gestión previa")
    db.add(legacy)
    db.commit()
    lead = incoming(db, 1, telefono="54911")
    assert lead.id == legacy.id and lead.asesor_apertura_id is None
    assert repartir_pendientes(db)["asignados"] == 0
    assert lead.estado == "CONTACTADO" and lead.notas == "Gestión previa"


def test_sin_telefono_no_mezcla_y_sin_identidad_rechaza(db):
    from fastapi import HTTPException
    first = incoming(db, 1, telefono="")
    second = incoming(db, 2, telefono="")
    assert first.id != second.id and first.telefono == ""
    with pytest.raises(HTTPException) as error:
        registrar_formulario_meta(db,{})
    assert error.value.status_code == 422


def test_seed_no_habilita_destinatarios_ni_pisa_pausa_admin(db):
    seed_campanas_meta(db)
    db.commit()
    campana=db.get(MetaLeadCampana,"1122869520123560")
    assert campana.producto=="MODULO" and campana.activa
    campana.activa=False
    db.commit()
    seed_campanas_meta(db)
    db.commit()
    assert not campana.activa
    assert db.query(MetaLeadDestino).count()==0


def test_reenvios_simultaneos_no_duplican(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}",
                           connect_args={"timeout": 10, "check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine, autoflush=False)
    with sessions() as db:
        campaign(db)
        advisor(db)
    barrier=Barrier(2)
    def enviar():
        with sessions() as session:
            barrier.wait()
            lead=incoming(session,1)
            return lead.id,lead.meta_created
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:enviar(),range(2)))
    assert results[0][0]==results[1][0]
    assert sorted(result[1] for result in results)==[False,True]
    with sessions() as db:
        assert db.query(Lead).count()==1
        assert db.query(MetaLeadRecepcion).count()==1
        assert db.query(Interaccion).count()==2
    engine.dispose()


def test_scheduler_org_no_salta_turnos_globales(db):
    c=campaign(db)
    org=partner(db,"AL-010",organizer=True)
    a=advisor(db)
    db.add(MetaLeadOrganizacion(form_id=c.form_id,organizacion_codigo=org.codigo,habilitada=False))
    db.get(MetaLeadDestino,f"asesor:{a.id}").habilitado=False
    db.commit()
    first,second=incoming(db,1),incoming(db,2)
    db.get(MetaLeadOrganizacion,(c.form_id,org.codigo)).habilitada=True
    db.get(MetaLeadDestino,f"asesor:{a.id}").habilitado=True
    # Igual que producción, los toggles aún no están confirmados al drenar.
    result=repartir_pendientes(db,organizacion_codigo=org.codigo)
    assert result["asignados"]==2 and result["asignados_organizacion"]==1
    assert first.aliado_codigo==org.codigo
    assert second.asesor_apertura_id==a.id


def test_pendientes_desconocidos_no_bloquean_campana_habilitada(db):
    campaign(db)
    a=advisor(db,enable=False)
    for i in range(1,4):
        incoming(db,i,form="unknown")
    valid=incoming(db,4)
    db.add(MetaLeadDestino(clave=f"asesor:{a.id}",habilitado=True,modulos=True))
    db.commit()
    result=repartir_pendientes(db,limite=1)
    assert result["asignados"]==1 and result["total"]==4 and result["pendientes"]==3
    assert valid.asesor_apertura_id==a.id


def test_migracion_crea_esquema_semilla_y_defaults_off():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    engine=create_engine("sqlite://")
    legacy=[t for name,t in Base.metadata.tables.items() if not name.startswith("meta_lead_")]
    Base.metadata.create_all(engine,tables=legacy)
    spec=importlib.util.spec_from_file_location("reparto_migration",
        Path(__file__).resolve().parents[1]/"migrations/versions/0038_meta_lead_reparto.py")
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        with sessionmaker(bind=connection)() as session:
            assert session.get(MetaLeadCampana,"1122869520123560").producto=="MODULO"
            session.execute(MetaLeadDestino.__table__.insert().values(clave="asesor:99"))
            session.flush()
            preference=session.get(MetaLeadDestino,"asesor:99")
            assert preference.habilitado is False and preference.modulos is False and preference.piscinas is False
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert not any(n.startswith("meta_lead_") for n in inspect(connection).get_table_names())
    engine.dispose()


def test_cuenta_tecnica_no_recibe_aunque_tenga_preferencia_activa(db):
    campaign(db)
    user=advisor(db)
    user.es_agente_ia=True
    db.commit()
    lead=incoming(db,1)
    assert lead.asesor_apertura_id is None


def test_claudia_conserva_gate_de_su_org_aunque_falte_flag_organizador(db):
    c=campaign(db)
    claudia=partner(db,"AL-010",organizer=False)
    assert incoming(db,1).aliado_codigo is None
    db.add(MetaLeadOrganizacion(form_id=c.form_id,organizacion_codigo=claudia.codigo,habilitada=True))
    db.commit()
    assert incoming(db,2).aliado_codigo==claudia.codigo


def test_campana_creada_despues_clasifica_pendiente_al_repartir(db):
    a=advisor(db)
    lead=incoming(db,1,form="nueva")
    assert lead.producto_interes=="SIN_DEFINIR"
    campaign(db,"nueva","PISCINA")
    db.get(MetaLeadDestino,f"asesor:{a.id}").piscinas=True
    db.commit()
    assert repartir_pendientes(db,"nueva")["asignados"]==1
    assert lead.producto_interes=="PISCINA"
