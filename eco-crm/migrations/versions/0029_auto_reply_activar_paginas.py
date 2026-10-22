"""Activa auto-reply mensajes + comentarios + eliminar negativos en todas las páginas activas

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-22
"""
from alembic import op
from sqlalchemy import text

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(text("""
        UPDATE meta_paginas
        SET
            auto_reply_mensajes    = TRUE,
            auto_reply_comentarios = TRUE,
            auto_eliminar_negativos = TRUE
        WHERE activa = TRUE
    """))


def downgrade():
    bind = op.get_bind()
    bind.execute(text("""
        UPDATE meta_paginas
        SET
            auto_reply_mensajes    = FALSE,
            auto_reply_comentarios = FALSE,
            auto_eliminar_negativos = FALSE
        WHERE activa = TRUE
    """))
