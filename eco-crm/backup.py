"""
backup.py — Backup automático del SQLite del CRM.

Uso manual:    python backup.py
Uso scheduler: importado desde main.py via APScheduler (cron 03:00 ART)

Estrategia:
  - Copia /app/data/eco_crm.db → /app/data/backups/eco_crm_YYYYMMDD_HHMMSS.db
  - Mantiene solo los últimos 7 backups (borra los más viejos)
  - Registra cada operación en consola con timestamp
"""

import os
import shutil
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH     = Path(os.getenv("DB_PATH",     "/app/data/eco_crm.db"))
BACKUP_DIR  = Path(os.getenv("BACKUP_DIR",  "/app/data/backups"))
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS",  "7"))


def run_backup() -> bool:
    """
    Ejecuta el backup del SQLite.
    Retorna True si tuvo éxito, False si hubo algún error.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"eco_crm_{ts}.db"

    # ── 1. Verificar que la base existe ─────────────────────────────────────
    if not DB_PATH.exists():
        logger.warning(f"[BACKUP] ⚠  Base de datos no encontrada en {DB_PATH}. Saltando backup.")
        return False

    # ── 2. Crear directorio de backups si no existe ──────────────────────────
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── 3. Copiar ────────────────────────────────────────────────────────────
    try:
        shutil.copy2(str(DB_PATH), str(dest))
        size_kb = dest.stat().st_size // 1024
        logger.info(f"[BACKUP] ✓  {dest.name}  ({size_kb} KB)  —  {datetime.now().isoformat()}")
        print(f"[BACKUP] ✓  {dest.name}  ({size_kb} KB)  —  {datetime.now().isoformat()}")
    except Exception as e:
        logger.error(f"[BACKUP] ✗  Error al copiar la base: {e}")
        print(f"[BACKUP] ✗  Error al copiar la base: {e}")
        return False

    # ── 4. Rotar: mantener solo los últimos MAX_BACKUPS ──────────────────────
    try:
        backups = sorted(BACKUP_DIR.glob("eco_crm_*.db"), key=lambda p: p.stat().st_mtime)
        to_delete = backups[:-MAX_BACKUPS] if len(backups) > MAX_BACKUPS else []
        for old in to_delete:
            old.unlink()
            logger.info(f"[BACKUP] 🗑  Backup antiguo eliminado: {old.name}")
            print(f"[BACKUP] 🗑  Backup antiguo eliminado: {old.name}")
    except Exception as e:
        logger.warning(f"[BACKUP] ⚠  No se pudo rotar backups: {e}")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_backup()
