"""Agrega columna tipo a meta_paginas; limpia datos WA lines

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-22

- Agrega columna `tipo` (PAGINA_FB | LINEA_WA) a meta_paginas
- Clasifica líneas WA existentes (page_ids no numéricos)
- Corrige emoji en numero_whatsapp de viviendas_premium_juan
- Limpia numero_whatsapp de la página FB de Javier Massera para evitar colisión
"""
from alembic import op
from sqlalchemy import text

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

# page_ids conocidos que son líneas WA puras (no páginas FB reales)
_LINEAS_WA_PAGEIDS = [
    "piscinas_fabrica_directa",
    "wa_agentes_ventas",
    "viviendas_premium_juan",
    # 910994205421879 usa el wa_phone_id como page_id — es también LINEA_WA
]


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Agregar columna tipo si no existe
    bind.execute(text(
        "ALTER TABLE meta_paginas ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'PAGINA_FB'"
    ))

    # 2. Marcar líneas WA por page_id no numérico
    bind.execute(text(
        "UPDATE meta_paginas SET tipo = 'LINEA_WA' "
        "WHERE tipo IS NULL OR tipo = 'PAGINA_FB' "
        "AND page_id ~ '[^0-9]'"   # cualquier carácter no numérico en page_id
    ))

    # 3. Asegurar que los page_ids conocidos estén marcados
    for pid in _LINEAS_WA_PAGEIDS:
        bind.execute(text(
            "UPDATE meta_paginas SET tipo = 'LINEA_WA' WHERE page_id = :pid"
        ), {"pid": pid})

    # 4. Corregir emoji en viviendas_premium_juan
    bind.execute(text(
        "UPDATE meta_paginas "
        "SET numero_whatsapp = '+5491162692583' "
        "WHERE page_id = 'viviendas_premium_juan' "
        "AND numero_whatsapp LIKE '%162692583%'"
    ))

    # 5. Limpiar numero_whatsapp de la página FB 1227473720444757 (Piscinas Fábrica Directa FB)
    # para que el fallback de número solo encuentre la línea WA piscinas_fabrica_directa
    bind.execute(text(
        "UPDATE meta_paginas "
        "SET numero_whatsapp = NULL "
        "WHERE page_id = '1227473720444757' "
        "AND numero_whatsapp LIKE '%3417536439%'"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        "ALTER TABLE meta_paginas DROP COLUMN IF EXISTS tipo"
    ))
