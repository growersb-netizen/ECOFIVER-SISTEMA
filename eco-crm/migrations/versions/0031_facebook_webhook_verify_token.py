"""Inserta facebook_webhook_verify_token en configuracion_sistema si no existe

Revision ID: 0031
Revises: 0029
Create Date: 2026-10-22
"""
from alembic import op
from sqlalchemy import text

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_TOKEN = "ecofiver-webhook-verify-2026"


def upgrade():
    bind = op.get_bind()
    existing = bind.execute(text(
        "SELECT id FROM configuracion_sistema WHERE clave = 'facebook_webhook_verify_token'"
    )).fetchone()
    if not existing:
        bind.execute(text(
            "INSERT INTO configuracion_sistema (clave, valor, es_secreto, categoria) "
            "VALUES ('facebook_webhook_verify_token', :val, FALSE, 'meta')"
        ), {"val": _TOKEN})


def downgrade():
    bind = op.get_bind()
    bind.execute(text(
        "DELETE FROM configuracion_sistema WHERE clave = 'facebook_webhook_verify_token'"
    ))
