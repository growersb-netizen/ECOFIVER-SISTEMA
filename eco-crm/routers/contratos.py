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
from database.models import Contrato, VentaFinanciada, VentaContado, Usuario, ConfiguracionSistema, Pago
from routers.auth import require_auth, require_roles, get_user_roles, require_auth_or_apikey, get_current_user
from routers.configuracion import get_config_value
from routers.aliados import siguiente_numero_solicitud
from utils.documentos import render_html, html_to_pdf, monto_en_letras, split_nombre_apellido

router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR   = Path("data/contratos")  # dentro del volumen persistente (/app/data) — no ephemeral
TEMPLATE_DIR = Path("data/plantillas_contratos")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

UMBRAL_REDONDEO_INSCRIPCION = 5.0  # diferencias de hasta $5 (redondeo de comprobante) cuentan como saldo 0

# Etiqueta del producto para el recibo — antes estaba hardcodeada a "Piscina de
# Fibra de Vidrio" en el template, así que un recibo de MÓDULO salía con el
# nombre de producto equivocado.
_PRODUCTO_LABEL_RECIBO = {
    "PISCINA": "Piscina de Fibra de Vidrio",
    "COMBO": "Combo Piscina + Módulo",
    "MODULO": "Módulo Habitacional Industrializado",
}


def _abs_url(request: Request, path: str) -> str:
    """
    Arma una URL absoluta con el host público real de la request (evita rutas
    relativas que Claude no puede abrir). Uvicorn no confía en X-Forwarded-Proto
    por defecto, así que request.base_url suele devolver "http://" aunque el
    tráfico real llegue por HTTPS detrás del proxy de Railway — se prioriza el
    header por sobre el scheme que infiere Starlette.

    Las llamadas service-to-service dentro de Railway (ej. eco-multiagente →
    eco-crm) no pasan por el proxy público: el Host que llega es el DNS
    interno "*.railway.internal", inalcanzable desde afuera (Claude, un
    navegador). En ese caso se ignora el host de la request y se usa el
    dominio público real de la variable de entorno que Railway inyecta solo.
    """
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    if host and ".railway.internal" in host:
        public_host = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
        if public_host:
            return f"https://{public_host}{path}"
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{host}{path}"


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


# ─── HELPERS — SECCIONES HTML DINÁMICAS DEL CONTRATO ─────────────────────────

def _fmt_money(v) -> str:
    """Alias de _fmt_ar — formato argentino de precio."""
    return _fmt_ar(v)


def _seccion_pago_html(tipo_plan: str, ctx: dict) -> str:
    """Genera el bloque HTML 'Sistema de Pago' según FINANCIADO, CONGELAMIENTO o CONTADO."""

    # Los valores en ctx ya vienen formateados como strings (p.ej. "2.500.000")
    def _sv(key: str) -> str:
        return str(ctx.get(key) or "")

    if tipo_plan == "CONGELAMIENTO":
        return (
            '<div class="section">'
            '<div class="section-header">Sistema de Pago &nbsp;•&nbsp; Congelamiento de Precio — Entrega Programada</div>'
            '<div class="pago-grid">'
            '<div class="pago-cell"><div class="plabel">Valor Total de la Operación</div>'
            '<div class="pvalue">$ ' + _sv("valor_total") + '</div></div>'
            '<div class="pago-cell"><div class="plabel">Flete incluido</div>'
            '<div class="pvalue">$ ' + _sv("flete") + '</div></div>'
            '<div class="pago-cell"><div class="plabel">Cuotas de congelamiento</div>'
            '<div class="pvalue">' + _sv("n_cuotas_congelamiento") + ' cuotas de $ '
            + _sv("valor_cuota_congelamiento") + '.-</div></div>'
            '<div class="pago-cell"><div class="plabel">Saldo contra entrega</div>'
            '<div class="pvalue">$ ' + _sv("saldo_contra_entrega") + '.-</div></div>'
            '</div>'
            '<div class="modalidad-row">'
            '<span style="font-weight:bold;font-size:10px;">Fecha de entrega estimada:&nbsp;&nbsp;'
            '<strong style="color:#1a3a6b;">' + _sv("fecha_entrega_estimada") + '</strong></span>'
            '<span class="financiado-badge">Entrega Programada</span>'
            '</div>'
            '</div>'
        )

    if tipo_plan == "CONTADO":
        señia_raw    = ctx.get("señia", ctx.get("pago_inicial", "0"))
        try:
            señia_num = float(str(señia_raw).replace(".", "").replace(",", ".") or 0)
        except Exception:
            señia_num = 0.0
        tiene_señia  = señia_num > 0
        señia        = str(señia_raw) if tiene_señia else ""
        saldo        = ctx.get("saldo_contra_entrega", "")
        total        = ctx.get("valor_total", ctx.get("precio_total", ""))
        modalidad    = ctx.get("modalidad_pago", "Transferencia")
        fecha_ent    = ctx.get("fecha_entrega_estimada", "")
        condiciones  = ctx.get("condiciones_entrega",
                               "La entrega se realizará una vez abonado el saldo contra entrega. "
                               "La coordinación de fecha y horario se efectuará entre las partes "
                               "con al menos 72 hs de anticipación.")
        items        = ctx.get("incluye_items", [])
        if isinstance(items, str):
            import json as _json
            try:
                items = _json.loads(items)
            except Exception:
                items = [i.strip() for i in items.split(",") if i.strip()]

        items_html = "".join(
            '<div style="display:flex;align-items:baseline;gap:4px;font-size:10px;margin-bottom:2px;">'
            '<span style="color:#1a3a6b;font-weight:bold;">✔</span>'
            '<span>' + str(it) + '</span></div>'
            for it in items
        ) if items else '<span style="font-size:10px;color:#555;">Consultar detalle completo con el asesor</span>'

        # Fila de seña: solo si se abonó una
        if tiene_señia:
            fila_señia = (
                '<div class="pago-cell"><div class="plabel">Seña / Reserva abonada</div>'
                '<div class="pvalue" style="color:#c8902a;">$ ' + señia + '</div></div>'
                '<div class="pago-cell"><div class="plabel">Saldo contra entrega</div>'
                '<div class="pvalue">$ ' + str(saldo) + '.-</div></div>'
                '<div class="pago-cell"><div class="plabel">Modalidad de la seña</div>'
                '<div class="pvalue">' + str(modalidad) + '</div></div>'
            )
        else:
            fila_señia = (
                '<div class="pago-cell" style="grid-column:span 3"><div class="plabel">Forma de pago</div>'
                '<div class="pvalue">Pago total contra entrega &nbsp;•&nbsp; ' + str(modalidad) + '</div></div>'
            )

        return (
            '<div class="section">'
            '<div class="section-header">Condiciones de la Operación &nbsp;•&nbsp; Venta de Contado — Entrega Contra Pago</div>'
            '<div class="pago-grid">'
            '<div class="pago-cell"><div class="plabel">Precio Total de la Operación</div>'
            '<div class="pvalue" style="font-size:14px;">$ ' + str(total) + '</div></div>'
            + fila_señia +
            '</div>'
            '<div style="border:1px solid #ddd;border-top:none;padding:5px 8px;">'
            '<div style="font-size:9px;color:#666;text-transform:uppercase;letter-spacing:.5px;font-weight:bold;margin-bottom:4px;">La operación incluye:</div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 12px;">' + items_html + '</div>'
            '</div>'
            '<div class="modalidad-row" style="flex-direction:column;align-items:flex-start;gap:3px;">'
            '<div style="display:flex;align-items:center;gap:12px;width:100%;">'
            '<span style="font-weight:bold;font-size:10px;">Fecha de entrega estimada:&nbsp;'
            '<strong style="color:#1a3a6b;">' + str(fecha_ent) + '</strong></span>'
            '<span class="financiado-badge" style="margin-left:auto;">Contado</span>'
            '</div>'
            '<div style="font-size:9px;color:#444;line-height:1.4;margin-top:2px;">'
            '<strong>Condiciones de entrega:</strong> ' + str(condiciones) + '</div>'
            '</div>'
            '</div>'
        )

    # FINANCIADO (default)
    check_ef = ctx.get("check_efectivo", "")
    mark_ef  = ctx.get("mark_efectivo", "")
    check_tr = ctx.get("check_transferencia", "")
    mark_tr  = ctx.get("mark_transferencia", "")
    return (
        '<div class="section">'
        '<div class="section-header">Sistema de Pago &nbsp;•&nbsp; 100% Financiado</div>'
        '<div class="pago-grid">'
        '<div class="pago-cell"><div class="plabel">Valor de mercado</div>'
        '<div class="pvalue">$ ' + _sv("valor_mercado") + '</div></div>'
        '<div class="pago-cell"><div class="plabel">Pago inicial</div>'
        '<div class="pvalue">$ ' + _sv("pago_inicial") + '</div></div>'
        '<div class="pago-cell"><div class="plabel">Cantidad de cuotas propuesta</div>'
        '<div class="pvalue">' + _sv("cant_cuotas") + ' cuotas</div></div>'
        '<div class="pago-cell"><div class="plabel">Cuota ofrecida</div>'
        '<div class="pvalue">$ ' + _sv("valor_cuota")
        + '.-&nbsp;<span style="font-size:9px;background:#1a3a6b;color:white;padding:1px 6px;border-radius:3px;">M - Fija</span></div></div>'
        '</div>'
        '<div class="modalidad-row">'
        '<span style="font-weight:bold;font-size:10px;">Modalidad de pago:</span>'
        '<span style="display:inline-flex;align-items:center;gap:5px;">'
        '<span class="box ' + check_ef + '">' + mark_ef + '</span> Efectivo</span>'
        '<span style="display:inline-flex;align-items:center;gap:5px;">'
        '<span class="box ' + check_tr + '">' + mark_tr + '</span> Transferencia</span>'
        '<span class="financiado-badge">100% Financiado</span>'
        '</div>'
        '</div>'
    )


