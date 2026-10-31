"""Circuito comercial: contado (estados separados), expedientes de financiación con
Admisión humana, comisiones del propietario, gastos publicitarios y objetivos

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-31

Solo agrega columnas (nulas) y tablas. No modifica ventas, pagos ni comisiones existentes.
"""
from alembic import op
from sqlalchemy import text

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_COLS_VENTA = [
    ("circuito_estado", "VARCHAR(30)"), ("cerrada_por", "VARCHAR(50)"), ("lead_id", "INTEGER"),
    ("entrega_confirmada_at", "TIMESTAMPTZ"), ("entrega_confirmada_por_id", "INTEGER"),
    ("entrega_evidencia", "TEXT"), ("cobro_confirmado_por_id", "INTEGER"), ("cobro_evidencia", "TEXT"),
]


def upgrade() -> None:
    b = op.get_bind()
    for col, tipo in _COLS_VENTA:
        b.execute(text(f"ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS {col} {tipo}"))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS expedientes_financiacion (
            id SERIAL PRIMARY KEY, lead_id INTEGER, cliente_nombre VARCHAR(150) NOT NULL,
            cliente_telefono VARCHAR(30), producto VARCHAR(20) NOT NULL, modelo VARCHAR(150) DEFAULT '',
            valor_cuota_estimado DOUBLE PRECISION, datos_apertura JSON DEFAULT '{}',
            estado VARCHAR(30) NOT NULL DEFAULT 'CONSULTA_RECIBIDA', abierto_por VARCHAR(50) DEFAULT '',
            asignado_admision_id INTEGER REFERENCES usuarios(id), videollamada_id INTEGER,
            venta_financiada_id INTEGER REFERENCES ventas_financiadas(id),
            cuotas_iniciales_confirmadas_at TIMESTAMPTZ, cuotas_iniciales_confirmadas_por_id INTEGER,
            created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_expedientes_estado ON expedientes_financiacion (estado)"))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_expedientes_lead ON expedientes_financiacion (lead_id)"))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS expedientes_eventos (
            id SERIAL PRIMARY KEY, expediente_id INTEGER NOT NULL, estado_anterior VARCHAR(30) DEFAULT '',
            estado_nuevo VARCHAR(30) NOT NULL, actor VARCHAR(60) NOT NULL, detalle TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_expedientes_eventos_exp ON expedientes_eventos (expediente_id)"))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS comisiones_propietario (
            id SERIAL PRIMARY KEY, clave VARCHAR(80) NOT NULL UNIQUE, tipo VARCHAR(20) NOT NULL,
            venta_contado_id INTEGER REFERENCES ventas_contado(id),
            venta_financiada_id INTEGER REFERENCES ventas_financiadas(id), expediente_id INTEGER,
            producto VARCHAR(20) DEFAULT '', base_calculo DOUBLE PRECISION NOT NULL, regla VARCHAR(80) NOT NULL,
            monto DOUBLE PRECISION NOT NULL, estado VARCHAR(20) NOT NULL DEFAULT 'GENERADA',
            generada_at TIMESTAMPTZ NOT NULL, cobrada_at TIMESTAMPTZ, cobrada_evidencia TEXT,
            anulada_motivo TEXT, actualizada_por_id INTEGER, canal VARCHAR(40),
            created_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS gastos_publicitarios (
            id SERIAL PRIMARY KEY, tipo VARCHAR(15) NOT NULL, fecha DATE NOT NULL,
            monto DOUBLE PRECISION NOT NULL, campana VARCHAR(150) DEFAULT '', producto VARCHAR(20) DEFAULT '',
            canal VARCHAR(40) DEFAULT '', nota TEXT DEFAULT '', registrado_por_id INTEGER REFERENCES usuarios(id),
            created_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS objetivos_economicos (
            id SERIAL PRIMARY KEY, periodo VARCHAR(7) NOT NULL, indicador VARCHAR(40) NOT NULL,
            producto VARCHAR(20) DEFAULT '', canal VARCHAR(40) DEFAULT '', valor DOUBLE PRECISION NOT NULL,
            version INTEGER NOT NULL DEFAULT 1, vigente BOOLEAN DEFAULT TRUE, origen VARCHAR(40) DEFAULT 'panel',
            nota TEXT DEFAULT '', autorizado_por_id INTEGER REFERENCES usuarios(id),
            created_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("CREATE INDEX IF NOT EXISTS ix_objetivos_periodo ON objetivos_economicos (periodo)"))


def downgrade() -> None:
    raise RuntimeError("Downgrade de 0042 deshabilitado: borraría expedientes, decisiones de Admisión y comisiones")
