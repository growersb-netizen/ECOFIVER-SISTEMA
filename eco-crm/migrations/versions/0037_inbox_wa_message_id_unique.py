"""inbox_mensajes: unique index parcial sobre wa_message_id (no nulo)

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import text
    bind = op.get_bind()

    # Pre-flight: detectar duplicados antes de intentar crear el índice.
    # Si hay duplicados, informar cuáles son para que se resuelvan con autorización
    # antes de ejecutar la migración (punto 5 y 6 del checklist de activación).
    dup_check = bind.execute(text("""
        SELECT wa_message_id, COUNT(*) AS cnt
        FROM inbox_mensajes
        WHERE wa_message_id IS NOT NULL
        GROUP BY wa_message_id
        HAVING COUNT(*) > 1
    """)).fetchall()

    if dup_check:
        lines = "\n".join(f"  wamid={r[0]}  count={r[1]}" for r in dup_check)
        raise RuntimeError(
            f"Existen {len(dup_check)} wa_message_id duplicados en inbox_mensajes.\n"
            f"{lines}\n\n"
            "Resolverlos manualmente (con autorización) antes de aplicar esta migración."
        )

    # Índice UNIQUE parcial: solo filas donde wa_message_id IS NOT NULL.
    # Permite múltiples NULL (mensajes manuales del CRM sin wamid).
    bind.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        uix_inbox_wa_message_id
        ON inbox_mensajes (wa_message_id)
        WHERE wa_message_id IS NOT NULL
    """))


def downgrade() -> None:
    from sqlalchemy import text
    bind = op.get_bind()
    bind.execute(text("DROP INDEX IF EXISTS uix_inbox_wa_message_id"))
