"""Control empresarial: estado administrativo de agentes, historial y guardias

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-31

Solo crea tablas. Sin filas = todos los agentes ACTIVOS (comportamiento actual).
"""
from alembic import op
from sqlalchemy import text

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    b = op.get_bind()
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS agentes_control (
            agente VARCHAR(30) PRIMARY KEY,
            estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
            motivo TEXT DEFAULT '',
            actualizado_por_id INTEGER REFERENCES usuarios(id),
            actualizado_at TIMESTAMPTZ DEFAULT now()
        )"""))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS agentes_control_eventos (
            id SERIAL PRIMARY KEY,
            agente VARCHAR(30) NOT NULL,
            estado_anterior VARCHAR(20) DEFAULT '',
            estado_nuevo VARCHAR(20) NOT NULL,
            motivo TEXT DEFAULT '',
            usuario_id INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )"""))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_agentes_control_eventos_agente ON agentes_control_eventos (agente)"))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS guardias_operativas (
            id SERIAL PRIMARY KEY,
            alcance VARCHAR(40) NOT NULL,
            desde TIMESTAMPTZ NOT NULL,
            hasta TIMESTAMPTZ NOT NULL,
            motivo TEXT DEFAULT '',
            creado_por_id INTEGER REFERENCES usuarios(id),
            activa BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )"""))


def downgrade() -> None:
    raise RuntimeError("Downgrade de 0041 deshabilitado: borraría el historial de control")
