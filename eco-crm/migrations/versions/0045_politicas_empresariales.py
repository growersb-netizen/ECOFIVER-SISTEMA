"""Políticas empresariales versionadas (capa 2 de instrucciones) e historial

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-31

Solo crea tablas.
"""
from alembic import op
from sqlalchemy import text

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    b = op.get_bind()
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS politicas_empresariales (
            id SERIAL PRIMARY KEY, codigo VARCHAR(60) NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            titulo VARCHAR(200) NOT NULL, objetivo TEXT DEFAULT '', instruccion TEXT NOT NULL,
            departamento VARCHAR(30) DEFAULT '', agentes JSON DEFAULT '[]', metrica_exito TEXT DEFAULT '',
            estado VARCHAR(25) NOT NULL DEFAULT 'PENDIENTE_APROBACION', autor VARCHAR(60) DEFAULT '',
            aprobado_por_id INTEGER REFERENCES usuarios(id), aprobado_at TIMESTAMPTZ, aplicada_desde TIMESTAMPTZ,
            resultado TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_politicas_codigo ON politicas_empresariales (codigo, version)"))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS politicas_eventos (
            id SERIAL PRIMARY KEY, politica_id INTEGER NOT NULL, de VARCHAR(25) DEFAULT '', a VARCHAR(25) NOT NULL,
            actor VARCHAR(60) NOT NULL, detalle TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT now())"""))


def downgrade() -> None:
    raise RuntimeError("Downgrade de 0045 deshabilitado: borraría políticas e historial")
