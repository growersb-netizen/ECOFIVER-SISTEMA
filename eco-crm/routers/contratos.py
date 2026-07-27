"""
Módulo — Contratos
Gestión de contratos: plantillas Word subidas por admin, generación con datos del cliente.
"""
import os
import json
import shutil
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Header
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Contrato, VentaFinanciada, VentaContado, Usuario, ConfiguracionSistema
from routers.auth import require_auth, require_roles, get_user_roles, require_auth_or_apikey, get_current_user
from routers.configuracion import get_config_value
from utils.documentos import render_html, html_to_pdf, monto_en_letras, split_nombre_apellido

router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR   = Path("uploads/contratos")
TEMPLATE_DIR = Path("data/plantillas_contratos")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def _fmt_ar(monto) -> str:
    """Formato argentino: punto de miles, sin decimales. Ej: 2500000 -> '2.500.000'."""
    try:
        return f"{float(monto or 0):,.0f}".replace(",", ".")
    except Exception:
        return "0"

TIPOS_PLANTILLA = {
    "modulo":  "Módulo habitacional",
    "piscina": "Piscina",
}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _plantilla_path(tipo: str) -> Path:
    return TEMPLATE_DIR / f"contrato_{tipo}.docx"


def _plantilla_existe(tipo: str) -> bool:
    return _plantilla_path(tipo).exists()


def _get_empresa(db: Session) -> dict:
    return {
        "nombre":    get_config_value("empresa_nombre",    db) or "EcoFiver",
        "cuit":      get_config_value("empresa_cuit",      db) or "",
        "domicilio": get_config_value("empresa_domicilio", db) or "",
        "telefono":  get_config_value("empresa_telefono",  db) or "",
        "email":     get_config_value("empresa_email",     db) or "",
    }


def _fill_template(template_path: Path, context: dict) -> bytes:
    """
    Llena la plantilla .docx con docxtpl.
    Placeholders en el Word: {{ nombre_cliente }}, {{ modelo }}, etc.
    """
    try:
        from docxtpl import DocxTemplate
        doc = DocxTemplate(str(template_path))
        doc.render(context)
        import io
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    except ImportError:
        raise HTTPException(500, "docxtpl no instalado — redepoyar la app")
    except Exception as e:
        raise HTTPException(500, f"Error procesando plantilla: {e}")


def _build_context(venta: VentaFinanciada, db: Session) -> dict:
    """Construye el contexto completo para llenar la plantilla."""
    empresa = _get_empresa(db)
    hoy = datetime.now()

    # Formato de fechas legible
    def fmt(dt):
        if not dt: return "—"
        return dt.strftime("%d/%m/%Y")

    # Forma de pago legible
    forma_map = {
        "PMI": "Plan de Módulos Individual (PMI)",
        "DIRECTA_50": "Financiación directa 50/50",
        "CONTADO": "Contado",
        "SIN_DEFINIR": "A definir",
    }
    forma = forma_map.get(venta.forma_pago or "", venta.forma_pago or "")

    # Tipo de producto
    tipo_map = {"MODULO": "Módulo habitacional", "PISCINA": "Piscina", "COMBO": "Combo"}
    tipo_prod = tipo_map.get(venta.producto or "", venta.producto or "")

    return {
        # Empresa
        "empresa_nombre":    empresa["nombre"],
        "empresa_cuit":      empresa["cuit"],
        "empresa_domicilio": empresa["domicilio"],
        "empresa_telefono":  empresa["telefono"],
        "empresa_email":     empresa["email"],
        # Fecha
        "fecha_contrato":    hoy.strftime("%d de %B de %Y"),
        "fecha_contrato_corta": hoy.strftime("%d/%m/%Y"),
        # Cliente
        "nombre_cliente":    venta.cliente_nombre or "",
        "telefono_cliente":  venta.cliente_telefono or "",
        "localidad_cliente": venta.cliente_localidad or "",
        # Producto
        "tipo_producto":     tipo_prod,
        "modelo":            venta.modelo_especifico or "",
        "color":             venta.color or "",
        "superficie_m2":     str(venta.superficie_m2 or ""),
        # Financiación
        "forma_pago":        forma,
        "precio_total":      f"${venta.precio_total:,.0f}" if venta.precio_total else "—",
        "anticipo":          f"${venta.anticipo:,.0f}" if venta.anticipo else "—",
        "cantidad_cuotas":   str(venta.cantidad_cuotas or ""),
        "valor_cuota":       f"${venta.valor_cuota:,.0f}" if venta.valor_cuota else "—",
        "fecha_inicio_plan": fmt(venta.fecha_inicio_plan),
        "fecha_primer_vencimiento": fmt(venta.fecha_primer_vencimiento),
        # Extras en blanco para que el usuario los complete si quiere
        "dni_cliente":       "______________________",
        "domicilio_cliente": "______________________",
    }


