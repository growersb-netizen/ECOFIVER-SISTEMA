"""Agrega vendedor_slug a usuarios para vincular cuentas CRM a líneas WA comerciales

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-25

Permite asociar una cuenta de usuario del CRM a una línea específica de WhatsApp
(MetaPagina.vendedor_slug). Los usuarios sin este campo ni rol ADMIN no acceden
a la bandeja de WhatsApp.
"""
from alembic import op
from sqlalchemy import text

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS vendedor_slug VARCHAR(50)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE usuarios DROP COLUMN IF EXISTS vendedor_slug"))
