"""Agrega campos de organización y template WA a aliados

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("aliados")}

    if "es_organizador" not in cols:
        op.add_column("aliados", sa.Column("es_organizador", sa.Boolean(), nullable=True, server_default="false"))

    if "organizacion_codigo" not in cols:
        op.add_column("aliados", sa.Column("organizacion_codigo", sa.String(20), nullable=True))
        op.create_index("ix_aliados_organizacion_codigo", "aliados", ["organizacion_codigo"])

    if "wa_template_presentacion" not in cols:
        op.add_column("aliados", sa.Column("wa_template_presentacion", sa.Text(), nullable=True))


def downgrade() -> None:
    pass
