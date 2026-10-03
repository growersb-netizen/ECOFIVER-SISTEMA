"""
migrate_sqlite_to_pg.py — Copia datos de SQLite → PostgreSQL con validación de conteos.

Prerequisitos:
  - DATABASE_URL apuntando a PostgreSQL (env var o .env)
  - El esquema de PostgreSQL ya creado (alembic upgrade head corrido previamente)
  - El archivo SQLite en la ruta indicada por SQLITE_PATH (default: data/eco_crm.db)

Uso:
  python migrate_sqlite_to_pg.py [--sqlite-path <ruta>] [--dry-run]

CRITICAL: No modifica ni elimina el archivo .db original bajo ninguna circunstancia.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("migrate")

# Tablas de Construsol: NUNCA se tocan — lógica aislada e intocable
CONSTRUSOL_TABLES = {
    "clientes_cobranza_historica",
    "pagos_cobranza_historica",
    "historial_edicion_cobranza",
}


def _make_engines(sqlite_path: str):
    pg_url = os.getenv("DATABASE_URL", "")
    if not pg_url or "postgresql" not in pg_url and "postgres" not in pg_url:
        log.error("DATABASE_URL no apunta a PostgreSQL. Abortando.")
        sys.exit(1)

    sqlite_url = f"sqlite:///{sqlite_path}"
    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dst_engine = create_engine(
        pg_url,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 10},
    )
    return src_engine, dst_engine


def _get_ordered_tables(src_engine):
    inspector = inspect(src_engine)
    return inspector.get_table_names()


def _topological_sort(tables: list[str], dst_engine) -> list[str]:
    """Ordena tablas según dependencias FK en PostgreSQL para evitar violaciones."""
    q = text("""
        SELECT tc.table_name, ccu.table_name AS depends_on
        FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON rc.unique_constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
    """)
    with dst_engine.connect() as conn:
        deps = conn.execute(q).fetchall()

    table_set = set(tables)
    graph: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in deps:
        if child in table_set and parent in table_set and child != parent:
            graph[child].add(parent)

    # Kahn's algorithm
    in_degree = {t: len(graph[t]) for t in tables}
    queue = [t for t in tables if in_degree[t] == 0]
    result = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for t in tables:
            if node in graph[t]:
                in_degree[t] -= 1
                if in_degree[t] == 0:
                    queue.append(t)
    # Any remaining (cycles or missing) append at end
    result.extend(t for t in tables if t not in result)
    return result


def _count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0


def _get_bool_cols(dst_engine, table: str) -> set[str]:
    """Retorna columnas de tipo boolean en PostgreSQL para la tabla dada."""
    q = text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = :t AND data_type = 'boolean'
    """)
    with dst_engine.connect() as conn:
        rows = conn.execute(q, {"t": table}).fetchall()
    return {r[0] for r in rows}


def _copy_table(src_engine, dst_engine, table: str, dry_run: bool) -> tuple[int, int]:
    with src_engine.connect() as src:
        rows = src.execute(text(f'SELECT * FROM "{table}"')).fetchall()
        if not rows:
            return 0, 0
        keys = src.execute(text(f'SELECT * FROM "{table}" LIMIT 0')).keys()
        cols = list(keys)

    src_count = len(rows)

    if dry_run:
        log.info(f"  [dry-run] {table}: {src_count} filas (no se copian)")
        return src_count, 0

    bool_cols = _get_bool_cols(dst_engine, table)

    def cast_row(row):
        d = dict(zip(cols, row))
        for c in bool_cols:
            if c in d and d[c] is not None:
                d[c] = bool(d[c])
        return d

    with dst_engine.begin() as dst:
        col_list = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        stmt = text(
            f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
            f"ON CONFLICT DO NOTHING"
        )
        dst.execute(stmt, [cast_row(row) for row in rows])

    dst_count = _count(dst_engine, table)
    return src_count, dst_count


def migrate(sqlite_path: str, dry_run: bool = False):
    if not Path(sqlite_path).exists():
        log.error(f"SQLite no encontrado: {sqlite_path}")
        sys.exit(1)

    log.info(f"Fuente SQLite : {sqlite_path}")
    log.info(f"Destino PG    : {os.getenv('DATABASE_URL', '')[:40]}...")
    log.info(f"Modo          : {'DRY RUN' if dry_run else 'REAL'}")
    log.info("─" * 60)

    src_engine, dst_engine = _make_engines(sqlite_path)
    tables = _get_ordered_tables(src_engine)

    # Validate PG schema has the same tables
    pg_inspector = inspect(dst_engine)
    pg_tables = set(pg_inspector.get_table_names())

    # Sort tables by FK dependency order to avoid FK violations
    tables_in_pg = [t for t in tables if t in pg_tables]
    tables_sorted = _topological_sort(tables_in_pg, dst_engine)
    # Put skipped tables at end
    tables_skipped = [t for t in tables if t not in pg_tables]
    tables = tables_sorted + tables_skipped

    results = []
    errors = []

    for table in tables:
        if table in CONSTRUSOL_TABLES:
            # Construsol se incluye en la migración pero se marca como protegida
            log.info(f"  {table}: [CONSTRUSOL — se migra pero no se altera lógica]")

        if table not in pg_tables:
            log.warning(f"  {table}: tabla no existe en PG — saltando")
            errors.append(f"Tabla ausente en PG: {table}")
            continue

        try:
            src_n, dst_n = _copy_table(src_engine, dst_engine, table, dry_run)
            ok = dry_run or dst_n >= src_n
            status = "✓" if ok else "✗ MISMATCH"
            log.info(f"  {table}: {src_n} SQLite → {dst_n} PG  {status}")
            results.append((table, src_n, dst_n, ok))
            if not ok:
                errors.append(f"Conteo no coincide: {table} ({src_n} vs {dst_n})")
        except Exception as exc:
            log.error(f"  {table}: ERROR — {exc}")
            errors.append(f"Error en {table}: {exc}")

    log.info("─" * 60)
    total_src = sum(r[1] for r in results)
    total_dst = sum(r[2] for r in results)
    log.info(f"Total filas SQLite : {total_src}")
    log.info(f"Total filas PG     : {total_dst}")

    if errors:
        log.error(f"\n{len(errors)} problemas encontrados:")
        for e in errors:
            log.error(f"  • {e}")
        log.error("\n⚠️  NO elimines el archivo .db hasta resolver todos los errores.")
        sys.exit(1)
    else:
        log.info("\n✅ Migración completada sin errores.")
        log.info("⚠️  Conserva el archivo .db como backup hasta confirmar PG en producción.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migración SQLite → PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("SQLITE_PATH", "data/eco_crm.db"),
        help="Ruta al archivo SQLite (default: data/eco_crm.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo cuenta filas, no copia datos",
    )
    args = parser.parse_args()
    migrate(args.sqlite_path, args.dry_run)