# ─── HTML PAGE ────────────────────────────────────────────────────────────────

@router.get("/contratos", response_class=HTMLResponse)
async def contratos_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    plantillas = {t: _plantilla_existe(t) for t in TIPOS_PLANTILLA}
    return templates.TemplateResponse("contratos.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "plantillas": plantillas,
        "tipos_plantilla": TIPOS_PLANTILLA,
    })


# ─── API — PLANTILLAS ─────────────────────────────────────────────────────────

@router.get("/api/contratos/plantillas")
async def get_plantillas(current_user: Usuario = Depends(require_auth)):
    return {
        tipo: {
            "nombre": nombre,
            "existe": _plantilla_existe(tipo),
            "size_kb": round(_plantilla_path(tipo).stat().st_size / 1024, 1)
                       if _plantilla_existe(tipo) else None,
        }
        for tipo, nombre in TIPOS_PLANTILLA.items()
    }


@router.post("/api/contratos/plantillas/{tipo}")
async def upload_plantilla(
    tipo: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO")),
):
    if tipo not in TIPOS_PLANTILLA:
        raise HTTPException(400, f"Tipo inválido. Válidos: {list(TIPOS_PLANTILLA)}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Solo se aceptan archivos .docx (Word)")

    dest = _plantilla_path(tipo)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"ok": True, "tipo": tipo, "nombre": file.filename}


@router.get("/api/contratos/plantillas/{tipo}/download")
async def download_plantilla(
    tipo: str,
    current_user: Usuario = Depends(require_auth),
):
    if tipo not in TIPOS_PLANTILLA:
        raise HTTPException(400, "Tipo inválido")
    path = _plantilla_path(tipo)
    if not path.exists():
        raise HTTPException(404, "Plantilla no encontrada")
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"plantilla_contrato_{tipo}.docx",
    )


@router.delete("/api/contratos/plantillas/{tipo}")
async def delete_plantilla(
    tipo: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO")),
):
    if tipo not in TIPOS_PLANTILLA:
        raise HTTPException(400, "Tipo inválido")
    path = _plantilla_path(tipo)
    if path.exists():
        path.unlink()
    return {"ok": True}


# ─── API — GENERAR CONTRATO ───────────────────────────────────────────────────