def _recibo_box_html(tipo_plan: str, numero_solicitud: str) -> str:
    """Genera (o suprime) el bloque 'Recibo Autorizado' al pie del contrato."""
    if tipo_plan in ("CONGELAMIENTO", "CONTADO"):
        # Para CONTADO el recibo de seña se genera como documento separado
        return ""
    return (
        '<div class="recibo-box">'
        '<div class="recibo-title">Recibo Autorizado &nbsp;&nbsp; ' + str(numero_solicitud) + '</div>'
        '<div class="recibo-line"><span>Recibimos de</span><span class="recibo-underline"></span></div>'
        '<div class="recibo-line"><span>la suma de</span><span class="recibo-underline"></span></div>'
        '<div class="recibo-line"><span>como pago de <span class="cuota-inicial-bold">Cuota inicial</span>'
        ' en concepto de ingreso de derecho de suscripción y gasto detallado anteriormente.</span></div>'
        '</div>'
    )


def _texto_legal(tipo_plan: str, ctx: dict = None) -> str:
    if ctx is None:
        ctx = {}
    if tipo_plan == "CONGELAMIENTO":
        return (
            "Declaro bajo juramento que los datos procedentemente son verdaderos y en función de ellos, "
            "solicito mi pedido de acuerdo a los términos del contrato que declaro conocer y aceptar. "
            "El precio total queda congelado en la suma pactada, condicionado al cumplimiento del cronograma "
            "de pagos. La entrega se coordinará una vez abonado el saldo contra entrega en la fecha estimada "
            "indicada. Por último, reconozco estar en conocimiento que de solicitar la baja de la presente "
            "solicitud en cualquier momento una vez iniciada la misma la empresa tendrá un plazo no menor a "
            "180 días hábiles para la puesta a disposición de los fondos."
        )
    if tipo_plan == "CONTADO":
        señia_raw_legal = ctx.get("señia", "0")
        try:
            señia_num_legal = float(str(señia_raw_legal).replace(".", "").replace(",", ".") or 0)
        except Exception:
            señia_num_legal = 0.0
        if señia_num_legal > 0:
            clausula_seña = (
                "La seña abonada en este acto confirma la reserva del producto y la fecha de producción. "
                "El saldo restante deberá ser abonado contra entrega del producto en el domicilio indicado, "
                "previo coordinación de fecha y horario con la empresa. "
                "En caso de desistimiento por parte del comprador, la seña abonada no será devuelta. "
            )
        else:
            clausula_seña = (
                "El pago total de la operación se realizará contra entrega del producto en el domicilio "
                "indicado, previo coordinación de fecha y horario con la empresa con al menos 72 hs de anticipación. "
            )
        return (
            "Declaro bajo juramento que los datos proporcionados son verdaderos y en función de ellos formalizo "
            "la presente compra. El precio total de la operación queda fijado en la suma pactada, incluyendo "
            "todos los ítems detallados en la sección 'La operación incluye'. "
            + clausula_seña +
            "La empresa garantiza la entrega en la fecha estimada salvo causas de fuerza mayor debidamente "
            "notificadas al cliente con anticipación razonable."
        )
    return (
        "Declaro bajo juramento que los datos procedentemente son verdaderos y en función de ellos, "
        "solicito mi pedido de acuerdo a los términos del contrato que declaro conocer y aceptar; por "
        "otra parte, reconozco que lo abonado en este caso como suscripción inicial no me será reintegrado "
        "por ningún concepto. En caso de recisión o resolución contractual por parte de la empresa. Por "
        "último, reconozco estar en conocimiento que de solicitar la baja de la presente solicitud en "
        "cualquier momento una vez iniciada la misma la empresa tendrá un plazo no menor a 180 días hábiles "
        "para la puesta a disposición de los fondos. El pago de cada cuota debe realizarse entre los días "
        "1 y 10 de cada mes para mantener vigentes las promociones asignadas."
    )


