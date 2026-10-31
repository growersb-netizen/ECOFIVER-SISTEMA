"""exclusiones_comerciales: bajas de comunicaciones comerciales por teléfono

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-29

Solo agrega una tabla nueva. No modifica ni borra datos existentes.
"""
from alembic import op
from sqlalchemy import text

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS exclusiones_comerciales (
            id SERIAL PRIMARY KEY,
            telefono_clave VARCHAR(20) NOT NULL UNIQUE,
            telefono VARCHAR(30),
            lead_id INTEGER,
            canal VARCHAR(30),
            texto VARCHAR(300),
            activa BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now(),
            actualizada_at TIMESTAMPTZ DEFAULT now(),
            reactivada_por VARCHAR(150),
            motivo_reactivacion VARCHAR(300)
        )
    """))
    bind.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_exclusiones_comerciales_lead_id ON exclusiones_comerciales (lead_id)"
    ))


def downgrade() -> None:
    # Borraría las bajas registradas: se deja explícito y manual.
    raise RuntimeError("Downgrade de 0039 deshabilitado: eliminaría bajas pedidas por contactos")
