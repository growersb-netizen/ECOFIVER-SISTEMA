"""Controles de participación y campañas del reparto Meta."""
import json
import re
from dataclasses import dataclass
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    Aliado, AuditLog, Lead, MetaPagina, Usuario,
    MetaLeadCampana, MetaLeadDestino, MetaLeadOrganizacion, MetaLeadRecepcion,
)
from routers import auth
from utils import sesiones

router = APIRouter(prefix="/api/reparto-meta", tags=["Reparto Meta"])


@dataclass
class RepartoActor:
    nombre: str
    usuario_id: Optional[int] = None
    aliado_codigo: Optional[str] = None
    organizacion_codigo: Optional[str] = None
    global_admin: bool = False


def _actor_socio(socio: Aliado, usuario_id=None):
    # La restricción de Claudia tiene precedencia incluso sobre es_admin_crm.
    if socio.codigo == "AL-010":
        return RepartoActor(socio.nombre, usuario_id, socio.codigo, socio.codigo)
    if socio.es_admin_crm:
        return RepartoActor(socio.nombre, usuario_id, socio.codigo, global_admin=True)
    if socio.es_organizador:
        return RepartoActor(socio.nombre, usuario_id, socio.codigo, socio.codigo)
    raise HTTPException(403, "No tenés permisos para administrar el reparto")


def require_reparto_actor(request: Request, db: Session = Depends(get_db)):
    bearer = request.headers.get("Authorization", "")
    token = bearer[7:].strip() if bearer.startswith("Bearer ") else None
    # Una sesión explícita del panel de socios no se confunde con un Usuario
    # que casualmente tenga el mismo ID, ni con otra cookie CRM coexistente.
    token = token or request.cookies.get("socio_token") or request.cookies.get("access_token")
    if not token or not auth.SECRET_KEY:
        raise HTTPException(401, "No autenticado")
    # Contrato central (utils/sesiones.py): cada clase con su audiencia; un token
    # de socio nunca se interpreta como Usuario ni al revés.
    claims_socio = sesiones.validar(token, "socio", auth.SECRET_KEY)
    if claims_socio:
        socio = db.query(Aliado).filter_by(id=int(claims_socio["sub"]), estado="activo").first()
        if not socio:
            raise HTTPException(401, "Sesión inválida")
        return _actor_socio(socio)
    claims = sesiones.validar(token, "crm", auth.SECRET_KEY)
    if not claims:
        raise HTTPException(401, "Sesión inválida")
    identity = int(claims["sub"])
    user = db.query(Usuario).filter_by(id=identity, activo=True).first()
    if not user:
        raise HTTPException(401, "Sesión inválida")
    # Las sesiones históricas del SSO admin no guardaban aliado_codigo.
    # La identidad interna reservada también identifica a Claudia en esos JWT
    # ya emitidos; se obtiene del Usuario autenticado, nunca del body o claims.
    if (user.aliado_codigo == "AL-010" or
            (user.email or "").strip().lower() == "socio.admin.al010@ecofiver.crm"):
        socio = db.query(Aliado).filter_by(codigo="AL-010", estado="activo").first()
        if not socio:
            raise HTTPException(403, "Organización no disponible")
        return _actor_socio(socio, user.id)
    if "ADMIN" in auth.get_user_roles(user):
        return RepartoActor(user.nombre, user.id, user.aliado_codigo, global_admin=True)
    if user.aliado_codigo:
        socio = db.query(Aliado).filter_by(codigo=user.aliado_codigo, estado="activo").first()
        if socio:
            return _actor_socio(socio, user.id)
    raise HTTPException(403, "No tenés permisos para administrar el reparto")


def _global(actor):
    if not actor.global_admin:
        raise HTTPException(403, "Esta acción requiere administración global")


def _org_scope(actor, codigo):
    if not actor.global_admin and actor.organizacion_codigo != codigo:
        raise HTTPException(403, "La organización está fuera de tu alcance")


