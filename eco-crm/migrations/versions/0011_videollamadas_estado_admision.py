"""videollamadas: agregar estado_admision faltante en migración

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-13
"""
from alembic import op
from sqlalchemy import text

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE videollamadas ADD COLUMN IF NOT EXISTS estado_admision VARCHAR(20)"
    ))


def downgrade() -> None:
    pass
