"""contactos_proactivos: autorización de salientes (ventana 24 h de WhatsApp y deduplicación)

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-31

Solo crea una tabla.
"""
from alembic import op
from sqlalchemy import text

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    b = op.get_bind()
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS contactos_proactivos (
            id SERIAL PRIMARY KEY, telefono_clave VARCHAR(20) NOT NULL, origen VARCHAR(80) DEFAULT '',
            agente VARCHAR(30) DEFAULT '', created_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_contactos_proactivos_tel ON contactos_proactivos (telefono_clave, created_at)"))


def downgrade() -> None:
    op.get_bind().execute(text("DROP TABLE IF EXISTS contactos_proactivos"))