def _destino(db, clave, actor):
    if clave.startswith("aliado:"):
        codigo = clave.removeprefix("aliado:")
        target = db.query(Aliado).filter_by(codigo=codigo).first()
        if not target:
            raise HTTPException(404, "Aliado no encontrado")
        if not actor.global_admin and not (target.codigo == actor.organizacion_codigo or
                                          target.organizacion_codigo == actor.organizacion_codigo):
            raise HTTPException(403, "El vendedor no pertenece a tu organización")
        return target
    if clave.startswith("asesor:"):
        _global(actor)
        raw = clave.removeprefix("asesor:")
        if not raw.isdigit() or str(int(raw)) != raw:
            raise HTTPException(422, "Identificador de asesor inválido")
        target = db.query(Usuario).filter_by(id=int(raw)).first()
        if not target:
            raise HTTPException(404, "Asesor no encontrado")
        if target.es_agente_ia:
            raise HTTPException(422, "Las cuentas técnicas no reciben leads comerciales")
        if target.aliado_codigo:
            raise HTTPException(422, "Este asesor participa mediante su cuenta de aliado")
        if not {"ASESOR_APERTURA", "SUPERVISOR_CIERRE"}.intersection(auth.get_user_roles(target)):
            raise HTTPException(422, "El usuario no tiene un rol de asesor")
        return target
    raise HTTPException(422, "Tipo de destinatario inválido")


def _audit(db, actor, table, key, changes):
    db.add(AuditLog(table_name=table, action="UPDATE", usuario_id=actor.usuario_id,
                    usuario_nombre=f"{actor.nombre} ({actor.aliado_codigo})" if actor.aliado_codigo else actor.nombre,
                    changed_fields=json.dumps({"clave": key, "actor_aliado": actor.aliado_codigo,
                                                "cambios": changes}, ensure_ascii=False)))


def _lock(db):
    from utils.meta_ingreso import _serializar_ingreso
    _serializar_ingreso(db)


def _drain(db, form_id=None, limite=500, organizacion_codigo=None):
    from utils.meta_ingreso import repartir_pendientes
    result = repartir_pendientes(db, form_id=form_id, limite=limite, organizacion_codigo=organizacion_codigo)
    if isinstance(result, dict):
        return result.get("asignados", 0)
    return int(result or 0)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DestinoUpdate(StrictBody):
    habilitado: Optional[StrictBool] = None
    modulos: Optional[StrictBool] = None
    piscinas: Optional[StrictBool] = None


class GateUpdate(StrictBody):
    habilitada: StrictBool


class CampanaBody(StrictBody):
    form_id: str = Field(pattern=r"^[0-9]{1,50}$")
    page_id: str = Field(pattern=r"^[0-9]{1,50}$")
    nombre: str = Field(min_length=1, max_length=150)
    producto: Literal["MODULO", "PISCINA"]
    activa: StrictBool = False


class PendientesBody(StrictBody):
    form_id: Optional[str] = Field(default=None, pattern=r"^[0-9]{1,50}$")
    limite: StrictInt = Field(default=500, ge=1, le=500)


