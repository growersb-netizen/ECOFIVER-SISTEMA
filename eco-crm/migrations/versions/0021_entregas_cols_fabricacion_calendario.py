"""Agrega columnas de fabricación y calendario a entregas

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Agrega columnas a 'entregas' que pueden faltar si la tabla fue creada antes
    existing_cols = {c["name"] for c in inspector.get_columns("entregas")}

    if "requiere_fabricacion" not in existing_cols:
        op.add_column("entregas", sa.Column("requiere_fabricacion", sa.Boolean(), nullable=True, server_default="false"))

    if "auto_generada" not in existing_cols:
        op.add_column("entregas", sa.Column("auto_generada", sa.Boolean(), nullable=True, server_default="false"))

    if "fecha_original_venta" not in existing_cols:
        op.add_column("entregas", sa.Column("fecha_original_venta", sa.DateTime(timezone=True), nullable=True))

    if "confirmada_por_id" not in existing_cols:
        op.add_column("entregas", sa.Column("confirmada_por_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key(
                "fk_entregas_confirmada_por_id",
                "entregas", "usuarios",
                ["confirmada_por_id"], ["id"]
            )
        except Exception:
            pass

    # 'ordenes_fabrica_piscinas' y 'ordenes_fabrica_modulos': asegurar que existen
    tables = inspector.get_table_names()
    if "ordenes_fabrica_piscinas" not in tables:
        op.create_table(
            "ordenes_fabrica_piscinas",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("venta_contado_id", sa.Integer(), sa.ForeignKey("ventas_contado.id"), nullable=True),
            sa.Column("cliente_nombre", sa.String(150)),
            sa.Column("modelo", sa.String(100), default=""),
            sa.Column("color", sa.String(50), default=""),
            sa.Column("estado", sa.String(20), default="EN_ESPERA"),
            sa.Column("notas", sa.Text(), default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "ordenes_fabrica_modulos" not in tables:
        op.create_table(
            "ordenes_fabrica_modulos",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("venta_contado_id", sa.Integer(), sa.ForeignKey("ventas_contado.id"), nullable=True),
            sa.Column("cliente_nombre", sa.String(150)),
            sa.Column("superficie_m2", sa.Float(), default=0),
            sa.Column("configuracion", sa.Text(), default=""),
            sa.Column("estado", sa.String(20), default="EN_ESPERA"),
            sa.Column("notas", sa.Text(), default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    pass
