"""
Restaura un backup lógico de PostgreSQL (eco_crm_pg_*.jsonl.gz) en una base VACÍA.

    python restaurar_backup_pg.py <archivo.jsonl.gz> <DATABASE_URL_DESTINO> [--crear-esquema]

Salvaguardas:
- Se niega a escribir si alguna tabla del destino ya tiene filas (nunca pisa producción).
- --crear-esquema crea las tablas desde los modelos del código antes de cargar. Usá el mismo
  código (commit) que generó el backup. La versión de Alembic se toma del backup.
- Carga todo en una transacción: si algo falla, el destino queda como estaba.
- Al final ajusta las secuencias de los id y compara los conteos con el backup.

Procedimiento recomendado ante un incidente: crear una base nueva en Railway, restaurar
ahí, verificar, y recién después apuntar el CRM a la base nueva (decisión humana).
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import decimal
import gzip
import json
import sys

from sqlalchemy import MetaData, create_engine, func, select, text


def _valor(v):
    if isinstance(v, dict) and len(v) == 1:
        (k, x), = v.items()
        if k == "$dt":
            return dt.datetime.fromisoformat(x)
        if k == "$d":
            return dt.date.fromisoformat(x)
        if k == "$t":
            return dt.time.fromisoformat(x)
        if k == "$dec":
            return decimal.Decimal(x)
        if k == "$b64":
            return base64.b64decode(x)
    return v


def leer(archivo: str):
    """Itera (tabla, columnas, filas) del backup."""
    with gzip.open(archivo, "rt", encoding="utf-8") as f:
        cab = json.loads(f.readline())
        if cab.get("$formato") != "ecofiver-pg-jsonl":
            raise SystemExit("El archivo no es un backup de EcoFiver (ecofiver-pg-jsonl)")
        tabla, cols, filas = None, None, []
        for linea in f:
            obj = json.loads(linea)
            if isinstance(obj, dict) and "$tabla" in obj:
                if tabla:
                    yield tabla, cols, filas
                tabla, cols, filas = obj["$tabla"], obj["columnas"], []
            else:
                filas.append([_valor(v) for v in obj])
        if tabla:
            yield tabla, cols, filas


def restaurar(archivo: str, url_destino: str, crear_esquema: bool = False) -> dict:
    url_destino = url_destino.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url_destino)
    if crear_esquema:
        # Esquema de los modelos del código (las migraciones históricas no corren desde una base vacía);
        # la versión de Alembic se restaura desde el backup.
        from database.database import Base
        import database.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
    meta = MetaData()
    meta.reflect(bind=engine)
    with engine.connect() as conn:
        con_datos = [t.name for t in meta.sorted_tables if t.name != "alembic_version"
                     and conn.execute(select(func.count()).select_from(t)).scalar()]
    if con_datos:
        raise SystemExit(f"El destino NO está vacío ({', '.join(con_datos[:5])}…): no se restaura encima de datos")
    esperados = {}
    with engine.begin() as conn:
        conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        conn.execute(text("DELETE FROM alembic_version")) if "alembic_version" in meta.tables else None
        datos = {t: (c, f) for t, c, f in leer(archivo)}
        orden = [t.name for t in meta.sorted_tables if t.name in datos] + \
                [t for t in datos if t not in meta.tables]
        for nombre in orden:
            if nombre not in meta.tables:
                raise SystemExit(f"La tabla '{nombre}' del backup no existe en el destino: "
                                 "creá el esquema con el mismo código que generó el backup")
            cols, filas = datos[nombre]
            tabla = meta.tables[nombre]
            for col in tabla.columns:                      # NULL de SQL sigue siendo NULL (no el JSON 'null')
                if hasattr(col.type, "none_as_null"):
                    col.type.none_as_null = True
            faltan = [c for c in cols if c not in tabla.columns]
            if faltan:
                raise SystemExit(f"{nombre}: columnas del backup inexistentes en el destino: {faltan}")
            esperados[nombre] = len(filas)
            for i in range(0, len(filas), 500):
                lote = [dict(zip(cols, f)) for f in filas[i:i + 500]]
                if lote:
                    conn.execute(tabla.insert(), lote)
        # secuencias de las PK enteras
        for tabla in meta.sorted_tables:
            for col in tabla.primary_key.columns:
                seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, :c)"),
                                   {"t": tabla.name, "c": col.name}).scalar()
                if seq:
                    conn.execute(text(f'SELECT setval(:s, COALESCE((SELECT MAX("{col.name}") FROM "{tabla.name}"), 0) + 1, false)'),
                                 {"s": seq})
    with engine.connect() as conn:
        reales = {n: conn.execute(select(func.count()).select_from(meta.tables[n])).scalar() for n in esperados}
    distintos = {n: (esperados[n], reales[n]) for n in esperados if esperados[n] != reales[n]}
    if distintos:
        raise SystemExit(f"Conteos distintos tras restaurar: {distintos}")
    return esperados


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo")
    ap.add_argument("database_url_destino")
    ap.add_argument("--crear-esquema", action="store_true")
    a = ap.parse_args()
    c = restaurar(a.archivo, a.database_url_destino, a.crear_esquema)
    print(f"Restaurado: {len(c)} tablas, {sum(c.values())} filas")
    sys.exit(0)
