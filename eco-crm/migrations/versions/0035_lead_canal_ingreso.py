"""Agrega canal_ingreso a leads para diferenciar origen directo vs CRM

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-25

Valores: 'directo' (entró por WA personal del aliado/asesor) | 'crm' (asignado por admin).
Los leads existentes quedan con NULL (origen desconocido/legado).
"""
from alembic import op
from sqlalchemy import text

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS canal_ingreso VARCHAR(20)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS canal_ingreso"))