def _titulo_contrato(tipo_producto: str, tipo_plan: str = "FINANCIADO") -> str:
    if tipo_plan == "CONTADO":
        if tipo_producto == "MODULO":
            return "Contrato de Compraventa de Módulo Habitacional"
        if tipo_producto == "COMBO":
            return "Contrato de Compraventa de Piscina y Módulo"
        return "Contrato de Compraventa de Piscina de Fibra de Vidrio"
    if tipo_producto == "MODULO":
        return "Contrato de Financiación de Módulo"
    if tipo_producto == "COMBO":
        return "Contrato de Financiación de Piscina y Módulo"
    return "Contrato de Financiación de Piscina"


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


@router.post("/api/contratos/manual")
async def create_contrato(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO")),
):
    """Alta manual simple de un registro de Contrato (sin generar PDF ni venta) —
    usada por el formulario de contratos.html. Para generar el documento real y
    la venta, usar POST /api/contratos (endpoint unificado)."""
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


# ─── RUTAS ESPECÍFICAS — deben ir ANTES de {contrato_id} ─────────────────────

@router.get("/api/contratos/catalogo-modelos")
async def get_catalogo_modelos(current_user: Usuario = Depends(require_auth)):
    """Modelos, colores, medidas y sistemas disponibles para el formulario manual."""
    try:
        from routers.catalogo import load_catalogo, _MEDIDAS_PDF as _mpdf
        cat = load_catalogo()
    except Exception:
        cat = {}
        _mpdf = {}

    medidas_cat = cat.get("piscinas", {}).get("medidas", {})
    medidas = {**_mpdf, **medidas_cat}

    return {
        "piscinas": {
            "modelos": cat.get("piscinas", {}).get("modelos", []),
            "colores":  cat.get("piscinas", {}).get("colores", ["Blanco", "Beige", "Verde agua", "Celeste", "Azul"]),
            "medidas":  medidas,
            "sistemas": [
                "Sistema de Filtrado Completo + Iluminación",
                "Sistema de Filtrado Simple",
                "Sistema C-6 básico",
                "Sin sistema (solo estructura)",
            ],
        },
        "modulos": {
            "modelos": list(cat.get("modulos", {}).get("precios", {}).keys()),
            "precios":  cat.get("modulos", {}).get("precios", {}),
        },
    }


