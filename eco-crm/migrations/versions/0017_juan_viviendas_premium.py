"""Agrega línea WhatsApp de Juan Ciapessoni (viviendas premium)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Verificar si ya existe una fila para la página de viviendas premium (WABA 1740490483704122)
    result = bind.execute(text("""
        SELECT id FROM meta_paginas WHERE numero_whatsapp = '+5491162692583'
    """)).fetchone()

    if result:
        bind.execute(text("""
            UPDATE meta_paginas
            SET vendedor        = 'Ciapessoni Juan',
                portafolio      = 'Eco Módulos y Piscinas',
                wa_phone_id     = NULL,
                vendedor_slug   = 'juan',
                aliado_codigo   = NULL,
                activa          = TRUE
            WHERE numero_whatsapp = '+5491162692583'
        """))
    else:
        bind.execute(text("""
            INSERT INTO meta_paginas
                (page_id, nombre, vendedor, numero_whatsapp, portafolio,
                 wa_phone_id, vendedor_slug, aliado_codigo, activa)
            VALUES
                ('viviendas_premium_juan', 'Viviendas Premium',
                 'Ciapessoni Juan', '+5491162692583', 'Eco Módulos y Piscinas',
                 NULL, 'juan', NULL, TRUE)
        """))


def downgrade() -> None:
    pass
