"""control center: crear tabla comandos_agente

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-13
"""
from alembic import op
from sqlalchemy import text

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(text("""
        CREATE TABLE IF NOT EXISTS comandos_agente (
            id              SERIAL PRIMARY KEY,
            tipo            VARCHAR(20)  DEFAULT 'LIBRE',
            area            VARCHAR(30)  DEFAULT 'GENERAL',
            prioridad       VARCHAR(10)  DEFAULT 'NORMAL',
            titulo          VARCHAR(200) DEFAULT '',
            instruccion     TEXT         NOT NULL,
            contexto        JSONB        DEFAULT '{}',
            agente_destino  VARCHAR(100) DEFAULT '',
            estado          VARCHAR(20)  DEFAULT 'PENDIENTE',
            respuesta       TEXT         DEFAULT '',
            error_detalle   TEXT         DEFAULT '',
            http_status     INTEGER,
            enviado_por_id  INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ  DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  DEFAULT NOW()
        )
    """))


def downgrade() -> None:
    op.get_bind().execute(text("DROP TABLE IF EXISTS comandos_agente"))