@router.get("/api/contratos/generar/{venta_financiada_id}")
async def generar_contrato(
    venta_financiada_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Genera el .docx del contrato para una venta financiada.
    Devuelve el archivo para descarga directa.
    """
    venta = db.query(VentaFinanciada).filter(
        VentaFinanciada.id == venta_financiada_id
    ).first()
    if not venta:
        raise HTTPException(404, "Venta financiada no encontrada")

    # Determinar tipo de plantilla
    tipo = "piscina" if venta.producto == "PISCINA" else "modulo"
    if not _plantilla_existe(tipo):
        raise HTTPException(
            400,
            f"No hay plantilla para {TIPOS_PLANTILLA[tipo]}. "
            f"Ir a Contratos → Plantillas y subir el archivo .docx."
        )

    context = _build_context(venta, db)
    docx_bytes = _fill_template(_plantilla_path(tipo), context)

    # Guardar registro en DB si no existe
    contrato = db.query(Contrato).filter(
        Contrato.venta_financiada_id == venta_financiada_id
    ).first()
    if not contrato:
        contrato = Contrato(
            venta_financiada_id=venta_financiada_id,
            cliente_nombre=venta.cliente_nombre,
            tipo_contrato=f"{TIPOS_PLANTILLA[tipo]} — {venta.forma_pago}",
            estado="BORRADOR",
            responsable_id=current_user.id,
        )
        db.add(contrato)
        db.commit()

    nombre_archivo = f"contrato_{venta.cliente_nombre.replace(' ','_')}_{datetime.now():%Y%m%d}.docx"

    import io
    from fastapi.responses import Response
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/api/contratos/preview-variables")
async def preview_variables(current_user: Usuario = Depends(require_auth)):
    """Lista todas las variables disponibles para usar en las plantillas."""
    return {
        "empresa": ["empresa_nombre", "empresa_cuit", "empresa_domicilio", "empresa_telefono", "empresa_email"],
        "fecha":   ["fecha_contrato", "fecha_contrato_corta"],
        "cliente": ["nombre_cliente", "telefono_cliente", "localidad_cliente", "dni_cliente", "domicilio_cliente"],
        "producto":["tipo_producto", "modelo", "color", "superficie_m2"],
        "pago":    ["forma_pago", "precio_total", "anticipo", "cantidad_cuotas", "valor_cuota",
                    "fecha_inicio_plan", "fecha_primer_vencimiento"],
        "uso":     "En tu Word usá: {{ nombre_variable }}  (doble llave con espacios)",
    }


# ─── API — CONTRATOS (CRUD existente) ────────────────────────────────────────

@router.get("/api/contratos")
async def list_contratos(
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    q = db.query(Contrato)
    if estado:
        q = q.filter(Contrato.estado == estado)
    if tipo:
        q = q.filter(Contrato.tipo_contrato == tipo)
    contratos = q.order_by(Contrato.fecha_generacion.desc()).all()
    return [{
        "id": c.id,
        "cliente_nombre": c.cliente_nombre,
        "tipo_contrato": c.tipo_contrato or "",
        "fecha_generacion": c.fecha_generacion.isoformat() if c.fecha_generacion else "",
        "archivo_pdf": c.archivo_pdf,
        "estado": c.estado,
        "notas": c.notas or "",
        "venta_contado_id": c.venta_contado_id,
        "venta_financiada_id": c.venta_financiada_id,
    } for c in contratos]


@router.get("/api/contratos/ventas-pendientes")
async def ventas_sin_contrato(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Lista ventas financiadas que aún no tienen contrato generado."""
    ids_con_contrato = {
        c.venta_financiada_id
        for c in db.query(Contrato.venta_financiada_id)
        .filter(Contrato.venta_financiada_id.isnot(None)).all()
    }
    ventas = db.query(VentaFinanciada).filter(
        VentaFinanciada.id.notin_(ids_con_contrato)
    ).order_by(VentaFinanciada.created_at.desc()).limit(50).all()

    return [{
        "id": v.id,
        "cliente_nombre": v.cliente_nombre,
        "producto": v.producto,
        "modelo_especifico": v.modelo_especifico or "",
        "forma_pago": v.forma_pago,
        "precio_total": v.precio_total,
        "created_at": v.created_at.isoformat() if v.created_at else "",
    } for v in ventas]


@router.post("/api/contratos")
async def create_contrato(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO")),
):
    data = await request.json()
    contrato = Contrato(
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        cliente_nombre=data.get("cliente_nombre", ""),
        tipo_contrato=data.get("tipo_contrato", ""),
        estado=data.get("estado", "BORRADOR"),
        notas=data.get("notas", ""),
        responsable_id=current_user.id,
    )
    db.add(contrato)
    db.commit()
    db.refresh(contrato)
    return {"id": contrato.id, "ok": True}


@router.get("/api/contratos/{contrato_id}")
async def get_contrato(
    contrato_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    return {
        "id": c.id,
        "cliente_nombre": c.cliente_nombre,
        "tipo_contrato": c.tipo_contrato or "",
        "fecha_generacion": c.fecha_generacion.isoformat() if c.fecha_generacion else "",
        "archivo_pdf": c.archivo_pdf,
        "estado": c.estado,
        "notas": c.notas or "",
        "venta_contado_id": c.venta_contado_id,
        "venta_financiada_id": c.venta_financiada_id,
    }


@router.delete("/api/contratos/{contrato_id}")
async def delete_contrato(
    contrato_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN")),
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.put("/api/contratos/{contrato_id}")
async def update_contrato(
    contrato_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO")),
):
    contrato = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not contrato:
        raise HTTPException(404, "Contrato no encontrado")

    data = await request.json()
    old_estado = contrato.estado

    for field in ["cliente_nombre", "tipo_contrato", "estado", "notas"]:
        if field in data:
            setattr(contrato, field, data[field])

    if data.get("estado") == "FIRMADO" and old_estado != "FIRMADO":
        if contrato.venta_financiada_id:
            vf = db.query(VentaFinanciada).filter(
                VentaFinanciada.id == contrato.venta_financiada_id
            ).first()
            if vf:
                vf.estado_admision = "APROBADO"

    db.commit()
    return {"ok": True}


@router.post("/api/contratos/{contrato_id}/upload")
async def upload_contrato_pdf(
    contrato_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO")),
):
    contrato = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not contrato:
        raise HTTPException(404, "Contrato no encontrado")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".docx"]:
        raise HTTPException(400, "Solo se aceptan PDF o DOCX")

    filename = f"contrato_{contrato_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
    filepath = UPLOAD_DIR / filename

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    contrato.archivo_pdf = str(filepath)
    db.commit()
    return {"ok": True, "archivo": filename}


@router.get("/api/contratos/{contrato_id}/download")
async def download_contrato(
    contrato_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    contrato = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not contrato or not contrato.archivo_pdf:
        raise HTTPException(404, "Archivo no encontrado")
    path = Path(contrato.archivo_pdf)
    mt = "application/pdf" if str(path).endswith(".pdf") else \
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(str(path), media_type=mt)


# ─── MOTOR REAL — CONTRATO Y RECIBO (templates HTML + Playwright) ─────────────
# Genera documentos idénticos a los que ya se venían emitiendo manualmente.

def _venta_base_dict(venta: VentaFinanciada) -> dict:
    """Campos que ya existen en VentaFinanciada, listos para el template."""
    nombre, apellido = split_nombre_apellido(venta.cliente_nombre)
    return {
        "numero_solicitud": venta.numero_solicitud or "",
        "nombre": nombre,
        "apellido": apellido,
        "dni": venta.cliente_dni or "",
        "cuil": venta.cliente_cuil or "",
        "estado_civil": venta.cliente_estado_civil or "",
        "ocupacion": venta.cliente_ocupacion or "",
        "email": venta.cliente_email or "",
        "telefono": venta.cliente_telefono or "",
        "domicilio": venta.cliente_domicilio or "",
        "localidad": venta.cliente_localidad or "",
        "modelo": venta.modelo_especifico or venta.producto or "",
        "valor_mercado": _fmt_ar(venta.precio_total),
        "pago_inicial": _fmt_ar(venta.anticipo),
        "cant_cuotas": str(venta.cantidad_cuotas or ""),
        "valor_cuota": _fmt_ar(venta.valor_cuota),
    }


@router.post("/api/contratos/emitir/{venta_financiada_id}")
async def emitir_contrato(
    venta_financiada_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Genera el Contrato de Financiación real (HTML → PDF con Playwright),
    idéntico al que se venía emitiendo manualmente. Los datos que no están
    en VentaFinanciada (cónyuge, medidas, fecha nacimiento, etc.) se pasan
    en el body como "datos": {...} — ver templates/documentos/contrato_template.html
    para la lista completa de placeholders.
    """
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_financiada_id).first()
    if not venta:
        raise HTTPException(404, "Venta financiada no encontrada")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    overrides = body.get("datos", {}) if isinstance(body, dict) else {}

    hoy = datetime.now()
    context = {
        # Defaults
        "fecha_contrato": hoy.strftime("%d de %B de %Y"),
        "fecha_nacimiento": "", "telefono_alt": "", "piso": "", "depto": "",
        "provincia": "", "lugar_nacimiento": "",
        "conyuge_nombre": "", "conyuge_apellido": "", "conyuge_dni": "",
        "conyuge_nacimiento": "", "conyuge_telefono": "", "conyuge_email": "",
        "tipologia": "", "largo": "", "ancho": "", "profundidad_min": "",
        "profundidad_max": "", "sistema": "", "observaciones":
            "LA FECHA DE INSTALACIÓN SE ASIGNARÁ CONFORME AL PLAN DE PRODUCCIÓN VIGENTE.",
        "check_efectivo": "", "mark_efectivo": "",
        "check_transferencia": "", "mark_transferencia": "",
        "firma_productor_block": "",
    }
    context.update(_venta_base_dict(venta))
    context.update(overrides)

    modalidad = (overrides.get("modalidad_pago") or "").lower()
    if modalidad == "efectivo":
        context["check_efectivo"], context["mark_efectivo"] = "checked", "✓"
    elif modalidad == "transferencia":
        context["check_transferencia"], context["mark_transferencia"] = "checked", "✓"

    html = render_html("contrato_template.html", context)

    nombre_archivo = f"contrato_{(venta.cliente_nombre or 'cliente').replace(' ', '_').replace(',', '')}_{hoy:%Y%m%d%H%M%S}.pdf"
    out_path = UPLOAD_DIR / nombre_archivo
    await html_to_pdf(html, out_path)

    contrato = db.query(Contrato).filter(Contrato.venta_financiada_id == venta_financiada_id).first()
    if not contrato:
        contrato = Contrato(venta_financiada_id=venta_financiada_id)
        db.add(contrato)
    contrato.cliente_nombre = venta.cliente_nombre
    contrato.tipo_contrato = f"{venta.producto or ''} — {venta.forma_pago or ''}"
    contrato.tipo_documento = "CONTRATO"
    contrato.numero_solicitud = context.get("numero_solicitud") or ""
    contrato.archivo_pdf = str(out_path)
    contrato.datos_json = json.dumps(context, ensure_ascii=False)
    if contrato.estado is None:
        contrato.estado = "BORRADOR"
    db.commit()
    db.refresh(contrato)

    return {"ok": True, "contrato_id": contrato.id, "archivo": nombre_archivo,
            "download_url": f"/api/contratos/{contrato.id}/download"}


@router.post("/api/contratos/emitir-recibo/{venta_financiada_id}")
async def emitir_recibo(
    venta_financiada_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Genera un Recibo de Pago real (seña, pago a cuenta, saldo final o pago
    inicial completo). Body esperado:
    {
      "monto_recibido": 150000,
      "concepto": "Cuota inicial" | "Pago de cuota" | "Saldo final" | ...,
      "modalidad": "Transferencia" | "Efectivo",
      "datos": { ...overrides opcionales de cualquier placeholder... }
    }
    """
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_financiada_id).first()
    if not venta:
        raise HTTPException(404, "Venta financiada no encontrada")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    if not isinstance(body, dict):
        body = {}
    overrides = body.get("datos", {})

    monto_recibido = float(body.get("monto_recibido") or 0)
    concepto = body.get("concepto") or "Pago"
    modalidad = body.get("modalidad") or ""

    precio_total = venta.precio_total or 0
    anticipo_pagado = venta.anticipo or 0
    valor_cuota = venta.valor_cuota or 0
    cuotas_pagas = venta.cuotas_pagas or 0
    cant_cuotas = venta.cantidad_cuotas or 0
    ya_pagado_total = anticipo_pagado + (cuotas_pagas * valor_cuota)
    saldo_pendiente = max(0, precio_total - ya_pagado_total)
    es_cierre = saldo_pendiente <= 0

    tabla_filas = (
        f"<tr><td>Precio total</td><td>Piscina/módulo</td><td style='text-align:right'>$ {_fmt_ar(precio_total)}</td><td style='text-align:center'></td></tr>"
        f"<tr class='highlight'><td>Este recibo</td><td>{concepto}</td><td style='text-align:right'>$ {_fmt_ar(monto_recibido)}</td>"
        f"<td style='text-align:center'><span class='tag-paid'>Pagado</span></td></tr>"
        f"<tr class='{'cancelada-row' if es_cierre else 'saldo-row'}'><td>Saldo pendiente</td><td>Luego de este pago</td>"
        f"<td style='text-align:right'>$ {_fmt_ar(saldo_pendiente)}</td>"
        f"<td style='text-align:center'><span class='{'tag-cancelada' if es_cierre else 'tag-pending'}'>{'Cancelado' if es_cierre else 'Pendiente'}</span></td></tr>"
    )
    if cant_cuotas:
        tabla_filas += (
            f"<tr><td>Plan de cuotas</td><td>{cant_cuotas} cuotas de $ {_fmt_ar(valor_cuota)}</td>"
            f"<td style='text-align:right'>{cuotas_pagas}/{cant_cuotas} pagas</td><td style='text-align:center'></td></tr>"
        )

    if es_cierre:
        notice_bg, notice_border, notice_color, notice_strong = "#f0fff5", "#1a6b3a", "#1a1a1a", "#1a6b3a"
        nota_final = "<strong>Pago completo.</strong> No queda saldo pendiente sobre esta solicitud."
    else:
        notice_bg, notice_border, notice_color, notice_strong = "rgba(200,144,42,0.1)", "#c8902a", "#1a1a1a", "#c8902a"
        nota_final = (
            f"<strong>Saldo pendiente: $ {_fmt_ar(saldo_pendiente)}.</strong> "
            "El pago de cada cuota debe realizarse entre los días 1 y 10 de cada mes para mantener vigentes las promociones asignadas."
        )

    hoy = datetime.now()
    op_data_blocks = (
        f"<div><div class='op-label'>N° operación</div><div class='op-value'>{overrides.get('op_numero','—')}</div></div>"
        f"<div><div class='op-label'>Hora</div><div class='op-value'>{hoy.strftime('%H:%M')}</div></div>"
    )

    context = {
        "numero_solicitud": venta.numero_solicitud or "",
        "concepto_corto": concepto,
        "fecha_recibo": hoy.strftime("%d/%m/%Y"),
        "monto_recibido": _fmt_ar(monto_recibido),
        "monto_en_letras": monto_en_letras(monto_recibido),
        "modalidad": modalidad,
        "concepto": concepto,
        "domicilio_completo": venta.cliente_domicilio or "",
        "largo": "", "ancho": "", "profundidad_min": "", "profundidad_max": "", "sistema": "",
        "op_data_blocks": op_data_blocks,
        "tabla_filas": tabla_filas,
        "nota_final": nota_final,
        "notice_bg": notice_bg, "notice_border": notice_border,
        "notice_color": notice_color, "notice_strong": notice_strong,
    }
    context.update(_venta_base_dict(venta))
    context.update(overrides)

    html = render_html("recibo_template.html", context)

    nombre_archivo = f"recibo_{(venta.cliente_nombre or 'cliente').replace(' ', '_').replace(',', '')}_{hoy:%Y%m%d%H%M%S}.pdf"
    out_path = UPLOAD_DIR / nombre_archivo
    await html_to_pdf(html, out_path)

    recibo = Contrato(
        venta_financiada_id=venta_financiada_id,
        cliente_nombre=venta.cliente_nombre,
        tipo_contrato=concepto,
        tipo_documento="RECIBO",
        numero_solicitud=context.get("numero_solicitud") or "",
        archivo_pdf=str(out_path),
        datos_json=json.dumps(context, ensure_ascii=False),
        estado="EMITIDO",
    )
    db.add(recibo)
    db.commit()
    db.refresh(recibo)

    return {"ok": True, "recibo_id": recibo.id, "archivo": nombre_archivo,
            "saldo_pendiente": saldo_pendiente, "es_cierre": es_cierre,
            "download_url": f"/api/contratos/{recibo.id}/download"}