@router.get("")
def configuracion(db: Session = Depends(get_db), actor: RepartoActor = Depends(require_reparto_actor)):
    preferencias = {row.clave: row for row in db.query(MetaLeadDestino).all()}
    campanas = db.query(MetaLeadCampana).order_by(MetaLeadCampana.nombre).all()
    gates = {(row.organizacion_codigo, row.form_id): bool(row.habilitada)
             for row in db.query(MetaLeadOrganizacion).all()}
    aliados = db.query(Aliado)
    if not actor.global_admin:
        aliados = aliados.filter(or_(Aliado.codigo == actor.organizacion_codigo,
                                     Aliado.organizacion_codigo == actor.organizacion_codigo))
    destinatarios = []
    for aliado in aliados.order_by(Aliado.nombre).all():
        clave = f"aliado:{aliado.codigo}"
        pref = preferencias.get(clave)
        activo = aliado.estado == "activo"
        acceso = bool(aliado.password_hash)
        org = aliado.codigo if (aliado.es_organizador or aliado.codigo == "AL-010") else aliado.organizacion_codigo
        destinatarios.append({"clave": clave, "nombre": aliado.nombre, "tipo": "aliado", "codigo": aliado.codigo,
                              "organizacion_codigo": org, "activo": activo,
                              "elegible": activo and acceso,
                              "motivo": "" if activo and acceso else "Inactivo" if not activo else "Sin cuenta de acceso",
                              "habilitado": bool(pref and pref.habilitado), "modulos": bool(pref and pref.modulos),
                              "piscinas": bool(pref and pref.piscinas)})
    if actor.global_admin:
        for user in db.query(Usuario).order_by(Usuario.nombre).all():
            if user.es_agente_ia or user.aliado_codigo or not {"ASESOR_APERTURA", "SUPERVISOR_CIERRE"}.intersection(auth.get_user_roles(user)):
                continue
            clave = f"asesor:{user.id}"
            pref = preferencias.get(clave)
            elegible = bool(user.activo and user.password_hash)
            destinatarios.append({"clave": clave, "nombre": user.nombre, "tipo": "asesor", "codigo": str(user.id),
                                  "organizacion_codigo": None, "activo": bool(user.activo), "elegible": elegible,
                                  "motivo": "" if elegible else "Inactivo o sin cuenta de acceso",
                                  "habilitado": bool(pref and pref.habilitado), "modulos": bool(pref and pref.modulos),
                                  "piscinas": bool(pref and pref.piscinas)})
    org_query = db.query(Aliado).filter(or_(Aliado.es_organizador == True, Aliado.codigo == "AL-010"))
    if not actor.global_admin:
        org_query = org_query.filter(Aliado.codigo == actor.organizacion_codigo)
    organizaciones = [{"codigo": org.codigo, "nombre": org.nombre,
                       "campanas": {camp.form_id: gates.get((org.codigo, camp.form_id), False) for camp in campanas}}
                      for org in org_query.order_by(Aliado.nombre).all()]
    q = db.query(MetaLeadRecepcion).join(Lead, Lead.id == MetaLeadRecepcion.lead_id).filter(
        Lead.asesor_apertura_id.is_(None), or_(Lead.aliado_codigo.is_(None), Lead.aliado_codigo == ""), Lead.estado == "NUEVO")
    if not actor.global_admin:
        permitidas = [camp.form_id for camp in campanas if gates.get((actor.organizacion_codigo, camp.form_id), False)]
        q = q.filter(MetaLeadRecepcion.form_id.in_(permitidas))
    return {"alcance": "global" if actor.global_admin else "organizacion",
            "puede_crear_campanas": actor.global_admin, "puede_repartir_pendientes": actor.global_admin,
            "organizacion_codigo": actor.organizacion_codigo,
            "destinatarios": destinatarios,
            "campanas": [{"form_id": camp.form_id, "page_id": camp.page_id, "nombre": camp.nombre,
                           "producto": camp.producto, "activa": bool(camp.activa),
                           "habilitada_organizacion": gates.get((actor.organizacion_codigo, camp.form_id), False)}
                          for camp in campanas],
            "organizaciones": organizaciones, "pendientes": {"total": q.with_entities(Lead.id).distinct().count()},
            "paginas": [{"page_id": page.page_id, "nombre": page.nombre} for page in
                        db.query(MetaPagina).filter_by(activa=True).order_by(MetaPagina.nombre).all()] if actor.global_admin else []}


@router.patch("/destinos/{clave}")
def actualizar_destino(clave: str, data: DestinoUpdate, db: Session = Depends(get_db),
                       actor: RepartoActor = Depends(require_reparto_actor)):
    target = _destino(db, clave, actor)
    changes = data.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(422, "Indicá al menos un interruptor booleano")
    if any(changes.values()):
        activo = target.estado == "activo" if isinstance(target, Aliado) else target.activo
        if not activo or not target.password_hash:
            raise HTTPException(422, "El vendedor debe estar activo y tener una cuenta de acceso")
    _lock(db)
    pref = db.get(MetaLeadDestino, clave)
    if not pref:
        pref = MetaLeadDestino(clave=clave)
        db.add(pref)
    before = {field: bool(getattr(pref, field)) for field in changes}
    for field, value in changes.items():
        setattr(pref, field, value)
    pref.actualizado_por = actor.aliado_codigo or f"usuario:{actor.usuario_id}"
    _audit(db, actor, "meta_lead_destinos", clave, {k: {"antes": before[k], "despues": v} for k, v in changes.items()})
    db.commit()
    asignados = _drain(db, organizacion_codigo=actor.organizacion_codigo) if any(changes.values()) else 0
    return {"ok": True, "asignados": asignados, "clave": clave, "habilitado": bool(pref.habilitado),
            "modulos": bool(pref.modulos), "piscinas": bool(pref.piscinas)}


