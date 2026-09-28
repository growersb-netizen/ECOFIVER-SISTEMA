"""add en_produccion_desde to ventas_contado

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect as _ins
    bind = op.get_bind()
    cols = [c["name"] for c in _ins(bind).get_columns("ventas_contado")]
    if "en_produccion_desde" not in cols:
        op.add_column("ventas_contado", sa.Column("en_produccion_desde", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ventas_contado", "en_produccion_desde")
