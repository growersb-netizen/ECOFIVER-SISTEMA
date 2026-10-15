"""Agrega campos de admisión/producto a videollamadas: modelo, color, cuotas, DNI, devolución

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videollamadas", sa.Column("modelo_especifico", sa.String(150), nullable=True))
    op.add_column("videollamadas", sa.Column("color", sa.String(50), nullable=True))
    op.add_column("videollamadas", sa.Column("cantidad_cuotas", sa.Integer, nullable=True))
    op.add_column("videollamadas", sa.Column("dni_cliente", sa.String(20), nullable=True))
    op.add_column("videollamadas", sa.Column("devolucion", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("videollamadas", "devolucion")
    op.drop_column("videollamadas", "dni_cliente")
    op.drop_column("videollamadas", "cantidad_cuotas")
    op.drop_column("videollamadas", "color")
    op.drop_column("videollamadas", "modelo_especifico")
