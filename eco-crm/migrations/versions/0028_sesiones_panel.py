"""Crea tabla sesiones_panel para tracking de tiempo activo de socios

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sesiones_panel",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("aliado_codigo", sa.String(20), nullable=False),
        sa.Column("login_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("logout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minutos_activos", sa.Integer(), server_default="0"),
        sa.Column("user_agent", sa.String(300), nullable=True),
    )
    op.create_index("ix_sesiones_panel_aliado_codigo", "sesiones_panel", ["aliado_codigo"])
    op.create_index("ix_sesiones_panel_login_at", "sesiones_panel", ["login_at"])


def downgrade() -> None:
    op.drop_table("sesiones_panel")
