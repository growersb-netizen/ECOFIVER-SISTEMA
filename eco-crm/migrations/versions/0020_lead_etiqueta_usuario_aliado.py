"""Agrega etiqueta_color a leads y aliado_codigo a usuarios

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("etiqueta_color", sa.String(20), nullable=True))
    op.add_column("usuarios", sa.Column("aliado_codigo", sa.String(20), nullable=True))
    try:
        op.create_index("ix_usuarios_aliado_codigo", "usuarios", ["aliado_codigo"])
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index("ix_usuarios_aliado_codigo", table_name="usuarios")
    except Exception:
        pass
    op.drop_column("usuarios", "aliado_codigo")
    op.drop_column("leads", "etiqueta_color")
