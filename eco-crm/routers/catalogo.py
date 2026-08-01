"""
Catálogo de productos ampliable dinámicamente.
Modelos de piscinas y módulos habitacionales.
"""
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Usuario, PrecioHistorial
from routers.auth import require_auth, require_roles, get_user_roles, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")

FOTOS_DIR = Path("data/catalogo_fotos")  # dentro del volumen persistente (/app/data) — no ephemeral
FOTOS_DIR.mkdir(parents=True, exist_ok=True)
_EXTENSIONES_FOTO_VALIDAS = {".jpg", ".jpeg", ".png", ".webp"}
_MEDIA_TYPE_FOTO = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _write_auth(x_api_key: Optional[str], current_user: Optional[Usuario]):
    """Escritura de catálogo: sesión con rol de gestión, o X-API-Key (integraciones)."""
    if x_api_key and x_api_key == API_KEY:
        return
    if current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")):
        return
    raise HTTPException(403, "Sin permisos")

CATALOGO_FILE = Path("data/catalogo.json")
CATALOGO_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_CATALOGO = {
    "piscinas": {
        "modelos": [
            "Arco Romano Chico Recto", "Arco Romano Chico Curvo",
            "Arco Romano Mediano Recto", "Arco Romano Mediano Curvo",
            "Arco Romano Grande Recto", "Arco Romano Grande Curvo",
            "Minimalista Chica", "Minimalista Mediana", "Minimalista Grande",
            "Playa y Abanico Chica", "Playa y Abanico Mediana", "Playa y Abanico Grande",
            "Miniportante", "Autoportante", "Minideck Chico", "Minideck Grande"
        ],
        "colores": ["Blanco", "Beige", "Verde agua", "Celeste", "Azul"],
        "precios": {},          # precio CONTADO (el que se cotiza al cliente)
        "precios_lista": {},    # precio LISTA (base para financiación/cuotas)
        "fotos": {},            # modelo -> [urls] (para armar publicaciones de ML automáticamente)
        "cuotas_max": 36,       # plazo más largo ofrecido — usado para publicar en ML al valor de la cuota
    },
    "modulos": {
        # Viviendas modulares: se venden financiadas, por m². No confundir con
        # "modulos_deposito" (calidad inferior, de contado, para depósito).
        "superficies_m2": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72],
        "tecnologia": "NCE (Nautical Composite Engineering)",
        "modelos_custom": [],
        "precios": {},          # precio CONTADO
        "precios_lista": {},    # precio LISTA (base para financiación/cuotas)
        "fotos": {},            # superficie (str) o modelo_custom -> [urls]
        "cuotas_max": 60,       # plazo más largo ofrecido — usado para publicar en ML al valor de la cuota
    },
    "combos": {},  # nombre -> {"precio_lista":..., "precio_contado":..., "descripcion":..., "fotos": [...]}
    "modulos_deposito": {
        # Línea de módulos de calidad inferior a las viviendas modulares, para uso
        # como depósito. Se venden DE CONTADO (no financiado). Tamaños fijos x línea.
        "descripcion_base": (
            "Sin acabado final ni terminación de piso (piso colocado sin revestimiento). "
            "Incluye aberturas, pintura completa blanca e instalación eléctrica interna para luz."
        ),
        "descripcion_premium": (
            "Doble aislante con malla, terminación en placas de PRFV, incluye piso. "
            "Incluye aberturas, pintura completa blanca e instalación eléctrica interna para luz."
        ),
        "tamanos": {
            "6":  {"BASE": {"precio_contado": 2990000, "fotos": []}, "PREMIUM": {"precio_contado": 3690000, "fotos": []}},
            "12": {"BASE": {"precio_contado": 4990000, "fotos": []}, "PREMIUM": {"precio_contado": 5990000, "fotos": []}},
            "18": {"BASE": {"precio_contado": 7490000, "fotos": []}, "PREMIUM": {"precio_contado": 8990000, "fotos": []}},
            "24": {"BASE": {"precio_contado": None, "fotos": []}, "PREMIUM": {"precio_contado": None, "fotos": []}},
        },
    },
}


