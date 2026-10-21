"""Agrega apellido, provincia, localidad a aliados

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("aliados", sa.Column("apellido",  sa.String(100), nullable=True, server_default=""))
    op.add_column("aliados", sa.Column("provincia", sa.String(100), nullable=True, server_default=""))
    op.add_column("aliados", sa.Column("localidad", sa.String(150), nullable=True, server_default=""))


def downgrade():
    op.drop_column("aliados", "localidad")
    op.drop_column("aliados", "provincia")
    op.drop_column("aliados", "apellido")
