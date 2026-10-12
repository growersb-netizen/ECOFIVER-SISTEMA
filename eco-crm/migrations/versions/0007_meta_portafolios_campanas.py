"""add meta_portafolios y meta_campana_snapshots

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect as _ins
    bind = op.get_bind()
    tables = _ins(bind).get_table_names()

    # ── meta_portafolios ──────────────────────────────────────────────────────
    if "meta_portafolios" not in tables:
        op.create_table(
            "meta_portafolios",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("nombre", sa.String(150), unique=True, nullable=False),
            sa.Column("slug", sa.String(80), unique=True, nullable=False),
            sa.Column("ad_account_id", sa.String(50), nullable=True),
            sa.Column("system_token_enc", sa.Text(), nullable=True),
            sa.Column("activo", sa.Boolean(), server_default="true"),
            sa.Column("color", sa.String(20), server_default="#4f46e5"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        # Seed: portafolio por defecto "EcoFiver" y el portafolio con la cuenta publicitaria
        op.execute("""
            INSERT INTO meta_portafolios (nombre, slug, ad_account_id, activo, color)
            VALUES
              ('EcoModulos y Piscinas', 'ecomodulos', NULL, true, '#4f46e5'),
              ('Portafolio Publicitario', 'publicitario', 'act_2483423728803274', true, '#0891b2')
            ON CONFLICT (slug) DO NOTHING
        """)

    # ── meta_campana_snapshots ────────────────────────────────────────────────
    if "meta_campana_snapshots" not in tables:
        op.create_table(
            "meta_campana_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("portafolio_slug", sa.String(80), nullable=False, index=True),
            sa.Column("campaign_id", sa.String(50), nullable=False, index=True),
            sa.Column("campaign_name", sa.String(300), nullable=False),
            sa.Column("adset_name", sa.String(300), nullable=True),
            sa.Column("page_id", sa.String(50), nullable=True),
            sa.Column("status", sa.String(30), server_default="ACTIVE"),
            sa.Column("fecha", sa.Date(), nullable=False, index=True),
            sa.Column("spend", sa.Float(), server_default="0"),
            sa.Column("impressions", sa.Integer(), server_default="0"),
            sa.Column("clicks", sa.Integer(), server_default="0"),
            sa.Column("leads", sa.Integer(), server_default="0"),
            sa.Column("cpl", sa.Float(), nullable=True),
            sa.Column("daily_budget", sa.Float(), nullable=True),
            sa.Column("lifetime_budget", sa.Float(), nullable=True),
            sa.Column("raw_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_campana_snap_fecha_camp", "meta_campana_snapshots",
                        ["fecha", "campaign_id"])

    # ── leads: agregar columna meta_pagina_id si no existe ───────────────────
    lead_cols = [c["name"] for c in _ins(bind).get_columns("leads")]
    if "meta_pagina_id" not in lead_cols:
        op.add_column("leads",
                      sa.Column("meta_pagina_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_table("meta_campana_snapshots")
    op.drop_table("meta_portafolios")
    op.drop_column("leads", "meta_pagina_id")