def load_catalogo() -> dict:
    if CATALOGO_FILE.exists():
        try:
            cat = json.loads(CATALOGO_FILE.read_text(encoding="utf-8"))
            # Migración: completar claves nuevas si el archivo es de un esquema viejo
            cambiado = False
            for seccion in ("piscinas", "modulos"):
                cat.setdefault(seccion, {})
                for campo, default in DEFAULT_CATALOGO[seccion].items():
                    if campo not in cat[seccion]:
                        cat[seccion][campo] = default if not isinstance(default, (list, dict)) else type(default)()
                        cambiado = True
            if "combos" not in cat:
                cat["combos"] = {}
                cambiado = True
            if "modulos_deposito" not in cat:
                cat["modulos_deposito"] = json.loads(json.dumps(DEFAULT_CATALOGO["modulos_deposito"]))
                cambiado = True
            if cambiado:
                save_catalogo(cat)
            return cat
        except Exception:
            pass
    save_catalogo(DEFAULT_CATALOGO)
    return DEFAULT_CATALOGO


def save_catalogo(data: dict):
    CATALOGO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_modelos_piscina() -> List[str]:
    return load_catalogo()["piscinas"]["modelos"]


def get_all_modelos_modulo() -> List[str]:
    cat = load_catalogo()
    sup = cat["modulos"]["superficies_m2"]
    custom = cat["modulos"].get("modelos_custom", [])
    standard = [f"Módulo {m}m²" for m in sup]
    return standard + custom


# ─── HTML PAGE ────────────────────────────────────────────────────────────────