@router.get("/api/contratos/buscar")
async def buscar_contratos_manual(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Busca contratos por número de solicitud o nombre de cliente (para emitir recibos)."""
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COBRADOR")):
        raise HTTPException(403, "Sin permisos")

    q = (q or "").strip()
    query = db.query(Contrato).filter(Contrato.tipo_documento == "CONTRATO")
    if q:
        query = query.filter(
            Contrato.numero_solicitud.ilike(f"%{q}%") |
            Contrato.cliente_nombre.ilike(f"%{q}%")
        )
    rows = query.order_by(Contrato.fecha_generacion.desc()).limit(15).all()

    results = []
    for c in rows:
        datos = json.loads(c.datos_json) if c.datos_json else {}
        venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == c.venta_financiada_id).first()
        recibos_n = db.query(Contrato).filter(
            Contrato.venta_financiada_id == c.venta_financiada_id,
            Contrato.tipo_documento == "RECIBO",
        ).count()

        def _safe_num(v):
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).replace(".", "").replace(",", "."))
            except Exception:
                return 0.0

        results.append({
            "numero_solicitud":    c.numero_solicitud or "",
            "cliente_nombre":      c.cliente_nombre or "",
            "tipo_contrato":       c.tipo_contrato or "",
            "tipo_plan":           (venta.forma_pago if venta else "") or "FINANCIADO",
            "modelo":              datos.get("modelo", ""),
            "tipo_producto_label": datos.get("tipo_producto_label", ""),
            "nombre":              datos.get("nombre", ""),
            "apellido":            datos.get("apellido", ""),
            "telefono":            datos.get("telefono", ""),
            "dni":                 datos.get("dni", ""),
            "cuil":                datos.get("cuil", ""),
            "domicilio":           datos.get("domicilio", ""),
            "localidad":           datos.get("localidad", ""),
            "email":               datos.get("email", ""),
            "ocupacion":           datos.get("ocupacion", ""),
            "estado_civil":        datos.get("estado_civil", ""),
            "largo":               datos.get("largo", ""),
            "ancho":               datos.get("ancho", ""),
            "profundidad_min":     datos.get("profundidad_min", ""),
            "profundidad_max":     datos.get("profundidad_max", ""),
            "sistema":             datos.get("sistema", ""),
            "precio_total":        venta.precio_total if venta else 0,
            "cantidad_cuotas":     venta.cantidad_cuotas if venta else 0,
            "valor_cuota":         venta.valor_cuota if venta else 0,
            "n_cuotas_congelamiento":    datos.get("n_cuotas_congelamiento", ""),
            "valor_cuota_congelamiento": datos.get("valor_cuota_congelamiento", ""),
            "saldo_contra_entrega":      _safe_num(datos.get("saldo_contra_entrega", 0)),
            "fecha_entrega_estimada":    datos.get("fecha_entrega_estimada", ""),
            "venta_financiada_id":       c.venta_financiada_id,
            "contrato_id":               c.id,
            "recibos_emitidos":          recibos_n,
        })
    return results


# ─── FIN rutas específicas — ahora sí rutas con {contrato_id} ────────────────

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
        "tipo_producto_label": _PRODUCTO_LABEL_RECIBO.get(venta.producto, "Piscina de Fibra de Vidrio"),
    }
    context.update(_venta_base_dict(venta))
    context.update(overrides)

    modalidad = (overrides.get("modalidad_pago") or "").lower()
    if modalidad == "efectivo":
        context["check_efectivo"], context["mark_efectivo"] = "checked", "✓"
    elif modalidad == "transferencia":
        context["check_transferencia"], context["mark_transferencia"] = "checked", "✓"

    _tplan = (overrides.get("tipo_plan") or "FINANCIADO").upper()
    context.setdefault("valor_total", context.get("valor_mercado", ""))
    context.setdefault("flete", "")
    context.setdefault("n_cuotas_congelamiento", "")
    context.setdefault("valor_cuota_congelamiento", "")
    context.setdefault("saldo_contra_entrega", "")
    context.setdefault("fecha_entrega_estimada", "")
    context["seccion_pago_html"] = _seccion_pago_html(_tplan, context)
    context["recibo_box_html"]   = _recibo_box_html(_tplan, context.get("numero_solicitud", ""))
    context["texto_legal"]       = _texto_legal(_tplan, context)
    context["titulo_contrato"]   = _titulo_contrato(venta.producto or "PISCINA", _tplan)

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


async def generar_recibo_pdf(
    db: Session,
    venta: VentaFinanciada,
    monto_recibido: float,
    concepto: str = "Pago",
    modalidad: str = "",
    overrides: Optional[dict] = None,
) -> Contrato:
    """
    Arma el contexto, renderiza el PDF real del recibo y guarda el registro
    de Contrato (tipo_documento=RECIBO). Reusado por el endpoint de contratos
    y por el registro de pago de cuota (ventas_financiadas.py) para que
    CUALQUIER pago — cuota mensual o entrada/suscripción — emita recibo real.
    """
    overrides = overrides or {}
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
        "tipo_producto_label": _PRODUCTO_LABEL_RECIBO.get(venta.producto, "Piscina de Fibra de Vidrio"),
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
        venta_financiada_id=venta.id,
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

    recibo.saldo_pendiente = saldo_pendiente  # atributo en memoria, no persistido
    recibo.es_cierre = es_cierre
    recibo.nombre_archivo = nombre_archivo
    return recibo


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

    recibo = await generar_recibo_pdf(
        db, venta,
        monto_recibido=float(body.get("monto_recibido") or 0),
        concepto=body.get("concepto") or "Pago",
        modalidad=body.get("modalidad") or "",
        overrides=body.get("datos", {}),
    )
    return {"ok": True, "recibo_id": recibo.id, "archivo": recibo.nombre_archivo,
            "saldo_pendiente": recibo.saldo_pendiente, "es_cierre": recibo.es_cierre,
            "download_url": f"/api/contratos/{recibo.id}/download"}


# ─── ENDPOINT UNIFICADO — fuente única de verdad para crear contratos ────────
# Usado por: Claude.ai (vía MCP), Máximo (WhatsApp/Telegram), futuro frontend.
# Asigna numero_solicitud de forma atómica (mismo mecanismo que aliados.py),
# crea la venta financiada, genera el PDF real y, si viene, registra el pago
# inicial — todo en una sola llamada para que no puedan pisarse dos canales.

_TIPO_PRODUCTO_MAP = {"pileta": "PISCINA", "modulo": "MODULO", "combo": "COMBO", "exterior": "PISCINA"}


def _contrato_a_dict(contrato: Contrato, venta: Optional[VentaFinanciada], request: Optional[Request] = None) -> dict:
    datos = json.loads(contrato.datos_json) if contrato.datos_json else {}
    saldo = 0.0
    estado_inscripcion = datos.get("estado_inscripcion", "")
    if venta:
        objetivo_inscripcion = venta.monto_inscripcion if venta.monto_inscripcion is not None else (venta.precio_total or 0)
        saldo = max(0.0, objetivo_inscripcion - (venta.anticipo or 0))
        if saldo <= UMBRAL_REDONDEO_INSCRIPCION:
            saldo = 0.0
        estado_inscripcion = "completa" if saldo <= 0 else ("parcial" if (venta.anticipo or 0) > 0 else "pendiente")
    pdf_path = f"/api/contratos/{contrato.id}/download"
    return {
        "numero_solicitud": contrato.numero_solicitud or "",
        "contrato_id": contrato.id,
        "cliente_nombre": contrato.cliente_nombre or "",
        "tipo_contrato": contrato.tipo_contrato or "",
        "estado": contrato.estado or "",
        "estado_inscripcion": estado_inscripcion,
        "saldo_inscripcion_pendiente": saldo,
        "pdf_url": _abs_url(request, pdf_path) if request else pdf_path,
        "creado_en": contrato.fecha_generacion.isoformat() if contrato.fecha_generacion else "",
        "venta_financiada_id": contrato.venta_financiada_id,
        "historial_pagos": [
            {"monto": p.monto, "fecha_pago": p.fecha_pago.isoformat() if p.fecha_pago else "", "notas": p.notas or ""}
            for p in (venta.pagos if venta else [])
        ],
    }


@router.post("/api/contratos", status_code=201)
async def crear_contrato_unificado(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Crea la venta financiada, asigna numero_solicitud atómicamente y genera
    el PDF del contrato real. Ver spec completa en spec_endpoint_contratos.md
    (campos: cliente, conyuge, producto, financiacion, entrega, pago_registrado, origen).
    """
    body = await request.json()
    cliente = body.get("cliente") or {}
    conyuge = body.get("conyuge") or {}
    producto = body.get("producto") or {}
    financiacion = body.get("financiacion") or {}
    entrega = body.get("entrega") or {}
    pago_registrado = body.get("pago_registrado") or {}
    origen = body.get("origen") or {}

    # Validación completa: se juntan TODOS los campos faltantes en un solo error
    # (no se corta en el primero) para que quien emite el contrato sepa de una
    # sola vez todo lo que falta pedirle al cliente — un contrato con domicilio
    # o fecha de nacimiento en blanco sale incompleto y no es aceptable.
    faltantes = []
    for campo in ("nombre", "apellido", "dni", "telefono", "domicilio", "localidad",
                  "fecha_nacimiento", "estado_civil", "ocupacion", "email"):
        if not cliente.get(campo):
            faltantes.append(f"cliente.{campo}")
    if not producto.get("tipo"):
        faltantes.append("producto.tipo")
    if not producto.get("modelo"):
        faltantes.append("producto.modelo")
    if producto.get("tipo") == "pileta":
        for campo in ("largo_m", "ancho_m"):
            if producto.get(campo) is None:
                faltantes.append(f"producto.{campo}")
    for campo in ("valor_mercado", "pago_inicial", "cant_cuotas", "valor_cuota"):
        if financiacion.get(campo) is None:
            faltantes.append(f"financiacion.{campo}")
    if faltantes:
        raise HTTPException(400, {
            "mensaje": "Faltan datos obligatorios para emitir el contrato — no se genera incompleto.",
            "campos_faltantes": faltantes,
        })

    monto_pago = float(pago_registrado.get("monto") or 0)
    if monto_pago > float(financiacion["valor_mercado"]):
        raise HTTPException(422, "pago_registrado.monto no puede superar financiacion.valor_mercado")

    # DNI ya tiene una solicitud activa — advertencia, no bloqueo (a menos que se pida forzar)
    dni = str(cliente["dni"]).strip()
    existente = db.query(VentaFinanciada).filter(
        VentaFinanciada.cliente_dni == dni,
        VentaFinanciada.estado_plan.notin_(["CANCELADO", "FINALIZADO"]),
    ).first()
    if existente and not body.get("forzar"):
        raise HTTPException(409, {
            "mensaje": "El DNI ya tiene una solicitud activa sin resolver",
            "numero_solicitud": existente.numero_solicitud,
        })

    numero_solicitud = siguiente_numero_solicitud(db)
    ahora = datetime.now()

    tipo_producto = _TIPO_PRODUCTO_MAP.get((producto.get("tipo") or "").lower(), "PISCINA")
    cliente_nombre = f"{cliente['apellido']}, {cliente['nombre']}"
    pago_inicial = float(financiacion["pago_inicial"])
    saldo_inscripcion = max(0.0, pago_inicial - monto_pago)
    if saldo_inscripcion <= UMBRAL_REDONDEO_INSCRIPCION:
        saldo_inscripcion = 0.0
    estado_inscripcion = "completa" if saldo_inscripcion <= 0 else ("parcial" if monto_pago > 0 else "pendiente")

    venta = VentaFinanciada(
        cliente_nombre=cliente_nombre,
        cliente_telefono=cliente.get("telefono") or "",
        cliente_localidad=cliente.get("localidad") or "",
        producto=tipo_producto,
        modelo_especifico=producto["modelo"],
        color=producto.get("color"),
        superficie_m2=producto.get("superficie_m2"),
        forma_pago="PMI",
        precio_total=float(financiacion["valor_mercado"]),
        anticipo=monto_pago if monto_pago else 0,
        monto_inscripcion=pago_inicial,
        cantidad_cuotas=int(financiacion["cant_cuotas"]),
        valor_cuota=float(financiacion["valor_cuota"]),
        fecha_inicio_plan=ahora,
        estado_plan="ACTIVO",
        estado_admision=estado_inscripcion.upper(),
        numero_solicitud=numero_solicitud,
        cliente_dni=dni,
        cliente_cuil=cliente.get("cuil"),
        cliente_domicilio=cliente.get("domicilio"),
        cliente_estado_civil=cliente.get("estado_civil"),
        cliente_ocupacion=cliente.get("ocupacion"),
        cliente_email=cliente.get("email"),
        notas=f"Origen: {origen.get('canal','')} — operador: {origen.get('operador','')}",
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    if monto_pago > 0:
        db.add(Pago(
            venta_financiada_id=venta.id,
            monto=monto_pago,
            notas=f"{pago_registrado.get('concepto','')} — {pago_registrado.get('modalidad','')} — "
                  f"op {pago_registrado.get('comprobante_numero_operacion','')}",
        ))
        db.commit()

    # ── Render del contrato real ──────────────────────────────────────────
    observaciones = entrega.get("observacion_libre") or (
        f"ASIGNACIÓN DE FECHA PARA INSTALACIÓN EN {entrega['mes'].upper()} {entrega.get('anio','')}"
        if entrega.get("mes") else
        "LA FECHA DE INSTALACIÓN SE ASIGNARÁ CONFORME AL PLAN DE PRODUCCIÓN VIGENTE."
    )
    tipologia = producto["modelo"] + (" (medida especial)" if producto.get("medida_especial") else "")

    context = {
        "fecha_contrato": ahora.strftime("%d de %B de %Y"),
        "fecha_nacimiento": cliente.get("fecha_nacimiento") or "",
        "telefono_alt": cliente.get("telefono_alt") or "",
        "piso": cliente.get("piso") or "", "depto": cliente.get("depto") or "",
        "provincia": cliente.get("provincia") or "",
        "lugar_nacimiento": cliente.get("lugar_nacimiento") or "",
        "conyuge_nombre": conyuge.get("nombre") or "", "conyuge_apellido": conyuge.get("apellido") or "",
        "conyuge_dni": conyuge.get("dni") or "", "conyuge_nacimiento": conyuge.get("fecha_nacimiento") or "",
        "conyuge_telefono": conyuge.get("telefono") or "", "conyuge_email": conyuge.get("email") or "",
        "tipologia": tipologia,
        "largo": producto.get("largo_m") or "", "ancho": producto.get("ancho_m") or "",
        "profundidad_min": producto.get("profundidad_min_m") or "",
        "profundidad_max": producto.get("profundidad_max_m") or "",
        "sistema": producto.get("sistema") or "C-6",
        "observaciones": observaciones,
        "tipo_producto_label": _PRODUCTO_LABEL_RECIBO.get(tipo_producto, "Piscina de Fibra de Vidrio"),
        "check_efectivo": "", "mark_efectivo": "", "check_transferencia": "", "mark_transferencia": "",
        "firma_productor_block": "",
    }
    modalidad = (pago_registrado.get("modalidad") or "").lower()
    if modalidad == "efectivo":
        context["check_efectivo"], context["mark_efectivo"] = "checked", "✓"
    elif modalidad == "transferencia":
        context["check_transferencia"], context["mark_transferencia"] = "checked", "✓"
    context.update(_venta_base_dict(venta))
    context["estado_inscripcion"] = estado_inscripcion
    context.setdefault("valor_total", context.get("valor_mercado", ""))
    context.setdefault("flete", "")
    context.setdefault("n_cuotas_congelamiento", "")
    context.setdefault("valor_cuota_congelamiento", "")
    context.setdefault("saldo_contra_entrega", "")
    context.setdefault("fecha_entrega_estimada", "")
    context["seccion_pago_html"] = _seccion_pago_html("FINANCIADO", context)
    context["recibo_box_html"]   = _recibo_box_html("FINANCIADO", numero_solicitud)
    context["texto_legal"]       = _texto_legal("FINANCIADO", context)
    context["titulo_contrato"]   = _titulo_contrato(tipo_producto)

    pdf_url = None
    try:
        html = render_html("contrato_template.html", context)
        nombre_archivo = f"contrato_{cliente_nombre.replace(' ', '_').replace(',', '')}_{ahora:%Y%m%d%H%M%S}.pdf"
        out_path = UPLOAD_DIR / nombre_archivo
        await html_to_pdf(html, out_path)

        contrato = Contrato(
            venta_financiada_id=venta.id,
            cliente_nombre=cliente_nombre,
            tipo_contrato=f"{tipo_producto} — {venta.forma_pago}",
            tipo_documento="CONTRATO",
            numero_solicitud=numero_solicitud,
            archivo_pdf=str(out_path),
            datos_json=json.dumps(context, ensure_ascii=False),
            estado="BORRADOR",
        )
        db.add(contrato)
        db.commit()
        db.refresh(contrato)
        pdf_url = _abs_url(request, f"/api/contratos/{contrato.id}/download")
    except Exception as e:
        # La venta y el número YA quedaron registrados — el PDF se puede regenerar después.
        return {
            "numero_solicitud": numero_solicitud,
            "venta_financiada_id": venta.id,
            "pdf_url": None,
            "error_pdf": str(e),
            "estado_inscripcion": estado_inscripcion,
            "saldo_inscripcion_pendiente": saldo_inscripcion,
        }

    return {
        "numero_solicitud": numero_solicitud,
        "venta_financiada_id": venta.id,
        "contrato_id": contrato.id,
        "pdf_url": pdf_url,
        "estado_inscripcion": estado_inscripcion,
        "saldo_inscripcion_pendiente": saldo_inscripcion,
        "creado_en": ahora.isoformat(),
    }


@router.get("/api/contratos/solicitud/{numero_solicitud}")
async def consultar_contrato_por_numero(
    numero_solicitud: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """Estado completo de una solicitud (para 'cuánto le falta pagar a X')."""
    contrato = db.query(Contrato).filter(
        Contrato.numero_solicitud == numero_solicitud, Contrato.tipo_documento == "CONTRATO"
    ).order_by(Contrato.fecha_generacion.desc()).first()
    if not contrato:
        raise HTTPException(404, "Solicitud no encontrada")
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == contrato.venta_financiada_id).first()
    return _contrato_a_dict(contrato, venta, request)


@router.post("/api/contratos/{numero_solicitud}/pagos")
async def registrar_pago_por_numero(
    numero_solicitud: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Registra un pago posterior (a cuenta, saldo final) sobre una solicitud
    ya existente. Mismo objeto pago_registrado del endpoint de creación.
    Emite el recibo real y recalcula el estado de inscripción.
    """
    contrato = db.query(Contrato).filter(
        Contrato.numero_solicitud == numero_solicitud, Contrato.tipo_documento == "CONTRATO"
    ).order_by(Contrato.fecha_generacion.desc()).first()
    if not contrato or not contrato.venta_financiada_id:
        raise HTTPException(404, "Solicitud no encontrada")
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == contrato.venta_financiada_id).first()
    if not venta:
        raise HTTPException(404, "Venta financiada no encontrada")

    body = await request.json()
    pago_registrado = body.get("pago_registrado") or body
    monto = float(pago_registrado.get("monto") or 0)
    if monto <= 0:
        raise HTTPException(400, "pago_registrado.monto debe ser mayor a 0")
    concepto = pago_registrado.get("concepto", "pago")
    modalidad = pago_registrado.get("modalidad", "")

    db.add(Pago(
        venta_financiada_id=venta.id,
        monto=monto,
        notas=f"{concepto} — {modalidad} — op {pago_registrado.get('comprobante_numero_operacion','')}",
    ))
    venta.anticipo = (venta.anticipo or 0) + monto
    if venta.anticipo >= (venta.precio_total or 0):
        venta.estado_plan = "FINALIZADO"
    db.commit()

    objetivo_inscripcion = venta.monto_inscripcion if venta.monto_inscripcion is not None else (venta.precio_total or 0)
    saldo = max(0.0, objetivo_inscripcion - (venta.anticipo or 0))
    if saldo <= UMBRAL_REDONDEO_INSCRIPCION:
        saldo = 0.0
    estado_inscripcion = "completa" if saldo <= 0 else "parcial"

    concepto_recibo = {
        "seña": "Cuota inicial", "pago_a_cuenta": "Pago a cuenta", "pago_inicial_completo": "Cuota inicial",
    }.get(concepto, concepto.replace("_", " ").capitalize() or "Pago")

    recibo_pdf_url = None
    try:
        recibo = await generar_recibo_pdf(
            db, venta, monto_recibido=monto, concepto=concepto_recibo, modalidad=modalidad,
            overrides={"op_numero": pago_registrado.get("comprobante_numero_operacion", "")},
        )
        recibo_pdf_url = _abs_url(request, f"/api/contratos/{recibo.id}/download")
    except Exception as e:
        logger_err = str(e)  # el pago ya quedó registrado — el recibo se puede regenerar después
    else:
        logger_err = None

    return {
        "ok": True,
        "numero_solicitud": numero_solicitud,
        "monto_registrado": monto,
        "saldo_inscripcion_pendiente": saldo,
        "estado_inscripcion": estado_inscripcion,
        "recibo_pdf_url": recibo_pdf_url,
        **({"error_recibo": logger_err} if logger_err else {}),
    }


# ─── ENDPOINTS MANUALES — PANEL INTERNO ──────────────────────────────────────

@router.post("/api/contratos/emitir-nuevo", status_code=201)
async def emitir_nuevo_contrato(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Genera un contrato nuevo (PDF) para cualquier tipo de plan: FINANCIADO o CONGELAMIENTO.
    Uso manual desde el panel. Body: ver formulario en contratos.html.
    """
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COBRADOR")):
        raise HTTPException(403, "Sin permisos para emitir contratos")

    body = await request.json()
    tipo_plan    = (body.get("tipo_plan") or "FINANCIADO").upper()
    tipo_raw     = (body.get("tipo_producto") or "PISCINA").upper()
    tipo_producto = _TIPO_PRODUCTO_MAP.get(tipo_raw.lower(), tipo_raw)

    nombre   = (body.get("nombre")   or "").strip()
    apellido = (body.get("apellido") or "").strip()
    dni      = (body.get("dni")      or "").strip()
    if not nombre or not apellido or not dni:
        raise HTTPException(400, "Faltan nombre, apellido o DNI del cliente")

    cliente_nombre = f"{apellido}, {nombre}"
    ahora = datetime.now()
    fecha_str = body.get("fecha_contrato") or ahora.strftime("%d/%m/%Y")

    numero_solicitud = siguiente_numero_solicitud(db)

    if tipo_plan == "CONGELAMIENTO":
        valor_total       = float(body.get("valor_total") or 0)
        flete             = float(body.get("flete") or 0)
        n_cuotas          = int(body.get("n_cuotas_congelamiento") or 0)
        vcong             = float(body.get("valor_cuota_congelamiento") or 0)
        saldo_entrega     = float(body.get("saldo_contra_entrega") or 0)
        precio_total      = valor_total
        pago_ini_contrato = 0.0
        cant_cuotas_v     = n_cuotas
        valor_cuota_v     = vcong
        monto_insc        = n_cuotas * vcong
        señia             = 0.0
        incluye_items     = []
        condiciones_ent   = ""
    elif tipo_plan == "CONTADO":
        valor_total       = float(body.get("valor_total") or 0)
        señia             = float(body.get("señia") or body.get("pago_inicial") or 0)
        saldo_entrega     = float(body.get("saldo_contra_entrega") or (valor_total - señia))
        flete             = 0.0
        n_cuotas          = 1
        vcong             = 0.0
        pago_ini_contrato = señia
        cant_cuotas_v     = 1
        valor_cuota_v     = saldo_entrega
        precio_total      = valor_total
        monto_insc        = señia
        incluye_items     = body.get("incluye_items") or []
        condiciones_ent   = body.get("condiciones_entrega") or (
            "La entrega se realizará contra el pago total del saldo acordado. "
            "La coordinación de fecha y horario se realizará entre las partes "
            "con al menos 72 hs de anticipación."
        )
    else:
        valor_total       = float(body.get("valor_mercado") or 0)
        flete             = 0.0
        n_cuotas          = 0
        vcong             = 0.0
        saldo_entrega     = 0.0
        señia             = 0.0
        pago_ini_contrato = float(body.get("pago_inicial") or 0)
        cant_cuotas_v     = int(body.get("cant_cuotas") or 0)
        valor_cuota_v     = float(body.get("valor_cuota") or 0)
        precio_total      = valor_total
        monto_insc        = pago_ini_contrato
        incluye_items     = []
        condiciones_ent   = ""

    monto_pago = float(body.get("monto_pago_inicial") or 0)

    venta = VentaFinanciada(
        cliente_nombre=cliente_nombre,
        cliente_telefono=body.get("telefono") or "",
        cliente_localidad=body.get("localidad") or "",
        cliente_dni=dni,
        cliente_cuil=body.get("cuil") or "",
        cliente_domicilio=body.get("domicilio") or "",
        cliente_estado_civil=body.get("estado_civil") or "",
        cliente_ocupacion=body.get("ocupacion") or "",
        cliente_email=body.get("email") or "",
        producto=tipo_producto,
        modelo_especifico=body.get("modelo") or "",
        color=body.get("color") or "",
        forma_pago=tipo_plan,
        precio_total=precio_total,
        anticipo=monto_pago,
        monto_inscripcion=monto_insc,
        cantidad_cuotas=cant_cuotas_v,
        valor_cuota=valor_cuota_v,
        fecha_inicio_plan=ahora,
        estado_plan="ACTIVO",
        estado_admision="PENDIENTE" if monto_pago == 0 else "PARCIAL",
        numero_solicitud=numero_solicitud,
        notas=f"Emitido manualmente — {getattr(current_user, 'nombre', '') or current_user.email}",
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    if monto_pago > 0:
        db.add(Pago(
            venta_financiada_id=venta.id,
            monto=monto_pago,
            notas=f"{body.get('concepto_pago_inicial','Pago inicial')} — "
                  f"{body.get('modalidad_pago_inicial','')} — op {body.get('op_numero_pago','')}",
        ))
        db.commit()

    # Modalidad checkboxes (para FINANCIADO)
    modalidad = (body.get("modalidad_pago") or body.get("modalidad_pago_inicial") or "").lower()
    check_ef = "checked" if modalidad == "efectivo" else ""
    mark_ef  = "✓" if modalidad == "efectivo" else ""
    check_tr = "checked" if modalidad == "transferencia" else ""
    mark_tr  = "✓" if modalidad == "transferencia" else ""

    context = {
        "numero_solicitud":  numero_solicitud,
        "fecha_contrato":    fecha_str,
        "nombre":            nombre,
        "apellido":          apellido,
        "dni":               body.get("dni") or "",
        "cuil":              body.get("cuil") or "",
        "fecha_nacimiento":  body.get("fecha_nacimiento") or "",
        "estado_civil":      body.get("estado_civil") or "",
        "email":             body.get("email") or "",
        "telefono":          body.get("telefono") or "",
        "telefono_alt":      body.get("telefono_alt") or "",
        "domicilio":         body.get("domicilio") or "",
        "piso":              body.get("piso") or "",
        "depto":             body.get("depto") or "",
        "localidad":         body.get("localidad") or "",
        "provincia":         body.get("provincia") or "",
        "lugar_nacimiento":  body.get("lugar_nacimiento") or "",
        "ocupacion":         body.get("ocupacion") or "",
        "conyuge_nombre":    body.get("conyuge_nombre") or "",
        "conyuge_apellido":  body.get("conyuge_apellido") or "",
        "conyuge_dni":       body.get("conyuge_dni") or "",
        "conyuge_nacimiento":body.get("conyuge_nacimiento") or "",
        "conyuge_telefono":  body.get("conyuge_telefono") or "",
        "conyuge_email":     body.get("conyuge_email") or "",
        "tipo_producto_label": _PRODUCTO_LABEL_RECIBO.get(tipo_producto, tipo_producto.capitalize()),
        "tipologia":         body.get("modelo") or "",
        "modelo":            body.get("modelo") or "",
        "largo":             str(body.get("largo_m") or ""),
        "ancho":             str(body.get("ancho_m") or ""),
        "profundidad_min":   str(body.get("profundidad_min_m") or ""),
        "profundidad_max":   str(body.get("profundidad_max_m") or ""),
        "sistema":           body.get("sistema") or "",
        "observaciones":     body.get("observaciones") or
                             "LA FECHA DE INSTALACIÓN SE ASIGNARÁ CONFORME AL PLAN DE PRODUCCIÓN VIGENTE.",
        # FINANCIADO
        "valor_mercado":     _fmt_ar(valor_total),
        "pago_inicial":      _fmt_ar(pago_ini_contrato),
        "cant_cuotas":       str(cant_cuotas_v),
        "valor_cuota":       _fmt_ar(valor_cuota_v),
        "check_efectivo":    check_ef, "mark_efectivo": mark_ef,
        "check_transferencia": check_tr, "mark_transferencia": mark_tr,
        # CONGELAMIENTO
        "valor_total":               _fmt_ar(valor_total),
        "flete":                     _fmt_ar(flete),
        "n_cuotas_congelamiento":    str(n_cuotas),
        "valor_cuota_congelamiento": _fmt_ar(vcong),
        "saldo_contra_entrega":      _fmt_ar(saldo_entrega),
        "fecha_entrega_estimada":    body.get("fecha_entrega_estimada") or "",
        # CONTADO
        "señia":                     _fmt_ar(señia),
        "modalidad_pago":            body.get("modalidad_pago") or body.get("modalidad_pago_inicial") or "Transferencia",
        "incluye_items":             json.dumps(incluye_items, ensure_ascii=False),
        "condiciones_entrega":       condiciones_ent,
        "firma_productor_block":     "",
    }
    context["seccion_pago_html"] = _seccion_pago_html(tipo_plan, context)
    context["recibo_box_html"]   = _recibo_box_html(tipo_plan, numero_solicitud)
    context["texto_legal"]       = _texto_legal(tipo_plan, context)
    context["titulo_contrato"]   = _titulo_contrato(tipo_producto, tipo_plan)

    try:
        html = render_html("contrato_template.html", context)
        nombre_arch = f"contrato_{cliente_nombre.replace(' ','_').replace(',','')}_{ahora:%Y%m%d%H%M%S}.pdf"
        out_path = UPLOAD_DIR / nombre_arch
        await html_to_pdf(html, out_path)

        contrato = Contrato(
            venta_financiada_id=venta.id,
            cliente_nombre=cliente_nombre,
            tipo_contrato=f"{tipo_producto} — {tipo_plan}",
            tipo_documento="CONTRATO",
            numero_solicitud=numero_solicitud,
            archivo_pdf=str(out_path),
            datos_json=json.dumps(context, ensure_ascii=False),
            estado="BORRADOR",
            responsable_id=current_user.id,
        )
        db.add(contrato)
        db.commit()
        db.refresh(contrato)
        pdf_url = _abs_url(request, f"/api/contratos/{contrato.id}/download")
        return {
            "ok": True, "numero_solicitud": numero_solicitud,
            "venta_financiada_id": venta.id, "contrato_id": contrato.id,
            "pdf_url": pdf_url,
        }
    except Exception as e:
        return {
            "ok": True, "numero_solicitud": numero_solicitud,
            "venta_financiada_id": venta.id, "pdf_url": None, "error_pdf": str(e),
        }

@router.post("/api/contratos/recibo-por-numero/{numero_solicitud}", status_code=201)
async def emitir_recibo_manual(
    numero_solicitud: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Genera un recibo manual para un contrato ya existente.
    Body: { monto, cuota_actual, total_cuotas, tipo_cuota, concepto_libre,
            modalidad, medio_pago, op_numero, plan_descripcion, nota_final, fecha_pago }
    """
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COBRADOR")):
        raise HTTPException(403, "Sin permisos para emitir recibos")

    contrato = db.query(Contrato).filter(
        Contrato.numero_solicitud == numero_solicitud,
        Contrato.tipo_documento == "CONTRATO",
    ).order_by(Contrato.fecha_generacion.desc()).first()
    if not contrato:
        raise HTTPException(404, f"Contrato {numero_solicitud} no encontrado")

    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == contrato.venta_financiada_id).first()
    if not venta:
        raise HTTPException(404, "Venta financiada no encontrada")

    body = await request.json()
    monto = float(body.get("monto") or 0)
    if monto <= 0:
        raise HTTPException(400, "El monto debe ser > 0")

    cuota_actual   = str(body.get("cuota_actual") or "")
    total_cuotas   = str(body.get("total_cuotas") or "")
    tipo_cuota     = (body.get("tipo_cuota") or "")
    concepto_libre = (body.get("concepto_libre") or "").strip()
    modalidad      = (body.get("modalidad") or "Transferencia")
    medio_pago     = (body.get("medio_pago") or modalidad)
    op_numero      = (body.get("op_numero") or "")
    plan_desc      = (body.get("plan_descripcion") or "")
    nota_final     = (body.get("nota_final") or "")
    fecha_pago_str = (body.get("fecha_pago") or datetime.now().strftime("%d/%m/%Y"))

    if concepto_libre:
        concepto = concepto_libre
        concepto_corto = concepto_libre[:40]
    elif cuota_actual and total_cuotas:
        sufijo = f" — {tipo_cuota}" if tipo_cuota else ""
        concepto = f"Cuota {cuota_actual}/{total_cuotas}{sufijo}"
        concepto_corto = f"Cuota {cuota_actual}/{total_cuotas}"
    else:
        concepto = tipo_cuota or "Pago"
        concepto_corto = concepto[:40]

    op_data_blocks = (
        '<div><div class="op-label">Fecha de pago</div>'
        '<div class="op-value">' + fecha_pago_str + '</div></div>'
        '<div><div class="op-label">Medio de pago</div>'
        '<div class="op-value">' + medio_pago + '</div></div>'
        + (
            '<div><div class="op-label">N° Operación</div>'
            '<div class="op-value">' + op_numero + '</div></div>'
            if op_numero else ''
        )
        + (
            '<div><div class="op-label">Plan</div>'
            '<div class="op-value">' + plan_desc + '</div></div>'
            if plan_desc else ''
        )
    )

    tabla_filas = (
        '<tr class="highlight">'
        '<td><strong>' + concepto + '</strong></td>'
        '<td>' + modalidad + ((' — ' + medio_pago) if medio_pago != modalidad else '') + '</td>'
        '<td style="text-align:right">$ ' + _fmt_ar(monto) + '</td>'
        '<td style="text-align:center"><span class="tag-paid">PAGADO</span></td>'
        '</tr>'
    )

    if nota_final:
        notice_bg = "rgba(200,144,42,0.1)"
        notice_border = "#c8902a"
        notice_color = "#1a1a1a"
        notice_strong = "#c8902a"
    else:
        notice_bg = notice_border = notice_color = notice_strong = "transparent"

    datos = json.loads(contrato.datos_json) if contrato.datos_json else {}
    context = {
        "numero_solicitud":  numero_solicitud,
        "concepto_corto":    concepto_corto,
        "fecha_recibo":      fecha_pago_str,
        "monto_recibido":    _fmt_ar(monto),
        "monto_en_letras":   monto_en_letras(monto),
        "modalidad":         modalidad,
        "concepto":          concepto,
        "op_data_blocks":    op_data_blocks,
        "tabla_filas":       tabla_filas,
        "nota_final":        nota_final,
        "notice_bg":         notice_bg,
        "notice_border":     notice_border,
        "notice_color":      notice_color,
        "notice_strong":     notice_strong,
        "nombre":            datos.get("nombre", ""),
        "apellido":          datos.get("apellido", ""),
        "dni":               datos.get("dni", ""),
        "cuil":              datos.get("cuil", ""),
        "telefono":          datos.get("telefono", ""),
        "email":             datos.get("email", ""),
        "domicilio_completo":datos.get("domicilio", ""),
        "estado_civil":      datos.get("estado_civil", ""),
        "ocupacion":         datos.get("ocupacion", ""),
        "tipo_producto_label": datos.get("tipo_producto_label", ""),
        "modelo":            datos.get("modelo", ""),
        "largo":             datos.get("largo", ""),
        "ancho":             datos.get("ancho", ""),
        "profundidad_min":   datos.get("profundidad_min", ""),
        "profundidad_max":   datos.get("profundidad_max", ""),
        "sistema":           datos.get("sistema", ""),
    }

    db.add(Pago(
        venta_financiada_id=venta.id,
        monto=monto,
        notas=f"{concepto} — {modalidad} — op {op_numero}",
    ))
    venta.anticipo = (venta.anticipo or 0) + monto
    if venta.anticipo >= (venta.precio_total or 0):
        venta.estado_plan = "FINALIZADO"
    db.commit()

    ahora = datetime.now()
    html = render_html("recibo_template.html", context)
    nombre_arch = (
        f"recibo_{(contrato.cliente_nombre or 'cliente').replace(' ', '_').replace(',', '')}_{ahora:%Y%m%d%H%M%S}.pdf"
    )
    out_path = UPLOAD_DIR / nombre_arch
    await html_to_pdf(html, out_path)

    recibo = Contrato(
        venta_financiada_id=venta.id,
        cliente_nombre=contrato.cliente_nombre,
        tipo_contrato=concepto,
        tipo_documento="RECIBO",
        numero_solicitud=numero_solicitud,
        archivo_pdf=str(out_path),
        datos_json=json.dumps(context, ensure_ascii=False),
        estado="EMITIDO",
        responsable_id=current_user.id,
    )
    db.add(recibo)
    db.commit()
    db.refresh(recibo)

    return {
        "ok": True,
        "recibo_id": recibo.id,
        "numero_solicitud": numero_solicitud,
        "concepto": concepto,
        "monto": monto,
        "pdf_url": _abs_url(request, f"/api/contratos/{recibo.id}/download"),
    }
