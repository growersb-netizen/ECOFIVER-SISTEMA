"""Motor de tareas: columnas en comandos_agente + tareas_eventos + aprobaciones_accion

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-31

Solo agrega columnas y tablas. Los comandos existentes quedan con
version_motor NULL: no se ejecutan retroactivamente.
"""
from alembic import op
from sqlalchemy import text

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

_COLUMNAS = [
    ("version_motor", "INTEGER"),
    ("clave_idempotencia", "VARCHAR(120)"),
    ("intentos", "INTEGER DEFAULT 0"),
    ("max_intentos", "INTEGER DEFAULT 3"),
    ("proximo_intento", "TIMESTAMPTZ"),
    ("lease_token", "VARCHAR(40)"),
    ("lease_hasta", "TIMESTAMPTZ"),
    ("worker", "VARCHAR(80)"),
    ("padre_id", "INTEGER"),
    ("raiz_id", "INTEGER"),
    ("profundidad", "INTEGER DEFAULT 0"),
    ("creado_por_agente", "VARCHAR(50)"),
    ("resultado", "JSON"),
    ("evidencia", "JSON"),
    ("costo_usd", "DOUBLE PRECISION DEFAULT 0"),
    ("cancelacion_solicitada", "BOOLEAN DEFAULT FALSE"),
    ("iniciado_at", "TIMESTAMPTZ"),
    ("finalizado_at", "TIMESTAMPTZ"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for col, tipo in _COLUMNAS:
        bind.execute(text(f"ALTER TABLE comandos_agente ADD COLUMN IF NOT EXISTS {col} {tipo}"))
    bind.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_comandos_agente_idem "
                      "ON comandos_agente (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL"))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_comandos_agente_cola "
                      "ON comandos_agente (version_motor, estado, proximo_intento)"))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_comandos_agente_padre ON comandos_agente (padre_id)"))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_comandos_agente_raiz ON comandos_agente (raiz_id)"))
    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS tareas_eventos (
            id SERIAL PRIMARY KEY,
            tarea_id INTEGER NOT NULL,
            tipo VARCHAR(30) NOT NULL,
            detalle TEXT DEFAULT '',
            actor VARCHAR(100) DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT now()
        )"""))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_tareas_eventos_tarea ON tareas_eventos (tarea_id)"))
    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS aprobaciones_accion (
            id SERIAL PRIMARY KEY,
            tarea_id INTEGER,
            agente VARCHAR(50) NOT NULL,
            tipo_accion VARCHAR(50) NOT NULL,
            datos JSON DEFAULT '{}',
            motivo TEXT DEFAULT '',
            estado VARCHAR(20) DEFAULT 'PENDIENTE',
            decidido_por_id INTEGER REFERENCES usuarios(id),
            decidido_at TIMESTAMPTZ,
            comentario TEXT DEFAULT '',
            resultado TEXT DEFAULT '',
            lease_token VARCHAR(40),
            created_at TIMESTAMPTZ DEFAULT now()
        )"""))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_aprobaciones_estado ON aprobaciones_accion (estado)"))


def downgrade() -> None:
    raise RuntimeError("Downgrade de 0040 deshabilitado: borraría historial y aprobaciones auditadas")
