"""Resetea secuencias usando pg_get_serial_sequence para obtener el nombre correcto

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    targets = [
        "ventas_contado", "entregas", "ordenes_fabrica_piscinas",
        "ordenes_fabrica_modulos", "aliados", "usuarios", "presupuestos",
    ]
    for table in targets:
        if table not in tables:
            continue
        # pg_get_serial_sequence devuelve el nombre real de la secuencia,
        # sin depender de la convención de nombres
        bind.execute(sa.text(
            f"SELECT setval("
            f"  pg_get_serial_sequence('{table}', 'id'),"
            f"  COALESCE((SELECT MAX(id) FROM {table}), 1)"
            f")"
        ))


def downgrade() -> None:
    pass
