"""add portafolio to meta_paginas

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect as _ins
    bind = op.get_bind()
    cols = [c["name"] for c in _ins(bind).get_columns("meta_paginas")]
    if "portafolio" not in cols:
        op.add_column(
            "meta_paginas",
            sa.Column("portafolio", sa.String(100), nullable=True, server_default="EcoFiver"),
        )


def downgrade() -> None:
    op.drop_column("meta_paginas", "portafolio")
