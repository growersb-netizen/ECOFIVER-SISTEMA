"""
Módulo — Cobranza Histórica (Construsol)
Cartera de cobranza completamente independiente de la de EcoFiver
(ventas_financiadas). No comparte tablas, contadores ni cálculos —
separación exigida explícitamente por el negocio.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ClienteCobranzaHistorica, PagoCobranzaHistorica, Usuario
from routers.auth import require_auth_or_apikey, get_user_roles

router = APIRouter()

LINEAS_VALIDAS = {"viviendas", "piscinas"}


def _require_access(user: Usuario = Depends(require_auth_or_apikey)) -> Usuario:
    roles = get_user_roles(user)
    if "ADMIN" not in roles and "COBRANZAS" not in roles:
        raise HTTPException(403, "Sin permisos para Cobranza Histórica")
    return user


class ClienteCobranzaHistoricaReq(BaseModel):
    linea: str                          # "viviendas" | "piscinas"
    proyecto: Optional[str] = None
    apellido_nombre: str
    telefono: Optional[str] = ""
    dni: Optional[str] = None
    metros_o_modelo: Optional[str] = None
    cantidad_cuotas: Optional[int] = None
    anticipo: Optional[float] = None
    precio_total: Optional[float] = None
    cuota_actual: float = 0
    cac_pct: Optional[float] = None
    notas: Optional[str] = ""


class PagoReq(BaseModel):
    monto: float
    mes_correspondiente: Optional[str] = None
    notas: Optional[str] = ""


def _cliente_dict(c: ClienteCobranzaHistorica) -> dict:
    return {
        "id": c.id,
        "empresa": c.empresa,
        "linea": c.linea,
        "proyecto": c.proyecto or "",
        "apellido_nombre": c.apellido_nombre,
        "telefono": c.telefono or "",
        "dni": c.dni or "",
        "metros_o_modelo": c.metros_o_modelo or "",
        "cantidad_cuotas": c.cantidad_cuotas,
        "anticipo": c.anticipo,
        "precio_total": c.precio_total,
        "cuota_actual": c.cuota_actual or 0,
        "cac_pct": c.cac_pct,
        "estado_plan": c.estado_plan or "ACTIVO",
        "notas": c.notas or "",
        "ultimo_pago": (
            {"monto": c.pagos[-1].monto, "fecha_pago": c.pagos[-1].fecha_pago.isoformat()}
            if c.pagos else None
        ),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/api/cobranza-historica/cartera")
async def get_cartera_historica(
    linea: Optional[str] = None,
    estado_plan: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    q = db.query(ClienteCobranzaHistorica).filter(ClienteCobranzaHistorica.empresa == "construsol")
    if linea:
        q = q.filter(ClienteCobranzaHistorica.linea == linea)
    if estado_plan:
        q = q.filter(ClienteCobranzaHistorica.estado_plan == estado_plan)
    clientes = q.order_by(ClienteCobranzaHistorica.apellido_nombre.asc()).all()
    return [_cliente_dict(c) for c in clientes]


@router.get("/api/cobranza-historica/resumen")
async def get_resumen_historica(
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    """Totales por línea — emitido (cuota vigente total), cobrado del mes, morosos. Nunca se mezcla con EcoFiver."""
    clientes = db.query(ClienteCobranzaHistorica).filter(
        ClienteCobranzaHistorica.empresa == "construsol",
        ClienteCobranzaHistorica.estado_plan != "CANCELADO",
    ).all()

    inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _resumen_linea(linea: str) -> dict:
        items = [c for c in clientes if c.linea == linea]
        emitido = sum(c.cuota_actual or 0 for c in items)
        cobrado_mes = 0.0
        for c in items:
            cobrado_mes += sum(p.monto for p in c.pagos if p.fecha_pago and p.fecha_pago.replace(tzinfo=None) >= inicio_mes)
        morosos = [c for c in items if c.estado_plan == "ATRASADO"]
        return {
            "cantidad_clientes": len(items),
            "emitido_mes": emitido,
            "cobrado_mes": cobrado_mes,
            "pendiente_mes": max(0.0, emitido - cobrado_mes),
            "cantidad_morosos": len(morosos),
            "monto_moroso": sum(c.cuota_actual or 0 for c in morosos),
        }

    return {
        "empresa": "construsol",
        "viviendas": _resumen_linea("viviendas"),
        "piscinas": _resumen_linea("piscinas"),
    }


@router.get("/api/cobranza-historica/morosidad")
async def get_morosidad_historica(
    linea: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    q = db.query(ClienteCobranzaHistorica).filter(
        ClienteCobranzaHistorica.empresa == "construsol",
        ClienteCobranzaHistorica.estado_plan == "ATRASADO",
    )
    if linea:
        q = q.filter(ClienteCobranzaHistorica.linea == linea)
    morosos = q.order_by(ClienteCobranzaHistorica.apellido_nombre.asc()).all()
    return {
        "total_cuentas": len(morosos),
        "total_adeudado": sum(c.cuota_actual or 0 for c in morosos),
        "clientes": [_cliente_dict(c) for c in morosos],
    }


@router.post("/api/cobranza-historica/clientes", status_code=201)
async def crear_cliente_historico(
    body: ClienteCobranzaHistoricaReq,
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    if body.linea not in LINEAS_VALIDAS:
        raise HTTPException(400, f"linea debe ser una de: {sorted(LINEAS_VALIDAS)}")
    cliente = ClienteCobranzaHistorica(
        empresa="construsol",
        linea=body.linea,
        proyecto=body.proyecto,
        apellido_nombre=body.apellido_nombre,
        telefono=body.telefono or "",
        dni=body.dni,
        metros_o_modelo=body.metros_o_modelo,
        cantidad_cuotas=body.cantidad_cuotas,
        anticipo=body.anticipo,
        precio_total=body.precio_total,
        cuota_actual=body.cuota_actual or 0,
        cac_pct=body.cac_pct,
        notas=body.notas or "",
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return _cliente_dict(cliente)


@router.put("/api/cobranza-historica/clientes/{cliente_id}")
async def actualizar_cliente_historico(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    cliente = db.query(ClienteCobranzaHistorica).filter(
        ClienteCobranzaHistorica.id == cliente_id, ClienteCobranzaHistorica.empresa == "construsol",
    ).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    body = await request.json()
    campos_editables = (
        "linea", "proyecto", "apellido_nombre", "telefono", "dni", "metros_o_modelo",
        "cantidad_cuotas", "anticipo", "precio_total", "cuota_actual", "cac_pct",
        "estado_plan", "notas",
    )
    for campo in campos_editables:
        if campo in body:
            setattr(cliente, campo, body[campo])
    db.commit()
    db.refresh(cliente)
    return _cliente_dict(cliente)


@router.post("/api/cobranza-historica/clientes/{cliente_id}/pago")
async def registrar_pago_historico(
    cliente_id: int,
    body: PagoReq,
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    cliente = db.query(ClienteCobranzaHistorica).filter(
        ClienteCobranzaHistorica.id == cliente_id, ClienteCobranzaHistorica.empresa == "construsol",
    ).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    if body.monto <= 0:
        raise HTTPException(400, "monto debe ser mayor a 0")

    pago = PagoCobranzaHistorica(
        cliente_id=cliente.id, monto=body.monto,
        mes_correspondiente=body.mes_correspondiente, notas=body.notas or "",
    )
    db.add(pago)
    if cliente.estado_plan == "ATRASADO":
        cliente.estado_plan = "ACTIVO"
    db.commit()
    db.refresh(cliente)
    return {"ok": True, "cliente": _cliente_dict(cliente)}


@router.post("/api/cobranza-historica/aplicar-icac")
async def aplicar_icac_historico(
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(_require_access),
):
    """
    Indexación mensual por ICAC para Construsol — por defecto solo aplica a
    "viviendas" (las piscinas de Construsol no indexan por CAC, según los
    datos reales de la cartera). cuota_nueva = cuota_actual × (1 + pct/100).
    """
    body = await request.json()
    pct = float(body.get("pct") or 0)
    linea = body.get("linea", "viviendas")
    if pct <= 0:
        raise HTTPException(400, "pct debe ser mayor a 0")
    if linea not in LINEAS_VALIDAS:
        raise HTTPException(400, f"linea debe ser una de: {sorted(LINEAS_VALIDAS)}")

    clientes = db.query(ClienteCobranzaHistorica).filter(
        ClienteCobranzaHistorica.empresa == "construsol",
        ClienteCobranzaHistorica.linea == linea,
        ClienteCobranzaHistorica.estado_plan != "CANCELADO",
    ).all()

    ahora = datetime.now()
    afectados = []
    for c in clientes:
        anterior = c.cuota_actual or 0
        nueva = round(anterior * (1 + pct / 100))
        c.cuota_actual = nueva
        c.cac_pct = pct
        c.ultima_indexacion = ahora
        c.notas = (c.notas or "").strip()
        c.notas += f"\n[ICAC {ahora:%m/%Y}: +{pct}%] cuota ${anterior:,.0f} → ${nueva:,.0f}"
        afectados.append({
            "id": c.id, "apellido_nombre": c.apellido_nombre,
            "cuota_anterior": anterior, "cuota_nueva": nueva,
        })

    db.commit()
    return {"ok": True, "pct": pct, "linea": linea, "cantidad_actualizados": len(afectados), "clientes": afectados}
