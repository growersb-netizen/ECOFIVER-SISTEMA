"""
Biblioteca de activos visuales y copies — Eco Módulos & Piscinas.
Almacena imágenes subidas por el usuario y copies pre-aprobados.
El scheduler y Ecopost los usan para publicaciones orgánicas y anuncios.

Estructura en /data/:
  assets.json                    → metadata de imágenes y copies
  assets/images/<id>.jpg/png     → archivos de imagen
"""

import os
import json
import uuid
import base64
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_DATA_DIR   = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent.parent
ASSETS_DIR  = _DATA_DIR / "assets" / "images"
ASSETS_JSON = _DATA_DIR / "assets.json"

# Etiquetas válidas para filtrar
ETIQUETAS_VALIDAS = [
    "modulos", "piscinas", "combo",
    "contado", "financiado",
    "familia", "obra", "instalacion",
    "exterior", "interior", "verano", "invierno",
    "historia", "general"
]


# ── Inicialización ────────────────────────────────────────────────────────────

def _init():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if not ASSETS_JSON.exists():
        ASSETS_JSON.write_text(json.dumps({"imagenes": [], "copies": []}, ensure_ascii=False, indent=2))

def _cargar() -> dict:
    _init()
    try:
        return json.loads(ASSETS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"imagenes": [], "copies": []}

def _guardar(data: dict):
    _init()
    ASSETS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Imágenes ──────────────────────────────────────────────────────────────────

def guardar_imagen(b64_data: str, nombre: str, etiquetas: list[str],
                   descripcion: str = "", mime: str = "image/jpeg") -> dict:
    """
    Guarda una imagen en disco y su metadata en assets.json.
    b64_data: string base64 (sin prefijo data:...).
    Retorna el dict de metadata del asset.
    """
    ext = "png" if "png" in mime else "jpg"
    asset_id = str(uuid.uuid4())[:8]
    filename = f"{asset_id}.{ext}"
    filepath = ASSETS_DIR / filename

    # Guardar archivo
    raw = base64.b64decode(b64_data)
    filepath.write_bytes(raw)

    # Metadata
    meta = {
        "id": asset_id,
        "nombre": nombre or filename,
        "filename": filename,
        "mime": mime,
        "etiquetas": [t for t in etiquetas if t in ETIQUETAS_VALIDAS],
        "descripcion": descripcion,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "origen": "subida",   # 'subida' | 'ia'
        "activa": True,
    }

    data = _cargar()
    data["imagenes"].append(meta)
    _guardar(data)
    logger.info(f"[assets] Imagen guardada: {filename} etiquetas={etiquetas}")
    return meta


def guardar_imagen_ia(b64_data: str, descripcion: str, etiquetas: list[str],
                      mime: str = "image/png") -> dict:
    """Igual que guardar_imagen pero marca origen='ia'."""
    meta = guardar_imagen(b64_data, f"IA_{datetime.now().strftime('%d%m%y_%H%M')}", etiquetas, descripcion, mime)
    meta["origen"] = "ia"
    data = _cargar()
    for img in data["imagenes"]:
        if img["id"] == meta["id"]:
            img["origen"] = "ia"
    _guardar(data)
    return meta


def listar_imagenes(etiquetas: list[str] | None = None, solo_activas: bool = True) -> list[dict]:
    """Retorna lista de metadata de imágenes, opcionalmente filtrada por etiquetas."""
    data = _cargar()
    imgs = data.get("imagenes", [])
    if solo_activas:
        imgs = [i for i in imgs if i.get("activa", True)]
    if etiquetas:
        imgs = [i for i in imgs if any(t in i.get("etiquetas", []) for t in etiquetas)]
    return sorted(imgs, key=lambda x: x.get("fecha", ""), reverse=True)


def leer_imagen_b64(asset_id: str) -> tuple[str, str] | None:
    """Retorna (base64, mime) de la imagen, o None si no existe."""
    data = _cargar()
    meta = next((i for i in data["imagenes"] if i["id"] == asset_id), None)
    if not meta:
        return None
    filepath = ASSETS_DIR / meta["filename"]
    if not filepath.exists():
        return None
    raw = filepath.read_bytes()
    return base64.b64encode(raw).decode(), meta.get("mime", "image/jpeg")


