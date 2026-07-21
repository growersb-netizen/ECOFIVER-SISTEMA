"""
Importación masiva de clientes existentes:
- Ventas financiadas en curso
- Ventas contado con entregas pactadas
"""
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import VentaFinanciada, VentaContado, Entrega, Usuario, Lead
from routers.auth import require_auth, require_roles, get_user_roles
from routers.leads import asignar_asesor_round_robin

router = APIRouter()
templates = Jinja2Templates(directory="templates")

COLUMNAS_FINANCIADAS = {
    "cliente_nombre": ["nombre", "cliente", "name"],
    "cliente_telefono": ["telefono", "tel", "phone", "celular"],
    "cliente_localidad": ["localidad", "ciudad", "city", "ubicacion"],
    "producto": ["producto", "product", "tipo"],
    "modelo_especifico": ["modelo", "model", "modelo_especifico"],
    "color": ["color"],
    "superficie_m2": ["superficie", "m2", "metros", "superficie_m2"],
    "forma_pago": ["forma_pago", "pago", "plan"],
    "precio_total": ["precio_total", "precio", "price", "valor"],
    "anticipo": ["anticipo", "enganche", "inicial", "ingreso"],
    "cantidad_cuotas": ["cuotas", "cantidad_cuotas", "meses"],
    "valor_cuota": ["valor_cuota", "monto_cuota", "cuota"],
    "fecha_inicio_plan": ["fecha_inicio", "inicio_plan", "fecha_inicio_plan"],
    "fecha_primer_vencimiento": ["primer_vencimiento", "fecha_primer_vencimiento", "vencimiento"],
    "cuotas_pagas": ["cuotas_pagas", "pagadas", "abonadas"],
    "estado_plan": ["estado_plan", "estado", "estado_financiacion"],
    "notas": ["notas", "observaciones", "notes"],
}

COLUMNAS_CONTADO = {
    "cliente_nombre": ["nombre", "cliente", "name"],
    "cliente_telefono": ["telefono", "tel", "phone", "celular"],
    "cliente_localidad": ["localidad", "ciudad", "city", "ubicacion"],
    "producto": ["producto", "product", "tipo"],
    "modelo_especifico": ["modelo", "model"],
    "color": ["color"],
    "superficie_m2": ["superficie", "m2", "metros"],
    "precio_final": ["precio_final", "precio", "price", "valor"],
    "forma_pago": ["forma_pago", "pago"],
    "fecha_instalacion": ["fecha_instalacion", "fecha_entrega", "instalacion"],
    "rango_horario": ["horario", "rango_horario", "hora"],
    "distancia_km": ["distancia_km", "distancia", "km"],
    "estado": ["estado", "status"],
    "notas": ["notas", "observaciones"],
}


def find_col(df, keys):
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for k in keys:
        if k.lower() in cols_lower:
            return cols_lower[k.lower()]
    return None


def safe_str(val) -> str:
    if val is None or str(val).lower() in ("nan", "none", ""):
        return ""
    return str(val).strip()


def safe_float(val) -> Optional[float]:
    try:
        s = safe_str(val)
        if not s:
            return None
        # Remove currency symbols and commas
        s = s.replace("$", "").replace(",", "").replace(".", "", s.count(".") - 1).strip()
        return float(s)
    except Exception:
        return None


def safe_int(val) -> Optional[int]:
    f = safe_float(val)
    return int(f) if f is not None else None


def safe_date(val) -> Optional[datetime]:
    if val is None or str(val).lower() in ("nan", "none", ""):
        return None
    try:
        if hasattr(val, "to_pydatetime"):
            return val.to_pydatetime()
        return datetime.fromisoformat(str(val).strip())
    except Exception:
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"]:
            try:
                return datetime.strptime(str(val).strip(), fmt)
            except Exception:
                pass
    return None


