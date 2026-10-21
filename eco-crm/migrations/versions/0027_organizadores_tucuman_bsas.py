"""Activa es_organizador para Javier Ruiz (Tucumán) y Claudia Ríos (Buenos Aires)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-21
"""
from alembic import op
from sqlalchemy import text

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Claudia Ríos — código conocido AL-010, zona Buenos Aires
    bind.execute(text("""
        UPDATE aliados
        SET es_organizador = TRUE,
            zona = CASE WHEN (zona IS NULL OR zona = '') THEN 'Buenos Aires' ELSE zona END
        WHERE codigo = 'AL-010'
    """))

    # Javier Ruiz — búsqueda por nombre (Tucumán)
    bind.execute(text("""
        UPDATE aliados
        SET es_organizador = TRUE,
            zona = CASE WHEN (zona IS NULL OR zona = '') THEN 'Tucumán' ELSE zona END
        WHERE (nombre ILIKE '%Javier%Ruiz%' OR nombre ILIKE '%Ruiz%Javier%')
          AND estado = 'activo'
    """))


def downgrade():
    bind = op.get_bind()
    bind.execute(text("UPDATE aliados SET es_organizador = FALSE WHERE codigo = 'AL-010'"))
    bind.execute(text("""
        UPDATE aliados SET es_organizador = FALSE
        WHERE nombre ILIKE '%Javier%Ruiz%' OR nombre ILIKE '%Ruiz%Javier%'
    """))
