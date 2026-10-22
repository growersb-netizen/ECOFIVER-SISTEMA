"""Fuerza zona='Buenos Aires' para AL-010 (Stefania Pardo)

La migración 0027 preservaba la zona existente si no era NULL/vacía.
AL-010 tenía zona='ramos mejia', por lo que quedó sin actualizar.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-22
"""
from alembic import op
from sqlalchemy import text

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(text("UPDATE aliados SET zona = 'Buenos Aires' WHERE codigo = 'AL-010'"))


def downgrade():
    bind = op.get_bind()
    bind.execute(text("UPDATE aliados SET zona = 'ramos mejia' WHERE codigo = 'AL-010'"))
