"""inbox: wa_linea en mensajes; wa_phone_id en meta_paginas

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
    from sqlalchemy import inspect as _ins, text
    bind = op.get_bind()

    # ── inbox_mensajes: columna wa_linea ──────────────────────────────────────
    inbox_cols = [c["name"] for c in _ins(bind).get_columns("inbox_mensajes")]
    if "wa_linea" not in inbox_cols:
        op.add_column(
            "inbox_mensajes",
            sa.Column("wa_linea", sa.String(50), nullable=True),
        )

    # ── meta_paginas: columna wa_phone_id ────────────────────────────────────
    meta_cols = [c["name"] for c in _ins(bind).get_columns("meta_paginas")]
    if "wa_phone_id" not in meta_cols:
        op.add_column(
            "meta_paginas",
            sa.Column("wa_phone_id", sa.String(60), nullable=True),
        )

    # ── Asignar Stefanía Devía a la línea 1126036495 ──────────────────────────
    bind.execute(text("""
        UPDATE meta_paginas
        SET vendedor = 'Stefanía Devía',
            nombre   = COALESCE(NULLIF(nombre,''), 'Ecofiver Módulos y Piscinas')
        WHERE numero_whatsapp LIKE '%1126036495%'
          AND (vendedor IS NULL OR vendedor = '')
    """))


def downgrade() -> None:
    op.drop_column("inbox_mensajes", "wa_linea")
    op.drop_column("meta_paginas", "wa_phone_id")