@router.patch("/organizaciones/{codigo}/campanas/{form_id}")
def actualizar_organizacion(codigo: str, form_id: str, data: GateUpdate,
                            db: Session = Depends(get_db), actor: RepartoActor = Depends(require_reparto_actor)):
    _org_scope(actor, codigo)
    org = db.query(Aliado).filter_by(codigo=codigo).first()
    if not org or not (org.es_organizador or org.codigo == "AL-010"):
        raise HTTPException(404, "Organización no encontrada")
    if not db.get(MetaLeadCampana, form_id):
        raise HTTPException(404, "Campaña no encontrada")
    if data.habilitada and org.estado != "activo":
        raise HTTPException(422, "La organización está inactiva")
    _lock(db)
    gate = db.get(MetaLeadOrganizacion, (form_id, codigo))
    if not gate:
        gate = MetaLeadOrganizacion(form_id=form_id, organizacion_codigo=codigo)
        db.add(gate)
    before = bool(gate.habilitada)
    gate.habilitada = data.habilitada
    gate.actualizado_por = actor.aliado_codigo or f"usuario:{actor.usuario_id}"
    _audit(db, actor, "meta_lead_organizaciones", f"{form_id}:{codigo}",
           {"habilitada": {"antes": before, "despues": data.habilitada}})
    db.commit()
    return {"ok": True, "asignados": _drain(db, form_id) if data.habilitada else 0,
            "form_id": form_id, "organizacion_codigo": codigo, "habilitada": data.habilitada}


async def _guardar_campana(form_id, data, db, actor, crear):
    _global(actor)
    if not data.nombre.strip():
        raise HTTPException(422, "Ingresá un nombre para la campaña")
    if form_id != data.form_id:
        raise HTTPException(422, "No se puede cambiar el identificador de la campaña")
    if not db.query(MetaPagina).filter_by(page_id=data.page_id, activa=True).first():
        raise HTTPException(422, "Seleccioná una página activa del CRM")
    camp = db.get(MetaLeadCampana, form_id)
    if crear and camp:
        raise HTTPException(409, "El formulario ya está configurado")
    if not crear and not camp:
        raise HTTPException(404, "Campaña no encontrada")
    if data.activa and (camp is None or not camp.activa or camp.page_id != data.page_id):
        pagina = db.query(MetaPagina).filter_by(page_id=data.page_id, activa=True).first()
        await _ensure_page_subscription(db, pagina)
    _lock(db)
    if camp is None:
        camp = MetaLeadCampana(form_id=form_id)
        db.add(camp)
    changes = data.model_dump(exclude={"form_id"})
    before = {field: getattr(camp, field) for field in changes}
    for field, value in changes.items():
        setattr(camp, field, value.strip() if field == "nombre" else value)
    if not camp.nombre:
        raise HTTPException(422, "Ingresá un nombre para la campaña")
    camp.actualizado_por = actor.aliado_codigo or f"usuario:{actor.usuario_id}"
    _audit(db, actor, "meta_lead_campanas", form_id, {k: {"antes": before[k], "despues": v} for k, v in changes.items()})
    db.commit()
    return {"ok": True, "form_id": form_id, "asignados": _drain(db, form_id) if camp.activa else 0}


@router.post("/campanas")
async def crear_campana(data: CampanaBody, db: Session = Depends(get_db),
                  actor: RepartoActor = Depends(require_reparto_actor)):
    return await _guardar_campana(data.form_id, data, db, actor, True)


@router.put("/campanas/{form_id}")
async def actualizar_campana(form_id: str, data: CampanaBody, db: Session = Depends(get_db),
                       actor: RepartoActor = Depends(require_reparto_actor)):
    return await _guardar_campana(form_id, data, db, actor, False)


