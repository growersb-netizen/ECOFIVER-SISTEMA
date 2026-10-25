"""
Pre-flight check para migración 0037 — SOLO LECTURA.
Detecta wa_message_id duplicados en inbox_mensajes ANTES de crear el índice UNIQUE.

Ejecutar en eco-crm:
  railway run python scripts/preflight_0037.py

No modifica nada. Informa el estado actual.
"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import text
from database.database import SessionLocal

db = SessionLocal()
try:
    # 1. Total de mensajes con wa_message_id
    total = db.execute(text(
        "SELECT COUNT(*) FROM inbox_mensajes WHERE wa_message_id IS NOT NULL"
    )).scalar()
    null_count = db.execute(text(
        "SELECT COUNT(*) FROM inbox_mensajes WHERE wa_message_id IS NULL"
    )).scalar()

    print(f"\n{'='*60}")
    print("PRE-FLIGHT: migración 0037 — inbox_mensajes.wa_message_id")
    print(f"{'='*60}")
    print(f"  Total mensajes con wa_message_id   : {total}")
    print(f"  Total mensajes sin wa_message_id   : {null_count}")

    # 2. Buscar duplicados
    dups = db.execute(text("""
        SELECT wa_message_id, COUNT(*) AS cnt
        FROM inbox_mensajes
        WHERE wa_message_id IS NOT NULL
        GROUP BY wa_message_id
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)).fetchall()

    if not dups:
        print("\n  RESULTADO: Sin duplicados. La migración puede ejecutarse.")
    else:
        print(f"\n  RESULTADO: {len(dups)} wa_message_id duplicado(s) — NO ejecutar la migración todavía.\n")
        for row in dups:
            print(f"    wamid={row[0]}  aparece={row[1]} veces")
        print("\n  Acción requerida: resolver duplicados con autorización antes de migrar.")

    # 3. ¿Existe el índice ya?
    idx_exists = db.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'inbox_mensajes'
          AND indexname = 'uix_inbox_wa_message_id'
    """)).fetchone()

    if idx_exists:
        print("\n  INFO: El índice uix_inbox_wa_message_id YA EXISTE en la base de datos.")
    else:
        print("\n  INFO: El índice uix_inbox_wa_message_id NO existe todavía.")

    # 4. Muestra los 5 wamids más recientes para confirmar formato
    recientes = db.execute(text("""
        SELECT wa_message_id, direccion, wa_linea, created_at
        FROM inbox_mensajes
        WHERE wa_message_id IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 5
    """)).fetchall()

    print(f"\n  Últimos 5 wa_message_id registrados:")
    for r in recientes:
        print(f"    {r[0]}  dir={r[1]}  linea={r[2]}  at={r[3]}")

    print(f"\n{'='*60}\n")

finally:
    db.close()
