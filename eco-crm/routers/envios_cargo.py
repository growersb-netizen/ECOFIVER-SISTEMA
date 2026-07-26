"""
Envíos por Vía Cargo y otras empresas de transporte terrestre.
Gestión completa: cotizar → crear → trackear → entregar.

COTIZADOR: Vía Cargo no tiene API pública. Implementamos:
  1) Tabla de zonas por provincia (configurable en el CRM)
  2) Dimensiones conocidas por modelo de producto
  3) Cálculo de peso volumétrico según fórmula estándar (L×A×H/6000)
  4) Estimación por rango (min-max) con nota de que es aproximado
  5) Link directo al calculador oficial de Vía Cargo con datos pre-cargados
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.database import get_db
from database.models import EnvioViaCargo, VentaContado, Usuario, StockPiscina, StockPanel
from routers.auth import require_auth, get_user_roles, require_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ─── TABLA DE ZONAS VÍA CARGO POR PROVINCIA ───────────────────────────────────
# Zona 1 (más cercana/barata) → Zona 6 (más lejana/cara)
# Basado en la estructura de tarifas de empresas de transporte terrestre argentinas.
# Los precios pueden actualizarse desde el panel de Configuración del CRM.

ZONAS_PROVINCIA: dict = {
    # Zona 1 — CABA y GBA
    "CABA": 1, "CIUDAD AUTÓNOMA DE BUENOS AIRES": 1,
    "BUENOS AIRES GBA": 1, "BUENOS AIRES": 2,
    # Zona 2 — Buenos Aires interior
    "LA PLATA": 2, "MAR DEL PLATA": 2, "BAHIA BLANCA": 2,
    # Zona 3 — Litoral y Cuyo
    "SANTA FE": 3, "CÓRDOBA": 3, "ENTRE RÍOS": 3,
    "MENDOZA": 3, "SAN JUAN": 3, "SAN LUIS": 3,
    # Zona 4 — NOA y parte Norte/Patagonia
    "TUCUMÁN": 4, "SALTA": 4, "JUJUY": 4,
    "CATAMARCA": 4, "LA RIOJA": 4, "SANTIAGO DEL ESTERO": 4,
    "NEUQUÉN": 4, "RÍO NEGRO": 4, "LA PAMPA": 4,
    # Zona 5 — NEA y Patagonia media
    "CORRIENTES": 5, "MISIONES": 5, "CHACO": 5, "FORMOSA": 5,
    "CHUBUT": 5, "SANTA CRUZ": 5,
    # Zona 6 — Patagonia extrema
    "TIERRA DEL FUEGO": 6,
}

# Tarifas base estimadas por zona (en ARS, con factor de ajuste).
# COSTO = base_zona + (peso_cobrable_kg × precio_por_kg_zona)
# peso_cobrable = max(peso_real_kg, peso_volumétrico_kg)
# peso_volumétrico = (largo_cm × ancho_cm × alto_cm) / 6000

TARIFAS_ZONA: dict = {
    # zona: {"base_min": X, "base_max": Y, "por_kg_min": A, "por_kg_max": B}
    1: {"base_min": 3_500,  "base_max": 5_000,  "por_kg_min": 180, "por_kg_max": 280},
    2: {"base_min": 5_000,  "base_max": 7_000,  "por_kg_min": 260, "por_kg_max": 380},
    3: {"base_min": 7_000,  "base_max": 10_000, "por_kg_min": 350, "por_kg_max": 500},
    4: {"base_min": 10_000, "base_max": 15_000, "por_kg_min": 450, "por_kg_max": 650},
    5: {"base_min": 14_000, "base_max": 22_000, "por_kg_min": 580, "por_kg_max": 850},
    6: {"base_min": 22_000, "base_max": 35_000, "por_kg_min": 800, "por_kg_max": 1200},
}

# Dimensiones y pesos conocidos por modelo de producto (largo×ancho×alto en cm, peso real en kg).
# Fuente: dimensiones reales de los productos EcoFiver.
# Estos pueden completarse/corregirse desde el catálogo.
DIMENSIONES_MODELOS: dict = {
    # Piscinas — (largo_cm, ancho_cm, alto_cm, peso_real_kg)
    "Miniportante":              (200, 100, 55, 45),
    "Autoportante":              (250, 130, 60, 70),
    "Minideck Chico":            (210, 90,  45, 40),
    "Minideck Grande":           (280, 120, 55, 65),
    "Minimalista Chica":         (300, 140, 65, 90),
    "Minimalista Mediana":       (380, 160, 70, 130),
    "Minimalista Grande":        (480, 200, 75, 190),
    "Arco Romano Chico Recto":   (320, 150, 65, 100),
    "Arco Romano Chico Curvo":   (320, 150, 65, 105),
    "Arco Romano Mediano Recto": (400, 180, 70, 145),
    "Arco Romano Mediano Curvo": (400, 180, 70, 150),
    "Arco Romano Grande Recto":  (500, 220, 80, 210),
    "Arco Romano Grande Curvo":  (500, 220, 80, 215),
    "Playa y Abanico Chica":     (340, 200, 65, 120),
    "Playa y Abanico Mediana":   (420, 240, 70, 170),
    "Playa y Abanico Grande":    (520, 280, 75, 230),
    # Módulos — se arman en destino, se despachan como paneles
    # Dimensión por PANEL NCE estándar
    "Módulo 6m²":   (240, 120, 20, 28),   # ~3 paneles
    "Módulo 12m²":  (240, 120, 20, 28),   # ~6 paneles
    "Módulo 18m²":  (240, 120, 20, 28),   # ~9 paneles
    "Módulo 24m²":  (240, 120, 20, 28),   # ~12 paneles
}

PANELES_POR_MODULO: dict = {
    "Módulo 6m²": 3, "Módulo 12m²": 6, "Módulo 18m²": 9,
    "Módulo 24m²": 12, "Módulo 30m²": 15, "Módulo 36m²": 18,
}

ESTADOS_COLOR = {
    "PENDIENTE":   ("#f59e0b", "🟡"),
    "EMPACADO":    ("#3b82f6", "🔵"),
    "DESPACHADO":  ("#8b5cf6", "🟣"),
    "EN_TRANSITO": ("#06b6d4", "🔷"),
    "ENTREGADO":   ("#22c55e", "🟢"),
    "PROBLEMA":    ("#ef4444", "🔴"),
}


def _envio_dict(e: EnvioViaCargo) -> dict:
    color, icono = ESTADOS_COLOR.get(e.estado or "PENDIENTE", ("#64748b", "⚪"))
    return {
        "id": e.id,
        "producto": e.producto or "",
        "modelo_especifico": e.modelo_especifico or "",
        "color": e.color or "",
        "cantidad": e.cantidad or 1,
        "desde_stock": e.desde_stock,
        "cliente_nombre": e.cliente_nombre,
        "cliente_telefono": e.cliente_telefono or "",
        "cliente_localidad": e.cliente_localidad or "",
        "provincia": e.provincia or "",
        "sucursal_cargo": e.sucursal_cargo or "",
        "precio_producto": e.precio_producto or 0,
        "costo_flete": e.costo_flete,
        "total": e.total or 0,
        "forma_pago": e.forma_pago or "",
        "estado": e.estado or "PENDIENTE",
        "estado_color": color,
        "estado_icono": icono,
        "numero_remito": e.numero_remito or "",
        "empresa_transporte": e.empresa_transporte or "VIA_CARGO",
        "fecha_despacho": e.fecha_despacho.isoformat() if e.fecha_despacho else "",
        "fecha_entrega_est": e.fecha_entrega_est.isoformat() if e.fecha_entrega_est else "",
        "fecha_entrega_real": e.fecha_entrega_real.isoformat() if e.fecha_entrega_real else "",
        "vendedor_nombre": e.vendedor.nombre if e.vendedor else "",
        "venta_contado_id": e.venta_contado_id,
        "notas": e.notas or "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
    }


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/envios-cargo", response_class=HTMLResponse)
async def envios_cargo_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = get_user_roles(current_user)
    vendedores = db.query(Usuario).filter(Usuario.activo == True).order_by(Usuario.nombre).all()
    return templates.TemplateResponse("envios_cargo.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "vendedores": [{"id": u.id, "nombre": u.nombre} for u in vendedores],
    })


# ─── API LIST ─────────────────────────────────────────────────────────────────

@router.get("/api/envios-cargo")
async def list_envios(
    estado: Optional[str] = None,
    search: Optional[str] = None,
    producto: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    q = db.query(EnvioViaCargo)
    if estado:
        q = q.filter(EnvioViaCargo.estado == estado.upper())
    if producto:
        q = q.filter(EnvioViaCargo.producto == producto.upper())
    if search:
        q = q.filter(
            EnvioViaCargo.cliente_nombre.ilike(f"%{search}%") |
            EnvioViaCargo.cliente_telefono.ilike(f"%{search}%") |
            EnvioViaCargo.numero_remito.ilike(f"%{search}%")
        )
    total = q.count()
    envios = q.order_by(EnvioViaCargo.created_at.desc()).offset(skip).limit(limit).all()

    # Estadísticas para el header
    stats = {
        s: db.query(EnvioViaCargo).filter(EnvioViaCargo.estado == s).count()
        for s in ["PENDIENTE", "EMPACADO", "DESPACHADO", "EN_TRANSITO", "ENTREGADO", "PROBLEMA"]
    }

    return {"total": total, "envios": [_envio_dict(e) for e in envios], "stats": stats}


# ─── API CREATE ───────────────────────────────────────────────────────────────

@router.post("/api/envios-cargo")
async def create_envio(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    for req in ["cliente_nombre", "producto"]:
        if not data.get(req):
            raise HTTPException(400, f"{req} es obligatorio")

    total = float(data.get("total") or 0)
    if not total:
        total = (float(data.get("precio_producto") or 0) +
                 float(data.get("costo_flete") or 0))

    envio = EnvioViaCargo(
        cliente_nombre=data["cliente_nombre"],
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        provincia=data.get("provincia", ""),
        sucursal_cargo=data.get("sucursal_cargo", ""),
        producto=data["producto"].upper(),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color", ""),
        cantidad=int(data.get("cantidad") or 1),
        desde_stock=bool(data.get("desde_stock", False)),
        precio_producto=float(data.get("precio_producto") or 0),
        costo_flete=float(data["costo_flete"]) if data.get("costo_flete") is not None else None,
        total=total,
        forma_pago=data.get("forma_pago", "TRANSFERENCIA"),
        vendedor_id=data.get("vendedor_id") or current_user.id,
        empresa_transporte=data.get("empresa_transporte", "VIA_CARGO"),
        estado="PENDIENTE",
        notas=data.get("notas", ""),
    )
    db.add(envio)

    # Descontar stock si corresponde
    if envio.desde_stock and envio.producto == "PISCINA" and envio.modelo_especifico:
        stock = db.query(StockPiscina).filter(
            StockPiscina.modelo.ilike(f"%{envio.modelo_especifico}%")
        ).first()
        if stock and stock.cantidad >= envio.cantidad:
            stock.cantidad -= envio.cantidad

    db.commit()
    db.refresh(envio)

    # Crear VentaContado asociada automáticamente
    if envio.precio_producto > 0 or envio.total > 0:
        dest = f"{envio.cliente_localidad} ({envio.provincia})" if envio.provincia else envio.cliente_localidad
        v = VentaContado(
            cliente_nombre=envio.cliente_nombre,
            cliente_telefono=envio.cliente_telefono,
            cliente_localidad=dest,
            producto=envio.producto,
            modelo_especifico=envio.modelo_especifico,
            color=envio.color,
            precio_final=envio.total,
            forma_pago=envio.forma_pago,
            vendedor_id=envio.vendedor_id,
            estado="COORDINADO",
            notas=f"Envío por {envio.empresa_transporte}. Sucursal: {envio.sucursal_cargo or 'por definir'}. Envío #ID{envio.id}",
            desde_stock=envio.desde_stock,
        )
        db.add(v)
        db.commit()
        envio.venta_contado_id = v.id
        db.commit()

    return {"ok": True, "id": envio.id, "venta_contado_id": envio.venta_contado_id}


# ─── API UPDATE ───────────────────────────────────────────────────────────────

@router.patch("/api/envios-cargo/{envio_id}")
async def update_envio(
    envio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    e = db.query(EnvioViaCargo).filter(EnvioViaCargo.id == envio_id).first()
    if not e:
        raise HTTPException(404, "Envío no encontrado")
    data = await request.json()

    for campo in ["estado", "numero_remito", "empresa_transporte",
                  "notas", "sucursal_cargo", "cliente_localidad", "provincia"]:
        if campo in data:
            setattr(e, campo, data[campo])

    for campo_dt in ["fecha_despacho", "fecha_entrega_est", "fecha_entrega_real"]:
        if data.get(campo_dt):
            try:
                setattr(e, campo_dt, datetime.fromisoformat(data[campo_dt]))
            except Exception:
                pass

    if "costo_flete" in data and data["costo_flete"] is not None:
        e.costo_flete = float(data["costo_flete"])
        e.total = (e.precio_producto or 0) + (e.costo_flete or 0)

    if "precio_producto" in data and data["precio_producto"] is not None:
        e.precio_producto = float(data["precio_producto"])
        e.total = (e.precio_producto or 0) + (e.costo_flete or 0)

    db.commit()
    return {"ok": True, "envio": _envio_dict(e)}


# ─── API STOCK (para el cotizador en la página) ───────────────────────────────
# IMPORTANTE: rutas estáticas ANTES de /{envio_id} para evitar colisión de paths

@router.get("/api/envios-cargo/stock/disponible")
async def stock_para_envio(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    from routers.catalogo import load_catalogo
    cat = load_catalogo()
    precios_piscinas = cat.get("piscinas", {}).get("precios", {})

    piscinas = db.query(StockPiscina).filter(StockPiscina.cantidad > 0).order_by(StockPiscina.modelo).all()
    return {
        "piscinas": [
            {
                "id": p.id, "modelo": p.modelo, "color": p.color or "",
                "cantidad": p.cantidad,
                "precio": precios_piscinas.get(p.modelo),
            }
            for p in piscinas
        ],
        "modulos_catalogo": cat.get("modulos", {}).get("superficies_m2", []),
        "colores_piscinas": cat.get("piscinas", {}).get("colores", []),
        "modelos_piscinas": cat.get("piscinas", {}).get("modelos", []),
        "precios_modulos": cat.get("modulos", {}).get("precios", {}),
        "precios_piscinas": precios_piscinas,
    }


# ─── COTIZADOR DE FLETE ───────────────────────────────────────────────────────
# Debe estar ANTES de /{envio_id} para que FastAPI no intente parsear "cotizar-flete" como int

@router.get("/api/envios-cargo/cotizar-flete")
async def cotizar_flete(
    provincia: str,
    modelo: str,
    cantidad: int = 1,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Estima el costo de flete para un producto hacia una provincia.
    Usa zonas y tarifas de referencia configuradas internamente.
    Retorna rango min-max en ARS junto a los datos técnicos usados.
    """
    # Normalizar y buscar zona
    prov_norm = provincia.strip().upper()
    zona = ZONAS_PROVINCIA.get(prov_norm)
    if zona is None:
        for k, v in ZONAS_PROVINCIA.items():
            if prov_norm in k or k in prov_norm:
                zona = v
                break
    if zona is None:
        zona = 3  # zona media por defecto si no se identifica la provincia

    # Obtener dimensiones del modelo
    dims = DIMENSIONES_MODELOS.get(modelo)
    modelo_match = modelo
    if dims is None:
        for k, v in DIMENSIONES_MODELOS.items():
            if modelo.lower() in k.lower() or k.lower() in modelo.lower():
                dims = v
                modelo_match = k
                break

    if dims is None:
        raise HTTPException(
            400,
            f"Modelo '{modelo}' no encontrado. Modelos disponibles: {', '.join(DIMENSIONES_MODELOS.keys())}"
        )

    largo_cm, ancho_cm, alto_cm, peso_real_kg = dims

    # Peso volumétrico estándar courier (L×A×H cm / 6000 = kg)
    peso_vol_kg = (largo_cm * ancho_cm * alto_cm) / 6000
    peso_cobrable_unitario = max(peso_real_kg, peso_vol_kg)

    # Para módulos: se despachan en paneles
    es_modulo = modelo_match.startswith("Módulo")
    if es_modulo:
        paneles_por_unidad = PANELES_POR_MODULO.get(modelo_match, 6)
        bultos_total = cantidad * paneles_por_unidad
        peso_cobrable_total = peso_cobrable_unitario * bultos_total
        peso_real_total = peso_real_kg * bultos_total
        peso_vol_total = peso_vol_kg * bultos_total
    else:
        bultos_total = cantidad
        peso_cobrable_total = peso_cobrable_unitario * cantidad
        peso_real_total = peso_real_kg * cantidad
        peso_vol_total = peso_vol_kg * cantidad

    # Calcular rango de costos
    tarifas = TARIFAS_ZONA[zona]
    costo_min = tarifas["base_min"] + (peso_cobrable_total * tarifas["por_kg_min"])
    costo_max = tarifas["base_max"] + (peso_cobrable_total * tarifas["por_kg_max"])

    return {
        "provincia": provincia,
        "zona": zona,
        "modelo": modelo_match,
        "cantidad": cantidad,
        "bultos": int(bultos_total),
        "peso_real_kg": round(peso_real_total, 1),
        "peso_vol_kg": round(peso_vol_total, 1),
        "peso_cobrable_kg": round(peso_cobrable_total, 1),
        "costo_min": int(round(costo_min)),
        "costo_max": int(round(costo_max)),
        "costo_promedio": int(round((costo_min + costo_max) / 2)),
        "dimensiones": {
            "largo_cm": largo_cm,
            "ancho_cm": ancho_cm,
            "alto_cm": alto_cm,
            "peso_unitario_kg": peso_real_kg,
        },
        "referencia": f"Zona {zona} — estimación orientativa",
        "nota": (
            "Los valores son estimativos basados en tarifas de referencia. "
            "Confirmá el precio exacto en la sucursal o calculadora oficial antes de cotizar."
        ),
        "link_calculadora": "https://www.viacargo.com.ar/calculadora",
    }


# ─── API DETAIL ───────────────────────────────────────────────────────────────
# Va AL FINAL para no interceptar rutas estáticas como /stock/disponible o /cotizar-flete

@router.get("/api/envios-cargo/{envio_id}")
async def get_envio(
    envio_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    e = db.query(EnvioViaCargo).filter(EnvioViaCargo.id == envio_id).first()
    if not e:
        raise HTTPException(404, "Envío no encontrado")
    return _envio_dict(e)
