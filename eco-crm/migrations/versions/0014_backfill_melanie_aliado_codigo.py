"""Backfill aliado_codigo = AL-010 para leads de línea Melanie (Claudia Ríos)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(text("""
        UPDATE leads
        SET aliado_codigo = 'AL-010'
        WHERE agente_asignado = 'melanie'
          AND (aliado_codigo IS NULL OR aliado_codigo = '')
    """))


def downgrade() -> None:
    pass
