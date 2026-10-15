"""Agrega aliado_codigo a videollamadas para vincular VLs de socios aliados

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "videollamadas",
        sa.Column("aliado_codigo", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_videollamadas_aliado_codigo",
        "videollamadas",
        ["aliado_codigo"],
    )


def downgrade() -> None:
    op.drop_index("ix_videollamadas_aliado_codigo", table_name="videollamadas")
    op.drop_column("videollamadas", "aliado_codigo")
