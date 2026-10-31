"""
backup.py — Backup automático del CRM: PostgreSQL (producción) y SQLite heredado.

Uso manual:    python backup.py
Uso scheduler: importado desde main.py via APScheduler (cron 03:00 ART)

Estrategia:
  - Copia /app/data/eco_crm.db → /app/data/backups/eco_crm_YYYYMMDD_HHMMSS.db
  - Sube el backup al bucket de Cloudflare R2 (backups/crm/) para redundancia externa
  - Mantiene solo los últimos 7 backups locales (borra los más viejos)
  - Registra cada operación en consola con timestamp
"""

import os
import shutil
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH     = Path(os.getenv("DB_PATH",     "/app/data/eco_crm.db"))
BACKUP_DIR  = Path(os.getenv("BACKUP_DIR",  "/app/data/backups"))
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS",  "7"))


def _upload_r2(local_path: Path) -> None:
    """Sube el backup a Cloudflare R2. Falla silenciosamente para no bloquear el backup local."""
    try:
        import boto3
        account_id = os.getenv("R2_ACCOUNT_ID", "")
        bucket     = os.getenv("R2_BUCKET_NAME", "")
        key_id     = os.getenv("R2_ACCESS_KEY_ID", "")
        key_secret = os.getenv("R2_SECRET_ACCESS_KEY", "")
        if not all([account_id, bucket, key_id, key_secret]):
            logger.warning("[BACKUP-R2] Credenciales R2 no configuradas — omitiendo subida remota")
            print("[BACKUP-R2] Credenciales R2 no configuradas — omitiendo subida remota")
            return
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=key_id,
            aws_secret_access_key=key_secret,
            region_name="auto",
        )
        object_key = f"backups/crm/{local_path.name}"
        s3.upload_file(str(local_path), bucket, object_key)
        logger.info(f"[BACKUP-R2] ☁  Subido a R2: {object_key}")
        print(f"[BACKUP-R2] ☁  Subido a R2: {object_key}")
    except Exception as e:
        logger.warning(f"[BACKUP-R2] ⚠  No se pudo subir a R2: {e}")
        print(f"[BACKUP-R2] ⚠  No se pudo subir a R2: {e}")


# ── PostgreSQL (producción) ──────────────────────────────────────────────────
# Volcado lógico de todas las tablas a un .jsonl.gz: no depende de la versión de
# pg_dump ni del servidor, se sube a R2 como el resto y se restaura con
# restaurar_backup_pg.py sobre una base vacía (nunca sobre producción).

def _valor_json(v):
    import base64
    import datetime as _dt
    import decimal
    import uuid
    if isinstance(v, _dt.datetime):
        return {"$dt": v.isoformat()}
    if isinstance(v, _dt.date):
        return {"$d": v.isoformat()}
    if isinstance(v, _dt.time):
        return {"$t": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"$dec": str(v)}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"$b64": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def volcar_postgres(database_url: str, destino: Path) -> dict:
    """Vuelca todas las tablas (incluida alembic_version) a destino (.jsonl.gz). Devuelve conteos."""
    import gzip
    import json
    from sqlalchemy import MetaData, create_engine, select
    engine = create_engine(database_url.replace("postgres://", "postgresql://", 1))
    meta = MetaData()
    meta.reflect(bind=engine)
    conteos = {}
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    with engine.connect() as conn, gzip.open(tmp, "wt", encoding="utf-8") as f:
        conn = conn.execution_options(stream_results=True, isolation_level="REPEATABLE READ")
        with conn.begin():                                   # una sola foto consistente de toda la base
            f.write(json.dumps({"$formato": "ecofiver-pg-jsonl", "version": 1,
                                "creado": datetime.now().isoformat()}) + "\n")
            for tabla in meta.sorted_tables:
                cols = [c.name for c in tabla.columns]
                f.write(json.dumps({"$tabla": tabla.name, "columnas": cols}) + "\n")
                n = 0
                for fila in conn.execute(select(tabla)):
                    f.write(json.dumps([_valor_json(v) for v in fila], ensure_ascii=False, default=str) + "\n")
                    n += 1
                conteos[tabla.name] = n
    tmp.rename(destino)
    engine.dispose()
    return conteos


def run_backup_pg() -> bool:
    database_url = os.getenv("DATABASE_URL", "")
    if "postgres" not in database_url:
        return False
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"eco_crm_pg_{ts}.jsonl.gz"
    try:
        conteos = volcar_postgres(database_url, dest)
        size_kb = dest.stat().st_size // 1024
        logger.info(f"[BACKUP-PG] ✓  {dest.name} ({size_kb} KB) · {len(conteos)} tablas · "
                    f"{sum(conteos.values())} filas")
    except Exception as e:
        logger.error(f"[BACKUP-PG] ✗  Error al volcar PostgreSQL: {e}")
        return False
    _upload_r2(dest)
    try:
        viejos = sorted(BACKUP_DIR.glob("eco_crm_pg_*.jsonl.gz"), key=lambda p: p.stat().st_mtime)
        for old in (viejos[:-MAX_BACKUPS] if len(viejos) > MAX_BACKUPS else []):
            old.unlink()
    except Exception as e:
        logger.warning(f"[BACKUP-PG] ⚠  No se pudo rotar backups: {e}")
    return True


def run_backup() -> bool:
    """
    Backup diario: PostgreSQL (producción) y, si existe, el SQLite heredado.
    Retorna True si el backup de la base en uso tuvo éxito.
    """
    if "postgres" in os.getenv("DATABASE_URL", ""):
        ok_pg = run_backup_pg()
        if DB_PATH.exists():
            _run_backup_sqlite()
        return ok_pg
    return _run_backup_sqlite()


def _run_backup_sqlite() -> bool:
    """Copia consistente del SQLite (base local o heredada)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"eco_crm_{ts}.db"

    # ── 1. Verificar que la base existe ─────────────────────────────────────
    if not DB_PATH.exists():
        logger.warning(f"[BACKUP] ⚠  Base de datos no encontrada en {DB_PATH}. Saltando backup.")
        return False

    # ── 2. Crear directorio de backups si no existe ──────────────────────────
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── 3. Copiar ────────────────────────────────────────────────────────────
    # API de backup de SQLite: copia consistente aunque haya escrituras en curso
    # e incluye lo confirmado en el WAL (shutil.copy2 del .db no lo incluía).
    try:
        src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            dst.close()
            src.close()
        if ok != "ok":
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"integrity_check del backup: {ok}")
        size_kb = dest.stat().st_size // 1024
        logger.info(f"[BACKUP] ✓  {dest.name}  ({size_kb} KB)  —  {datetime.now().isoformat()}")
        print(f"[BACKUP] ✓  {dest.name}  ({size_kb} KB)  —  {datetime.now().isoformat()}")
    except Exception as e:
        logger.error(f"[BACKUP] ✗  Error al copiar la base: {e}")
        print(f"[BACKUP] ✗  Error al copiar la base: {e}")
        return False

    # ── 3b. Subir a Cloudflare R2 (backup externo — falla silenciosamente) ───
    _upload_r2(dest)

    # ── 4. Rotar: mantener solo los últimos MAX_BACKUPS ──────────────────────
    try:
        backups = sorted(BACKUP_DIR.glob("eco_crm_2*.db"), key=lambda p: p.stat().st_mtime)
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
