"""Agrega FK venta_contado_id y venta_financiada_id a leads (A2)

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-24

Columnas que vinculan el lead con la venta concretada (contado o financiada).
Nullable, sin restricción FK en la DB (la integridad se mantiene en la app).
"""
from alembic import op
from sqlalchemy import text

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS venta_contado_id INTEGER"
    ))
    bind.execute(text(
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS venta_financiada_id INTEGER"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS venta_contado_id"))
    bind.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS venta_financiada_id"))
