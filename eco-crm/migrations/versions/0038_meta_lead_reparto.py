"""Preferencias de reparto Meta por producto, campaña y organización.

Revision ID: 0038
Revises: 0037
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("meta_lead_campanas",
        sa.Column("form_id", sa.String(50), primary_key=True),
        sa.Column("page_id", sa.String(50), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("producto", sa.String(20), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actualizado_por", sa.String(150)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("meta_lead_destinos",
        sa.Column("clave", sa.String(60), primary_key=True),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("modulos", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("piscinas", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actualizado_por", sa.String(150)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("meta_lead_organizaciones",
        sa.Column("form_id", sa.String(50), sa.ForeignKey("meta_lead_campanas.form_id"), primary_key=True),
        sa.Column("organizacion_codigo", sa.String(20), sa.ForeignKey("aliados.codigo"), primary_key=True),
        sa.Column("habilitada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actualizado_por", sa.String(150)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("meta_lead_recepciones",
        sa.Column("meta_lead_id", sa.String(100), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("form_id", sa.String(50), nullable=False, server_default=""),
        sa.Column("datos_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_meta_lead_recepciones_lead_id", "meta_lead_recepciones", ["lead_id"])
    op.create_index("ix_meta_lead_recepciones_form_id", "meta_lead_recepciones", ["form_id"])
    table = sa.table("meta_lead_campanas", sa.column("form_id"), sa.column("page_id"),
                     sa.column("nombre"), sa.column("producto"), sa.column("activa"))
    op.bulk_insert(table, [{"form_id": "1122869520123560", "page_id": "634872006383162",
                           "nombre": "Plan 18 Pasos", "producto": "MODULO", "activa": True}])


def downgrade():
    op.drop_table("meta_lead_recepciones")
    op.drop_table("meta_lead_organizaciones")
    op.drop_table("meta_lead_destinos")
    op.drop_table("meta_lead_campanas")
