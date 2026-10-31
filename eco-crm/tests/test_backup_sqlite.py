"""Backup del SQLite: copia consistente (incluye el WAL) y verificada."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup


def _base_wal(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")      # lo confirmado queda en el -wal
    con.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, nombre TEXT)")
    con.executemany("INSERT INTO leads (nombre) VALUES (?)", [(f"lead {i}",) for i in range(500)])
    con.commit()
    return con                                       # conexión abierta: el WAL no se vuelca


def _contar(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT count(*) FROM leads").fetchone()[0]
    except sqlite3.DatabaseError:
        return None
    finally:
        con.close()


def test_backup_incluye_lo_confirmado_en_el_wal(tmp_path, monkeypatch):
    db = tmp_path / "eco_crm.db"
    viva = _base_wal(str(db))
    monkeypatch.setattr(backup, "DB_PATH", db)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup, "_upload_r2", lambda p: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert backup.run_backup()
    (copia,) = (tmp_path / "backups").glob("eco_crm_*.db")
    assert _contar(copia) == 500
    viva.close()


def test_copia_de_archivo_pierde_el_wal(tmp_path):
    """Documenta el problema anterior: copiar el .db no incluye el WAL."""
    import shutil
    db = tmp_path / "eco_crm.db"
    viva = _base_wal(str(db))
    shutil.copy2(db, tmp_path / "copia.db")
    assert _contar(tmp_path / "copia.db") != 500
    viva.close()


def test_con_postgres_respalda_la_base_productiva_y_el_sqlite_heredado(tmp_path, monkeypatch):
    db = tmp_path / "eco_crm.db"
    _base_wal(str(db)).close()
    monkeypatch.setattr(backup, "DB_PATH", db)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup, "_upload_r2", lambda p: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/db")
    llamadas = []
    monkeypatch.setattr(backup, "run_backup_pg", lambda: llamadas.append("pg") or True)
    assert backup.run_backup() is True and llamadas == ["pg"]
    assert list((tmp_path / "backups").glob("eco_crm_2*.db"))                 # el SQLite heredado también