@router.get("/importar", response_class=HTMLResponse)
async def importar_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("importar.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


@router.post("/api/importar/preview")
async def preview_importacion(
    file: UploadFile = File(...),
    tipo: str = "financiadas",
    current_user: Usuario = Depends(require_auth)
):
    """Devuelve las primeras 5 filas y las columnas detectadas para previsualizar."""
    import pandas as pd

    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Error leyendo archivo: {e}")

    columnas_objetivo = COLUMNAS_FINANCIADAS if tipo == "financiadas" else COLUMNAS_CONTADO
    mapeo_detectado = {}
    for campo, keys in columnas_objetivo.items():
        col = find_col(df, keys)
        if col:
            mapeo_detectado[campo] = col

    preview_rows = df.head(5).fillna("").to_dict(orient="records")

    return {
        "columnas_archivo": list(df.columns),
        "columnas_detectadas": mapeo_detectado,
        "total_filas": len(df),
        "preview": preview_rows,
    }


@router.post("/api/importar/financiadas")
async def importar_financiadas(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """
    Importa clientes con financiaciones en curso desde Excel/CSV.
    Columnas esperadas: nombre, telefono, localidad, producto, modelo,
    forma_pago, precio_total, anticipo, cuotas, valor_cuota,
    fecha_inicio_plan, primer_vencimiento, cuotas_pagas, estado, notas.
    """
    import pandas as pd

    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Error leyendo archivo: {e}")

    creados = 0
    errores = []

    for idx, row in df.iterrows():
        try:
            nombre_col = find_col(df, COLUMNAS_FINANCIADAS["cliente_nombre"])
            if not nombre_col:
                raise ValueError("Columna 'nombre' no encontrada")

            nombre = safe_str(row.get(nombre_col))
            if not nombre:
                continue

            def get_val(campo):
                col = find_col(df, COLUMNAS_FINANCIADAS[campo])
                return row.get(col) if col else None

            forma_pago_raw = safe_str(get_val("forma_pago")).upper()
            if "PMI" in forma_pago_raw:
                forma_pago = "PMI"
            elif "50" in forma_pago_raw or "DIRECTA" in forma_pago_raw:
                forma_pago = "DIRECTA_50"
            else:
                forma_pago = "PMI"

            estado_raw = safe_str(get_val("estado_plan")).upper()
            estado_map = {
                "ACTIVO": "ACTIVO", "ATRASADO": "ATRASADO",
                "CANCELADO": "CANCELADO", "FINALIZADO": "FINALIZADO",
            }
            estado_plan = estado_map.get(estado_raw, "ACTIVO")

            producto_raw = safe_str(get_val("producto")).upper()
            if "PISCINA" in producto_raw:
                producto = "PISCINA"
            elif "COMBO" in producto_raw:
                producto = "COMBO"
            else:
                producto = "MODULO"

            venta = VentaFinanciada(
                cliente_nombre=nombre,
                cliente_telefono=safe_str(get_val("cliente_telefono")),
                cliente_localidad=safe_str(get_val("cliente_localidad")),
                producto=producto,
                modelo_especifico=safe_str(get_val("modelo_especifico")),
                color=safe_str(get_val("color")) or None,
                superficie_m2=safe_float(get_val("superficie_m2")),
                forma_pago=forma_pago,
                precio_total=safe_float(get_val("precio_total")) or 0,
                anticipo=safe_float(get_val("anticipo")) or 0,
                cantidad_cuotas=safe_int(get_val("cantidad_cuotas")) or 1,
                valor_cuota=safe_float(get_val("valor_cuota")) or 0,
                fecha_inicio_plan=safe_date(get_val("fecha_inicio_plan")),
                fecha_primer_vencimiento=safe_date(get_val("fecha_primer_vencimiento")),
                cuotas_pagas=safe_int(get_val("cuotas_pagas")) or 0,
                asesor_apertura_id=current_user.id,
                estado_plan=estado_plan,
                notas=safe_str(get_val("notas")),
            )
            db.add(venta)
            creados += 1
        except Exception as e:
            errores.append(f"Fila {idx + 2}: {str(e)}")

    db.commit()
    return {
        "importados": creados,
        "errores": errores[:20],
        "mensaje": f"Se importaron {creados} ventas financiadas correctamente."
    }


@router.post("/api/importar/contado")
async def importar_contado(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """
    Importa clientes con ventas contado y entregas pactadas desde Excel/CSV.
    Columnas esperadas: nombre, telefono, localidad, producto, modelo,
    precio_final, fecha_instalacion, horario, estado, notas.
    """
    import pandas as pd

    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Error leyendo archivo: {e}")

    creados = 0
    errores = []

    for idx, row in df.iterrows():
        try:
            nombre_col = find_col(df, COLUMNAS_CONTADO["cliente_nombre"])
            if not nombre_col:
                raise ValueError("Columna 'nombre' no encontrada")

            nombre = safe_str(row.get(nombre_col))
            if not nombre:
                continue

            def get_val(campo):
                col = find_col(df, COLUMNAS_CONTADO[campo])
                return row.get(col) if col else None

            producto_raw = safe_str(get_val("producto")).upper()
            if "PISCINA" in producto_raw:
                producto = "PISCINA"
            elif "COMBO" in producto_raw:
                producto = "COMBO"
            else:
                producto = "MODULO"

            estado_raw = safe_str(get_val("estado")).upper()
            estado_map = {
                "COORDINADO": "COORDINADO", "INSTALADO": "INSTALADO", "COBRADO": "COBRADO"
            }
            estado = estado_map.get(estado_raw, "COORDINADO")

            fecha_instalacion = safe_date(get_val("fecha_instalacion"))

            distancia_km = safe_float(get_val("distancia_km"))
            flete_calculado = None
            if distancia_km:
                precio_km = 3000  # flete unificado para todos los productos
                flete_calculado = distancia_km * precio_km

            venta = VentaContado(
                cliente_nombre=nombre,
                cliente_telefono=safe_str(get_val("cliente_telefono")),
                cliente_localidad=safe_str(get_val("cliente_localidad")),
                producto=producto,
                modelo_especifico=safe_str(get_val("modelo_especifico")),
                color=safe_str(get_val("color")) or None,
                superficie_m2=safe_float(get_val("superficie_m2")),
                precio_final=safe_float(get_val("precio_final")) or 0,
                forma_pago=safe_str(get_val("forma_pago")) or "CONTADO",
                vendedor_id=current_user.id,
                fecha_instalacion=fecha_instalacion,
                rango_horario=safe_str(get_val("rango_horario")),
                distancia_km=distancia_km,
                flete_calculado=flete_calculado,
                estado=estado,
                notas=safe_str(get_val("notas")),
            )
            db.add(venta)
            db.flush()  # get id

            # Create entrega automatically if has date
            if fecha_instalacion:
                entrega = Entrega(
                    venta_contado_id=venta.id,
                    cliente_nombre=nombre,
                    cliente_localidad=safe_str(get_val("cliente_localidad")),
                    producto=f"{producto} - {safe_str(get_val('modelo_especifico'))}",
                    fecha_instalacion=fecha_instalacion,
                    rango_horario=safe_str(get_val("rango_horario")),
                    estado="COORDINADA",
                )
                db.add(entrega)

            creados += 1
        except Exception as e:
            errores.append(f"Fila {idx + 2}: {str(e)}")

    db.commit()
    return {
        "importados": creados,
        "errores": errores[:20],
        "mensaje": f"Se importaron {creados} ventas contado correctamente."
    }


COLUMNAS_LEADS = {
    "nombre":            ["nombre", "name", "cliente", "contacto"],
    "telefono":          ["telefono", "tel", "phone", "celular", "whatsapp"],
    "localidad":         ["localidad", "ciudad", "city", "ubicacion", "provincia"],
    "producto_interes":  ["producto", "producto_interes", "interes", "tipo"],
    "modelo_especifico": ["modelo", "modelo_especifico", "model"],
    "forma_pago":        ["forma_pago", "pago", "plan", "financiacion"],
    "origen":            ["origen", "fuente", "source", "canal"],
    "notas":             ["notas", "observaciones", "notes", "comentarios"],
}


@router.post("/api/importar/leads")
async def importar_leads(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Importa leads (prospectos) desde Excel o CSV con distribución automática
    round-robin entre los asesores activos con rol ASESOR_APERTURA.

    Columnas reconocidas: nombre*, telefono*, localidad, producto, modelo,
    forma_pago, origen, notas.
    (* obligatorias)
    """
    import pandas as pd

    content = await file.read()
    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Error leyendo archivo: {e}")

    creados = 0
    errores = []
    asignaciones: dict = {}   # {asesor_id: count} para resumen

    for idx, row in df.iterrows():
        try:
            def get_val(campo):
                col = find_col(df, COLUMNAS_LEADS[campo])
                return row.get(col) if col else None

            nombre = safe_str(get_val("nombre"))
            if not nombre:
                continue

            telefono = safe_str(get_val("telefono"))
            if not telefono:
                errores.append(f"Fila {idx + 2}: falta teléfono para '{nombre}'")
                continue

            # Normalizar producto
            prod_raw = safe_str(get_val("producto_interes")).upper()
            if "PISCINA" in prod_raw:
                producto = "PISCINA"
            elif "COMBO" in prod_raw:
                producto = "COMBO"
            elif "MODULO" in prod_raw or "MÓDULO" in prod_raw:
                producto = "MODULO"
            else:
                producto = "SIN_DEFINIR"

            # Normalizar forma de pago
            pago_raw = safe_str(get_val("forma_pago")).upper()
            if "PMI" in pago_raw:
                forma_pago = "PMI"
            elif "50" in pago_raw or "DIRECTA" in pago_raw:
                forma_pago = "DIRECTA_50"
            elif "CONTADO" in pago_raw:
                forma_pago = "CONTADO"
            else:
                forma_pago = "SIN_DEFINIR"

            # Origen
            origen_raw = safe_str(get_val("origen")).upper()
            origen_map = {
                "INSTAGRAM": "INSTAGRAM", "WHATSAPP": "WHATSAPP",
                "WEB": "WEB", "REFERIDO": "REFERIDO", "IMPORTADO": "IMPORTADO",
            }
            origen = next((v for k, v in origen_map.items() if k in origen_raw), "IMPORTADO")

            # Round-robin
            asesor_id = asignar_asesor_round_robin(db)

            lead = Lead(
                nombre=nombre,
                telefono=telefono,
                localidad=safe_str(get_val("localidad")),
                producto_interes=producto,
                modelo_especifico=safe_str(get_val("modelo_especifico")),
                forma_pago=forma_pago,
                estado="NUEVO",
                asesor_apertura_id=asesor_id,
                origen=origen,
                notas=safe_str(get_val("notas")),
            )
            db.add(lead)
            db.flush()

            if asesor_id:
                asignaciones[asesor_id] = asignaciones.get(asesor_id, 0) + 1

            creados += 1

        except Exception as e:
            errores.append(f"Fila {idx + 2}: {str(e)}")

    db.commit()

    # Construir resumen de asignaciones con nombres
    resumen_asignaciones = []
    for uid, cnt in asignaciones.items():
        u = db.query(Usuario).filter(Usuario.id == uid).first()
        if u:
            resumen_asignaciones.append({"asesor": u.nombre, "leads_asignados": cnt})

    return {
        "importados": creados,
        "errores": errores[:20],
        "asignaciones": resumen_asignaciones,
        "mensaje": f"Se importaron {creados} leads y se distribuyeron entre {len(asignaciones)} asesor(es).",
    }


@router.get("/api/importar/template/{tipo}")
async def download_template(
    tipo: str,
    current_user: Usuario = Depends(require_auth)
):
    """Genera y devuelve un template Excel para importación."""
    import pandas as pd
    from fastapi.responses import StreamingResponse

    if tipo == "financiadas":
        columnas = [
            "nombre", "telefono", "localidad", "producto", "modelo",
            "color", "superficie_m2", "forma_pago", "precio_total",
            "anticipo", "cuotas", "valor_cuota", "fecha_inicio_plan",
            "primer_vencimiento", "cuotas_pagas", "estado_plan", "notas"
        ]
        ejemplo = {
            "nombre": "Juan Pérez", "telefono": "1154321234",
            "localidad": "Pilar", "producto": "PISCINA",
            "modelo": "Minimalista Mediana", "color": "Celeste",
            "superficie_m2": "", "forma_pago": "PMI",
            "precio_total": "2500000", "anticipo": "300000",
            "cuotas": "24", "valor_cuota": "91666",
            "fecha_inicio_plan": "2024-01-01",
            "primer_vencimiento": "2024-02-01",
            "cuotas_pagas": "6", "estado_plan": "ACTIVO", "notas": ""
        }
    elif tipo == "contado":
        columnas = [
            "nombre", "telefono", "localidad", "producto", "modelo",
            "color", "superficie_m2", "precio_final", "forma_pago",
            "fecha_instalacion", "horario", "distancia_km", "estado", "notas"
        ]
        ejemplo = {
            "nombre": "María García", "telefono": "1160987654",
            "localidad": "Tigre", "producto": "MODULO",
            "modelo": "Módulo 36m²", "color": "",
            "superficie_m2": "36", "precio_final": "8500000",
            "forma_pago": "CONTADO",
            "fecha_instalacion": "2024-03-15",
            "horario": "09:00-12:00", "distancia_km": "45",
            "estado": "COORDINADO", "notas": ""
        }
    elif tipo == "leads":
        columnas = ["nombre", "telefono", "localidad", "producto", "modelo", "forma_pago", "origen", "notas"]
        ejemplo = {
            "nombre": "Carlos López", "telefono": "1145678901",
            "localidad": "Zárate", "producto": "PISCINA",
            "modelo": "Minimalista Mediana", "forma_pago": "PMI",
            "origen": "INSTAGRAM", "notas": "",
        }
    else:
        raise HTTPException(400, "Tipo inválido. Use 'financiadas', 'contado' o 'leads'")

    df = pd.DataFrame([ejemplo], columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Importar")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=template_{tipo}.xlsx"}
    )
