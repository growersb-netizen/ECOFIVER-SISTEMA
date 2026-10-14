"""Agrega vendedor_slug y aliado_codigo a meta_paginas; registra línea de Javier Masera

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Nuevas columnas
    bind.execute(text("ALTER TABLE meta_paginas ADD COLUMN IF NOT EXISTS vendedor_slug VARCHAR(50)"))
    bind.execute(text("ALTER TABLE meta_paginas ADD COLUMN IF NOT EXISTS aliado_codigo VARCHAR(20)"))

    # Seed: línea Melanie (Stefanía Devía / Claudia Ríos)
    bind.execute(text("""
        UPDATE meta_paginas
        SET vendedor_slug = 'melanie', aliado_codigo = 'AL-010'
        WHERE wa_phone_id = '1562122100308561'
    """))

    # Registrar línea Javier Masera (Rosario) — wa_phone_id NULL hasta auto-descubrimiento
    bind.execute(text("""
        INSERT INTO meta_paginas
            (page_id, nombre, portafolio, numero_whatsapp, vendedor,
             wa_phone_id, vendedor_slug, aliado_codigo, activa)
        VALUES
            ('piscinas_fabrica_directa', 'Piscinas Fábrica Directa',
             'Eco Módulos y Piscinas', '+5493417536439', 'Masera Javier',
             NULL, 'javier', 'AL-032', TRUE)
        ON CONFLICT (page_id) DO UPDATE
            SET vendedor_slug = EXCLUDED.vendedor_slug,
                aliado_codigo = EXCLUDED.aliado_codigo,
                numero_whatsapp = EXCLUDED.numero_whatsapp
    """))


def downgrade() -> None:
    pass
