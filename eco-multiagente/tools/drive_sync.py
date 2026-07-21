"""
Sincronización Google Drive → Galería de Activos.

El usuario organiza sus imágenes en una carpeta de Drive con esta estructura:

  📁 Eco Módulos y Piscinas (root, DRIVE_GALLERY_FOLDER_ID)
    📁 modulos/
    📁 piscinas/
    📁 combo/
    📁 contado/
    📁 financiado/
    📁 familia/
    📁 obra/
    📁 general/

El sistema hace sync periódico (o manual desde el panel) y descarga
las imágenes nuevas a la galería, etiquetándolas con la carpeta de origen.
Las imágenes ya sincronizadas (por nombre + tamaño) se saltan.

Credenciales: service account JSON en env var GOOGLE_SERVICE_ACCOUNT_JSON
(el JSON completo como string, o la ruta al archivo .json).
"""

import os
import json
import base64
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"

# Carpeta raíz de la galería en Drive
DRIVE_GALLERY_FOLDER_ID = os.getenv(
    "DRIVE_GALLERY_FOLDER_ID",
    os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""),   # fallback al existente
)

# Carpetas reconocidas → etiquetas de galería
CARPETAS_ETIQUETAS: dict[str, list[str]] = {
    "modulos":     ["modulos"],
    "módulos":     ["modulos"],
    "piscinas":    ["piscinas"],
    "combo":       ["combo"],
    "contado":     ["contado"],
    "financiado":  ["financiado"],
    "familia":     ["familia"],
    "obra":        ["obra"],
    "instalacion": ["instalacion"],
    "instalación": ["instalacion"],
    "exterior":    ["exterior"],
    "interior":    ["interior"],
    "verano":      ["verano"],
    "invierno":    ["invierno"],
    "historia":    ["historia"],
    "general":     ["general"],
}

MIME_VALIDOS = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/gif", "image/heic",
}


# ── Autenticación con Service Account ────────────────────────────────────────

def _get_access_token() -> str:
    """
    Obtiene un access token de Google usando la service account.
    Soporta:
      - GOOGLE_SERVICE_ACCOUNT_JSON con el JSON completo como string
      - GOOGLE_SERVICE_ACCOUNT_FILE con la ruta a un archivo .json
    """
    sa_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sa_file     = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")

    if sa_json_str:
        sa_info = json.loads(sa_json_str)
    elif sa_file and os.path.exists(sa_file):
        with open(sa_file) as f:
            sa_info = json.load(f)
    else:
        raise RuntimeError(
            "Sin credenciales de Google Drive. "
            "Configurá GOOGLE_SERVICE_ACCOUNT_JSON o GOOGLE_SERVICE_ACCOUNT_FILE."
        )

    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GRequest

    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    creds.refresh(GRequest())
    return creds.token


# ── Helpers de Drive API ──────────────────────────────────────────────────────

