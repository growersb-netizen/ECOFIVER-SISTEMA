"""fix: resincronizar secuencia de comandos_agente

La tabla existía con datos (id hasta ~10) pero la secuencia SERIAL
quedó en un valor menor, causando UniqueViolation en cada INSERT.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-13
"""
from alembic import op
from sqlalchemy import text

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(text("""
        SELECT setval(
            pg_get_serial_sequence('comandos_agente', 'id'),
            COALESCE((SELECT MAX(id) FROM comandos_agente), 0) + 1,
            false
        )
    """))


def downgrade() -> None:
    pass