def eliminar_imagen(asset_id: str) -> bool:
    data = _cargar()
    orig = len(data["imagenes"])
    meta = next((i for i in data["imagenes"] if i["id"] == asset_id), None)
    if meta:
        filepath = ASSETS_DIR / meta["filename"]
        if filepath.exists():
            filepath.unlink()
    data["imagenes"] = [i for i in data["imagenes"] if i["id"] != asset_id]
    _guardar(data)
    return len(data["imagenes"]) < orig


def toggle_imagen(asset_id: str, activa: bool) -> bool:
    data = _cargar()
    for img in data["imagenes"]:
        if img["id"] == asset_id:
            img["activa"] = activa
            _guardar(data)
            return True
    return False


def elegir_imagen_para_contenido(etiquetas: list[str]) -> dict | None:
    """
    Elige aleatoriamente una imagen activa que coincida con las etiquetas.
    Usada por el scheduler para posts orgánicos.
    """
    import random
    candidatas = listar_imagenes(etiquetas=etiquetas, solo_activas=True)
    if not candidatas:
        # Fallback: cualquier imagen activa
        candidatas = listar_imagenes(solo_activas=True)
    if not candidatas:
        return None
    return random.choice(candidatas)


# ── Copies ────────────────────────────────────────────────────────────────────

def guardar_copy(texto: str, producto: str, objetivo: str,
                 etiquetas: list[str] | None = None, copy_id: str | None = None) -> dict:
    """
    Guarda o actualiza un copy aprobado.
    producto: 'modulos' | 'piscinas' | 'combo' | 'general'
    objetivo: 'captar' | 'cerrar' | 'nutrir' | 'financiacion' | 'general'
    """
    data = _cargar()
    if copy_id:
        # Actualizar existente
        for c in data["copies"]:
            if c["id"] == copy_id:
                c["texto"]    = texto
                c["producto"] = producto
                c["objetivo"] = objetivo
                c["etiquetas"] = etiquetas or []
                c["fecha_mod"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                _guardar(data)
                return c
    # Nuevo copy
    nuevo = {
        "id":       str(uuid.uuid4())[:8],
        "texto":    texto,
        "producto": producto,
        "objetivo": objetivo,
        "etiquetas": etiquetas or [],
        "fecha":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "activo":   True,
    }
    data["copies"].append(nuevo)
    _guardar(data)
    return nuevo


def listar_copies(producto: str | None = None, objetivo: str | None = None,
                  solo_activos: bool = True) -> list[dict]:
    data = _cargar()
    copies = data.get("copies", [])
    if solo_activos:
        copies = [c for c in copies if c.get("activo", True)]
    if producto:
        copies = [c for c in copies if c.get("producto") in (producto, "general")]
    if objetivo:
        copies = [c for c in copies if c.get("objetivo") in (objetivo, "general")]
    return sorted(copies, key=lambda x: x.get("fecha", ""), reverse=True)


def elegir_copy_para_contenido(producto: str, objetivo: str = "captar") -> dict | None:
    """Elige aleatoriamente un copy aprobado para el tipo de contenido. Usado por el scheduler."""
    import random
    candidatos = listar_copies(producto=producto, objetivo=objetivo)
    if not candidatos:
        candidatos = listar_copies(producto="general")
    if not candidatos:
        return None
    return random.choice(candidatos)


def eliminar_copy(copy_id: str) -> bool:
    data = _cargar()
    orig = len(data["copies"])
    data["copies"] = [c for c in data["copies"] if c["id"] != copy_id]
    _guardar(data)
    return len(data["copies"]) < orig


def toggle_copy(copy_id: str, activo: bool) -> bool:
    data = _cargar()
    for c in data["copies"]:
        if c["id"] == copy_id:
            c["activo"] = activo
            _guardar(data)
            return True
    return False


async def get_asset_of_week() -> dict:
    """
    Retorna el asset de la semana para el material lunes de aliados.
    Elige la imagen más reciente activa del catálogo; si no hay ninguna,
    retorna un dict vacío para que Franco genere el texto de igual manera.
    """
    import random
    imagenes = listar_imagenes(solo_activas=True)
    if not imagenes:
        return {}
    # Preferir imágenes de piscinas o módulos para el material semanal
    destacadas = [i for i in imagenes if any(
        t in i.get("etiquetas", []) for t in ("piscinas", "modulos", "combo")
    )]
    pool = destacadas or imagenes
    elegida = random.choice(pool[:10])  # entre los 10 más recientes
    return {
        "id": elegida.get("id"),
        "nombre": elegida.get("nombre"),
        "descripcion": elegida.get("descripcion"),
        "etiquetas": elegida.get("etiquetas", []),
    }
