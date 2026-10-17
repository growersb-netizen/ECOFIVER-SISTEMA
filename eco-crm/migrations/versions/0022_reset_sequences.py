"""Resetea secuencias desincronizadas de tablas con id serial

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # Resetea la secuencia de cada tabla al MAX(id) actual para evitar UniqueViolation
    for table in ("ventas_contado", "entregas", "ordenes_fabrica_piscinas", "ordenes_fabrica_modulos",
                  "aliados", "usuarios", "presupuestos", "pipeline_etapas"):
        if table not in tables:
            continue
        seq = f"{table}_id_seq"
        bind.execute(sa.text(
            f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1))"
        ))


def downgrade() -> None:
    pass