@router.post("/pendientes")
def distribuir_pendientes(data: PendientesBody, db: Session = Depends(get_db),
                          actor: RepartoActor = Depends(require_reparto_actor)):
    _global(actor)
    # El usuario dispara la cola; la política global decide destinos, sin poder
    # elegir un vendedor ajeno o alterar asignaciones ya existentes.
    asignados = _drain(db, data.form_id, data.limite)
    _audit(db, actor, "meta_lead_recepciones", data.form_id, {"repartir_pendientes": asignados})
    db.commit()
    return {"ok": True, "asignados": asignados}


async def _meta_request(client, method, path, token, params):
    from routers.agentes import _MetaLeadGraphError
    try:
        response = await client.request(method, f"https://graph.facebook.com/v23.0/{path}",
                                        headers={"Authorization": f"Bearer {token}"},
                                        params=params if method == "GET" else None,
                                        data=params if method != "GET" else None)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise _MetaLeadGraphError() from None
    if not isinstance(payload, dict):
        raise _MetaLeadGraphError()
    if response.is_error or payload.get("error"):
        error = payload.get("error") or {}
        raise _MetaLeadGraphError(error.get("code") if isinstance(error, dict) else None)
    return payload


async def _page_operation(db, pagina, operation):
    from routers.agentes import _meta_lead_graph_get, _MetaLeadGraphError
    from routers.configuracion import get_config_value
    token = pagina.page_token
    async with httpx.AsyncClient(timeout=15) as client:
        if token:
            try:
                return await operation(client, token)
            except _MetaLeadGraphError as exc:
                if exc.code != 190:
                    raise
        global_token = get_config_value("meta_page_access_token", db)
        if not global_token:
            raise _MetaLeadGraphError()
        identity = await _meta_lead_graph_get(client, pagina.page_id, "access_token", global_token)
        token = identity.get("access_token")
        if not isinstance(token, str) or not token:
            raise _MetaLeadGraphError()
        db.query(MetaPagina).filter_by(id=pagina.id).update({MetaPagina.page_token: token}, synchronize_session=False)
        db.commit()
        return await operation(client, token)


async def _ensure_page_subscription(db, pagina):
    from routers.agentes import _MetaLeadGraphError
    from routers.redes_sociales import FB_SUBSCRIBED_FIELDS

    async def subscribe(client, token):
        result = await _meta_request(client, "POST", f"{pagina.page_id}/subscribed_apps", token,
                                     {"subscribed_fields": FB_SUBSCRIBED_FIELDS})
        if result.get("success") is not True:
            raise _MetaLeadGraphError()
        return result

    try:
        await _page_operation(db, pagina, subscribe)
    except _MetaLeadGraphError:
        raise HTTPException(503, "No se pudo conectar la campaña a Meta. Reconectá Facebook desde Redes y reintentá; la campaña sigue desactivada.") from None
    db.query(MetaPagina).filter_by(id=pagina.id).update({MetaPagina.webhook_subscribed: True}, synchronize_session=False)
    db.commit()


@router.get("/formularios")
async def formularios(page_id: str, db: Session = Depends(get_db),
                      actor: RepartoActor = Depends(require_reparto_actor)):
    _global(actor)
    if not re.fullmatch(r"[0-9]{1,50}", page_id):
        raise HTTPException(422, "La página debe tener un identificador válido")
    pagina = db.query(MetaPagina).filter_by(page_id=page_id, activa=True).first()
    if not pagina:
        raise HTTPException(404, "Página activa no encontrada")
    from routers.agentes import _MetaLeadGraphError

    async def list_forms(client, token):
        forms, after = [], None
        # Hasta 1000 formularios por página, sin devolver URLs con credenciales.
        for _ in range(10):
            params = {"fields": "id,name,status", "limit": "100"}
            if after:
                params["after"] = after
            result = await _meta_request(client, "GET", f"{page_id}/leadgen_forms", token, params)
            forms.extend({"id": row.get("id"), "name": row.get("name", ""), "status": row.get("status", "")}
                         for row in result.get("data", []) if isinstance(row, dict) and row.get("id"))
            after = result.get("paging", {}).get("cursors", {}).get("after") if result.get("paging", {}).get("next") else None
            if not after:
                break
        return {"forms": forms, "has_more": bool(after)}

    try:
        return await _page_operation(db, pagina, list_forms)
    except _MetaLeadGraphError:
        raise HTTPException(503, "No se pudieron consultar formularios. Reconectá Facebook desde Redes y reintentá.") from None