@router.get("/catalogo-admin", response_class=HTMLResponse)
async def catalogo_admin_page(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    from routers.auth import get_user_roles
    roles = get_user_roles(user)
    if "ADMIN" not in roles:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/", 302)
    cat = load_catalogo()
    return templates.TemplateResponse("catalogo_admin.html", {
        "request": request,
        "user": user,
        "roles": roles,
        "catalogo": cat,
    })


# ─── API ──────────────────────────────────────────────────────────────────────

@router.get("/api/catalogo")
async def get_catalogo(current_user: Usuario = Depends(require_auth)):
    cat = load_catalogo()
    return {
        "piscinas": {
            "modelos": cat["piscinas"]["modelos"],
            "colores": cat["piscinas"]["colores"],
            "precios": cat["piscinas"].get("precios", {}),
            "precios_lista": cat["piscinas"].get("precios_lista", {}),
            "fotos": cat["piscinas"].get("fotos", {}),
            "cuotas_max": cat["piscinas"].get("cuotas_max", 36),
        },
        "modulos": {
            "superficies_m2": cat["modulos"]["superficies_m2"],
            "tecnologia": cat["modulos"]["tecnologia"],
            "modelos_custom": cat["modulos"].get("modelos_custom", []),
            "precios": cat["modulos"].get("precios", {}),
            "precios_lista": cat["modulos"].get("precios_lista", {}),
            "fotos": cat["modulos"].get("fotos", {}),
            "cuotas_max": cat["modulos"].get("cuotas_max", 60),
        },
        "combos": cat.get("combos", {}),
        "modulos_deposito": cat.get("modulos_deposito", DEFAULT_CATALOGO["modulos_deposito"]),
    }


@router.get("/api/catalogo/publico")
async def get_catalogo_publico():
    """Catálogo público sin autenticación — usado por web, agentes IA, simulador."""
    cat = load_catalogo()
    return {
        "piscinas": {
            "modelos": cat["piscinas"]["modelos"],
            "colores": cat["piscinas"]["colores"],
            "precios": cat["piscinas"].get("precios", {}),
            "precios_lista": cat["piscinas"].get("precios_lista", {}),
        },
        "modulos": {
            "superficies_m2": cat["modulos"]["superficies_m2"],
            "tecnologia": cat["modulos"]["tecnologia"],
            "modelos_custom": cat["modulos"].get("modelos_custom", []),
            "precios": cat["modulos"].get("precios", {}),
            "precios_lista": cat["modulos"].get("precios_lista", {}),
        },
        "combos": cat.get("combos", {}),
    }


# ─── FOTOS (para autocompletar publicaciones de MercadoLibre) ────────────────

@router.post("/api/catalogo/fotos/upload")
async def upload_foto_catalogo(
    request: Request,
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Sube una imagen al volumen persistente y devuelve su URL pública (para MercadoLibre y el catálogo)."""
    _write_auth(x_api_key, current_user)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _EXTENSIONES_FOTO_VALIDAS:
        raise HTTPException(400, f"Formato no soportado. Usar: {', '.join(sorted(_EXTENSIONES_FOTO_VALIDAS))}")
    contenido = await file.read()
    if len(contenido) > 8 * 1024 * 1024:
        raise HTTPException(400, "La imagen no puede superar 8MB")
    nombre = f"{uuid.uuid4().hex}{ext}"
    (FOTOS_DIR / nombre).write_bytes(contenido)

    from routers.contratos import _abs_url
    return {"ok": True, "filename": nombre, "url": _abs_url(request, f"/api/catalogo/fotos/{nombre}")}


@router.get("/api/catalogo/fotos/{filename}")
async def get_foto_catalogo(filename: str):
    """
    Público y SIN auth a propósito: MercadoLibre necesita poder buscar la
    imagen directamente desde sus servidores al crear la publicación.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Nombre de archivo inválido")
    path = FOTOS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Imagen no encontrada")
    media_type = _MEDIA_TYPE_FOTO.get(path.suffix.lower().lstrip("."), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type)


@router.put("/api/catalogo/fotos")
async def set_fotos_catalogo(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Asocia una lista de URLs de foto a una clave del catálogo.
    Body: { "tipo": "piscinas"|"modulos"|"combos"|"modulos_deposito",
            "clave": "<modelo o tamaño_LINEA>", "fotos": ["url1", "url2", ...] }
    Reemplaza la lista completa (no agrega incremental).
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    tipo = data.get("tipo", "")
    clave = data.get("clave", "")
    fotos = data.get("fotos", [])
    if tipo not in ("piscinas", "modulos", "combos", "modulos_deposito") or not clave:
        raise HTTPException(400, "tipo/clave inválidos")
    if not isinstance(fotos, list):
        raise HTTPException(400, "fotos debe ser una lista de URLs")

    cat = load_catalogo()
    if tipo == "combos":
        if clave not in cat.get("combos", {}):
            raise HTTPException(404, "Combo no encontrado")
        cat["combos"][clave]["fotos"] = fotos
    elif tipo == "modulos_deposito":
        try:
            tamano, linea = clave.split("_", 1)
        except ValueError:
            raise HTTPException(400, "clave debe tener formato '<tamano>_<BASE|PREMIUM>'")
        tamanos = cat.setdefault("modulos_deposito", {}).setdefault("tamanos", {})
        if tamano not in tamanos or linea not in tamanos[tamano]:
            raise HTTPException(404, "Tamaño/línea no encontrados")
        tamanos[tamano][linea]["fotos"] = fotos
    else:
        cat[tipo].setdefault("fotos", {})
        cat[tipo]["fotos"][clave] = fotos

    save_catalogo(cat)
    return {"ok": True, "tipo": tipo, "clave": clave, "fotos": fotos}


# ─── MÓDULOS DE DEPÓSITO (línea de contado, calidad inferior) ────────────────

@router.get("/api/catalogo/modulos-deposito")
async def get_modulos_deposito(current_user: Usuario = Depends(require_auth)):
    cat = load_catalogo()
    return cat.get("modulos_deposito", DEFAULT_CATALOGO["modulos_deposito"])


@router.put("/api/catalogo/modulos-deposito/precio")
async def set_precio_modulo_deposito(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Body: { "tamano": "6"|"12"|"18"|"24", "linea": "BASE"|"PREMIUM", "precio_contado": 2990000 }"""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    tamano = str(data.get("tamano", ""))
    linea = data.get("linea", "")
    precio = data.get("precio_contado")
    if linea not in ("BASE", "PREMIUM") or precio is None:
        raise HTTPException(400, "linea debe ser BASE o PREMIUM, precio_contado requerido")

    cat = load_catalogo()
    tamanos = cat.setdefault("modulos_deposito", {}).setdefault("tamanos", {})
    if tamano not in tamanos:
        tamanos[tamano] = {"BASE": {"precio_contado": None, "fotos": []}, "PREMIUM": {"precio_contado": None, "fotos": []}}
    valor_anterior = tamanos[tamano][linea].get("precio_contado")
    nuevo_valor = float(precio)
    if valor_anterior != nuevo_valor and current_user:
        db.add(PrecioHistorial(
            clave=f"modulos_deposito.{tamano}.{linea}",
            valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
            valor_nuevo=nuevo_valor,
            cambiado_por_id=current_user.id,
        ))
        db.commit()
    tamanos[tamano][linea]["precio_contado"] = nuevo_valor
    save_catalogo(cat)
    return {"ok": True, "tamanos": tamanos}


@router.get("/api/catalogo/modelos")
async def get_modelos(
    tipo: Optional[str] = None,
    current_user: Usuario = Depends(require_auth)
):
    if tipo == "PISCINA":
        return {"modelos": get_all_modelos_piscina()}
    elif tipo == "MODULO":
        return {"modelos": get_all_modelos_modulo()}
    else:
        return {
            "piscinas": get_all_modelos_piscina(),
            "modulos": get_all_modelos_modulo(),
        }


# ─── PISCINAS ─────────────────────────────────────────────────────────────────

@router.post("/api/catalogo/piscinas/modelos")
async def add_modelo_piscina(
    request: Request,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    nombre = data.get("nombre", "").strip()
    if not nombre:
        raise HTTPException(400, "Nombre requerido")

    cat = load_catalogo()
    if nombre in cat["piscinas"]["modelos"]:
        raise HTTPException(400, "El modelo ya existe")
    cat["piscinas"]["modelos"].append(nombre)
    save_catalogo(cat)
    return {"ok": True, "modelos": cat["piscinas"]["modelos"]}


@router.put("/api/catalogo/piscinas/modelos")
async def set_modelos_piscinas(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Reemplaza la lista completa de modelos de piscinas. Body: { modelos: [...] }"""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    modelos = data.get("modelos")
    if not isinstance(modelos, list) or not modelos:
        raise HTTPException(400, "modelos debe ser una lista no vacía")
    cat = load_catalogo()
    cat["piscinas"]["modelos"] = modelos
    save_catalogo(cat)
    return {"ok": True, "modelos": modelos}


@router.delete("/api/catalogo/piscinas/modelos/{nombre}")
async def delete_modelo_piscina(
    nombre: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if nombre not in cat["piscinas"]["modelos"]:
        raise HTTPException(404, "Modelo no encontrado")
    cat["piscinas"]["modelos"].remove(nombre)
    save_catalogo(cat)
    return {"ok": True}


@router.post("/api/catalogo/piscinas/colores")
async def add_color_piscina(
    request: Request,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    color = data.get("color", "").strip()
    if not color:
        raise HTTPException(400, "Color requerido")
    cat = load_catalogo()
    if color in cat["piscinas"]["colores"]:
        raise HTTPException(400, "El color ya existe")
    cat["piscinas"]["colores"].append(color)
    save_catalogo(cat)
    return {"ok": True, "colores": cat["piscinas"]["colores"]}


@router.delete("/api/catalogo/piscinas/colores/{color}")
async def delete_color_piscina(
    color: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if color not in cat["piscinas"]["colores"]:
        raise HTTPException(404, "Color no encontrado")
    cat["piscinas"]["colores"].remove(color)
    save_catalogo(cat)
    return {"ok": True}


@router.put("/api/catalogo/piscinas/precios")
async def update_precios_piscinas(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    cat = load_catalogo()
    precios_actuales = cat["piscinas"].get("precios", {})
    for clave, nuevo_valor in data.items():
        valor_anterior = precios_actuales.get(clave)
        if valor_anterior != nuevo_valor:
            db.add(PrecioHistorial(
                clave=f"piscinas.{clave}",
                valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
                valor_nuevo=float(nuevo_valor),
                cambiado_por_id=current_user.id,
            ))
    cat["piscinas"]["precios"].update(data)
    save_catalogo(cat)
    db.commit()
    return {"ok": True}


# ─── MÓDULOS ──────────────────────────────────────────────────────────────────

@router.post("/api/catalogo/modulos/superficies")
async def add_superficie(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    _write_auth(x_api_key, current_user)
    data = await request.json()
    m2 = data.get("m2")
    if m2 is None:
        raise HTTPException(400, "m2 requerido")
    try:
        m2 = int(m2)
    except Exception:
        raise HTTPException(400, "m2 debe ser un número")
    cat = load_catalogo()
    if m2 in cat["modulos"]["superficies_m2"]:
        raise HTTPException(400, "La superficie ya existe")
    cat["modulos"]["superficies_m2"].append(m2)
    cat["modulos"]["superficies_m2"].sort()
    save_catalogo(cat)
    return {"ok": True, "superficies": cat["modulos"]["superficies_m2"]}


@router.delete("/api/catalogo/modulos/superficies/{m2}")
async def delete_superficie(
    m2: int,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if m2 not in cat["modulos"]["superficies_m2"]:
        raise HTTPException(404, "Superficie no encontrada")
    cat["modulos"]["superficies_m2"].remove(m2)
    save_catalogo(cat)
    return {"ok": True}


@router.post("/api/catalogo/modulos/modelos-custom")
async def add_modelo_modulo_custom(
    request: Request,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    nombre = data.get("nombre", "").strip()
    if not nombre:
        raise HTTPException(400, "Nombre requerido")
    cat = load_catalogo()
    if nombre in cat["modulos"].get("modelos_custom", []):
        raise HTTPException(400, "El modelo ya existe")
    if "modelos_custom" not in cat["modulos"]:
        cat["modulos"]["modelos_custom"] = []
    cat["modulos"]["modelos_custom"].append(nombre)
    save_catalogo(cat)
    return {"ok": True, "modelos_custom": cat["modulos"]["modelos_custom"]}


@router.delete("/api/catalogo/modulos/modelos-custom/{nombre}")
async def delete_modelo_modulo_custom(
    nombre: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    custom = cat["modulos"].get("modelos_custom", [])
    if nombre not in custom:
        raise HTTPException(404, "Modelo no encontrado")
    custom.remove(nombre)
    cat["modulos"]["modelos_custom"] = custom
    save_catalogo(cat)
    return {"ok": True}


@router.put("/api/catalogo/modulos/precios")
async def update_precios_modulos(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    data = await request.json()
    cat = load_catalogo()
    precios_actuales = cat["modulos"].get("precios", {})
    for clave, nuevo_valor in data.items():
        valor_anterior = precios_actuales.get(clave)
        if valor_anterior != nuevo_valor:
            db.add(PrecioHistorial(
                clave=f"modulos.{clave}",
                valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
                valor_nuevo=float(nuevo_valor),
                cambiado_por_id=current_user.id,
            ))
    cat["modulos"]["precios"].update(data)
    save_catalogo(cat)
    db.commit()
    return {"ok": True}


# ─── PRECIOS UNIFICADO + HISTORIAL ───────────────────────────────────────────

@router.put("/api/catalogo/precios")
async def update_precios_unificado(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Body: { "tipo": "piscinas"|"modulos", "campo": "precios"|"precios_lista" (opcional, default "precios"),
            "precios": { "clave": valor, ... } }
    "precios" = precio CONTADO (el que se cotiza al cliente).
    "precios_lista" = precio LISTA (base para financiación/cuotas — no confundir).
    """
    _write_auth(x_api_key, current_user)
    data = await request.json()
    tipo = data.get("tipo", "").lower()
    campo = data.get("campo", "precios")
    if tipo not in ("piscinas", "modulos"):
        raise HTTPException(400, "tipo debe ser 'piscinas' o 'modulos'")
    if campo not in ("precios", "precios_lista"):
        raise HTTPException(400, "campo debe ser 'precios' o 'precios_lista'")
    nuevos_precios = data.get("precios", {})
    cat = load_catalogo()
    cat[tipo].setdefault(campo, {})
    precios_actuales = cat[tipo].get(campo, {})
    for clave, nuevo_valor in nuevos_precios.items():
        valor_anterior = precios_actuales.get(clave)
        if valor_anterior != nuevo_valor:
            db.add(PrecioHistorial(
                clave=f"{tipo}.{campo}.{clave}",
                valor_anterior=float(valor_anterior) if valor_anterior is not None else None,
                valor_nuevo=float(nuevo_valor),
                cambiado_por_id=current_user.id if current_user else None,
            ))
    cat[tipo][campo].update(nuevos_precios)
    save_catalogo(cat)
    db.commit()
    return {"ok": True, "tipo": tipo, "campo": campo, "precios_actualizados": len(nuevos_precios)}


# ─── COMBOS ───────────────────────────────────────────────────────────────────

@router.put("/api/catalogo/combos/{nombre}")
async def upsert_combo(
    nombre: str,
    request: Request,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Body: { precio_lista, precio_contado, descripcion, plazos_max }"""
    _write_auth(x_api_key, current_user)
    data = await request.json()
    cat = load_catalogo()
    cat.setdefault("combos", {})
    fotos_existentes = cat["combos"].get(nombre, {}).get("fotos", [])
    cat["combos"][nombre] = {
        "precio_lista": float(data.get("precio_lista") or 0),
        "precio_contado": float(data["precio_contado"]) if data.get("precio_contado") else None,
        "descripcion": data.get("descripcion", ""),
        "plazos_max": int(data.get("plazos_max") or 60),
        "fotos": fotos_existentes,  # se administran vía PUT /api/catalogo/fotos, no acá
    }
    save_catalogo(cat)
    return {"ok": True, "combos": cat["combos"]}


@router.delete("/api/catalogo/combos/{nombre}")
async def delete_combo(
    nombre: str,
    current_user: Usuario = Depends(require_roles("COORDINADOR_OPERATIVO"))
):
    cat = load_catalogo()
    if nombre not in cat.get("combos", {}):
        raise HTTPException(404, "Combo no encontrado")
    del cat["combos"][nombre]
    save_catalogo(cat)
    return {"ok": True}


@router.get("/api/catalogo/combos")
async def list_combos(current_user: Usuario = Depends(require_auth)):
    return load_catalogo().get("combos", {})


@router.get("/api/catalogo/historial-precios")
async def get_historial_precios(
    tipo: Optional[str] = None,
    clave: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(PrecioHistorial)
    if tipo:
        q = q.filter(PrecioHistorial.clave.like(f"{tipo}.%"))
    if clave:
        q = q.filter(PrecioHistorial.clave == clave)
    historial = q.order_by(PrecioHistorial.created_at.desc()).limit(limit).all()
    return [{
        "id": h.id,
        "clave": h.clave,
        "valor_anterior": float(h.valor_anterior) if h.valor_anterior is not None else None,
        "valor_nuevo": float(h.valor_nuevo) if h.valor_nuevo is not None else None,
        "cambiado_por": h.cambiado_por.nombre if h.cambiado_por else "",
        "created_at": h.created_at.isoformat() if h.created_at else "",
    } for h in historial]