async def _listar_archivos(folder_id: str, token: str) -> list[dict]:
    """Lista archivos de imagen directamente dentro de una carpeta de Drive."""
    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType,size,modifiedTime)",
        "pageSize": 200,
    }
    headers = {"Authorization": f"Bearer {token}"}
    archivos = []
    page_token = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            if page_token:
                params["pageToken"] = page_token
            r = await client.get(f"{DRIVE_API}/files", params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            archivos.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    return archivos


async def _listar_subcarpetas(folder_id: str, token: str) -> list[dict]:
    """Lista subcarpetas dentro de una carpeta de Drive."""
    params = {
        "q": f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        "fields": "files(id,name)",
        "pageSize": 50,
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{DRIVE_API}/files", params=params, headers=headers)
        r.raise_for_status()
        return r.json().get("files", [])


async def _descargar_archivo(file_id: str, token: str) -> bytes:
    """Descarga el contenido binario de un archivo de Drive."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.get(
            f"{DRIVE_API}/files/{file_id}",
            params={"alt": "media"},
            headers=headers,
        )
        r.raise_for_status()
        return r.content


# ── Sync principal ────────────────────────────────────────────────────────────

async def sincronizar_drive(folder_id: str | None = None) -> dict:
    """
    Recorre la carpeta de Drive (raíz + subcarpetas) y descarga las imágenes
    nuevas a la galería de activos local.

    Retorna {
      "nuevas": int,
      "saltadas": int,
      "errores": int,
      "detalle": [str]
    }
    """
    folder_id = folder_id or DRIVE_GALLERY_FOLDER_ID
    if not folder_id:
        raise RuntimeError("DRIVE_GALLERY_FOLDER_ID no configurado")

    from tools.asset_library import guardar_imagen, listar_imagenes

    # Nombres ya existentes en galería (para dedup por nombre)
    existentes = {img["nombre"] for img in listar_imagenes(solo_activas=False)}

    nuevas = saltadas = errores = 0
    detalle: list[str] = []

    try:
        token = _get_access_token()
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "nuevas": 0, "saltadas": 0, "errores": 0, "detalle": []}

    async def _procesar_carpeta(fid: str, etiquetas: list[str]):
        nonlocal nuevas, saltadas, errores
        try:
            archivos = await _listar_archivos(fid, token)
        except Exception as e:
            logger.warning(f"[DriveSync] Error listando carpeta {fid}: {e}")
            return

        for f in archivos:
            mime = f.get("mimeType", "")
            # Aceptar HEIC como imagen aunque el mime no sea standard
            if mime not in MIME_VALIDOS and "image" not in mime:
                continue
            nombre = f["name"]
            if nombre in existentes:
                saltadas += 1
                continue
            try:
                img_bytes = await _descargar_archivo(f["id"], token)
                b64 = base64.b64encode(img_bytes).decode()
                # Normalizar mime
                mime_out = "image/jpeg" if mime in ("image/jpg", "image/heic") else mime
                guardar_imagen(b64, nombre, etiquetas, descripcion="Sync Drive", mime=mime_out)
                existentes.add(nombre)
                nuevas += 1
                detalle.append(f"+ {nombre} [{', '.join(etiquetas)}]")
                logger.info(f"[DriveSync] Importada: {nombre}")
            except Exception as e:
                errores += 1
                detalle.append(f"! {nombre}: {e}")
                logger.warning(f"[DriveSync] Error descargando {nombre}: {e}")

    # Procesar raíz (etiqueta "general")
    await _procesar_carpeta(folder_id, ["general"])

    # Procesar subcarpetas conocidas
    try:
        subcarpetas = await _listar_subcarpetas(folder_id, token)
    except Exception as e:
        logger.warning(f"[DriveSync] Error listando subcarpetas: {e}")
        subcarpetas = []

    for sub in subcarpetas:
        nombre_sub = sub["name"].lower().strip()
        etiquetas_sub = CARPETAS_ETIQUETAS.get(nombre_sub, ["general"])
        await _procesar_carpeta(sub["id"], etiquetas_sub)

    return {
        "ok": True,
        "nuevas": nuevas,
        "saltadas": saltadas,
        "errores": errores,
        "detalle": detalle,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


async def verificar_conexion_drive() -> dict:
    """
    Verifica que las credenciales funcionen y que la carpeta configurada sea accesible.
    Retorna info de la carpeta o el error.
    """
    folder_id = DRIVE_GALLERY_FOLDER_ID
    if not folder_id:
        return {"ok": False, "error": "DRIVE_GALLERY_FOLDER_ID no configurado"}
    try:
        token = _get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{DRIVE_API}/files/{folder_id}",
                params={"fields": "id,name,mimeType"},
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
        return {
            "ok": True,
            "folder_id": folder_id,
            "folder_name": data.get("name", "?"),
        }
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No se pudo acceder a Drive: {e}"}
