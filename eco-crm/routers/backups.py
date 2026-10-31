"""
Backups de la base (solo el propietario): listado, backup en el momento y descarga.

El archivo contiene todos los datos del CRM (clientes incluidos): por eso no alcanza
con ADMIN (los socios que entran por SSO también lo son); exige el rol PROPIETARIO.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

import backup
from database.models import Usuario
from routers.circuito_comercial import _propietario

router = APIRouter()
_NOMBRE = re.compile(r"^eco_crm_(pg_)?\d{8}_\d{6}\.(jsonl\.gz|db)$")


def _archivos():
    if not backup.BACKUP_DIR.exists():
        return []
    fs = [p for p in backup.BACKUP_DIR.iterdir() if _NOMBRE.match(p.name)]
    return sorted(fs, key=lambda p: p.stat().st_mtime, reverse=True)


@router.get("/api/propietario/backups")
def listar(_: Usuario = Depends(_propietario)):
    return {"backups": [{"nombre": p.name, "kb": p.stat().st_size // 1024,
                         "fecha": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
                        for p in _archivos()],
            "programado": "Todos los días a las 03:00 (Argentina); se conservan los últimos "
                          f"{backup.MAX_BACKUPS} y se suben a Cloudflare R2 si está configurado."}


@router.post("/api/propietario/backups")
def ahora(_: Usuario = Depends(_propietario)):
    if not backup.run_backup():
        raise HTTPException(500, "El backup falló: revisá los logs del CRM ([BACKUP-PG])")
    return {"ok": True, "ultimo": (_archivos() or [None])[0].name if _archivos() else None}


@router.get("/api/propietario/backups/{nombre}")
def descargar(nombre: str, _: Usuario = Depends(_propietario)):
    if not _NOMBRE.match(nombre):
        raise HTTPException(400, "Nombre inválido")
    p = backup.BACKUP_DIR / nombre
    if not p.is_file():
        raise HTTPException(404, "No existe")
    return FileResponse(p, filename=nombre, media_type="application/octet-stream")
