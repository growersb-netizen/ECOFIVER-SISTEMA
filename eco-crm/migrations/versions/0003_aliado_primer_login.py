"""add primer_login to aliados

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect as _ins
    bind = op.get_bind()
    cols = [c["name"] for c in _ins(bind).get_columns("aliados")]
    if "primer_login" not in cols:
        op.add_column("aliados", sa.Column("primer_login", sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("aliados", "primer_login")
