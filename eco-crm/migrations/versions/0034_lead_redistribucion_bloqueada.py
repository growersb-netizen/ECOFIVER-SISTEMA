"""Agrega redistribucion_bloqueada a leads y protege los 1117 leads de AL-010

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-25

Columna booleana que marca leads excluidos del módulo reasignar-masivo.
Se inicializa en TRUE para todos los leads actualmente de AL-010 (1117 leads),
protegiendo su cartera existente. Los leads que se asignen a AL-010 en el
futuro tendrán redistribucion_bloqueada=FALSE y sí podrán redistribuirse.
"""
from alembic import op
from sqlalchemy import text

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS redistribucion_bloqueada BOOLEAN DEFAULT FALSE"
    ))
    bind.execute(text(
        "UPDATE leads SET redistribucion_bloqueada = TRUE WHERE aliado_codigo = 'AL-010'"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS redistribucion_bloqueada"))
