"""Vincula línea WhatsApp de Oscar Juárez (AL-035) a Viviendas Argentinas

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Viviendas Argentinas ya existe como página FB; la actualizamos con datos WA
    bind.execute(text("""
        UPDATE meta_paginas
        SET vendedor      = 'Juárez Oscar',
            numero_whatsapp = '+5493813500329',
            portafolio      = 'Eco Módulos y Piscinas',
            wa_phone_id     = NULL,
            vendedor_slug   = 'oscar',
            aliado_codigo   = 'AL-035',
            activa          = TRUE
        WHERE page_id = '777184055483861'
    """))


def downgrade() -> None:
    pass
