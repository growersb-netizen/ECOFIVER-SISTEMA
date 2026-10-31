"""Cotización de contado: caché de distancias por ruta desde la fábrica, promociones autorizadas y
desglose interno de la venta (producto / traslado / descuento)

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-31

Solo agrega tablas y columnas nulas.
"""
from alembic import op
from sqlalchemy import text

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    b = op.get_bind()
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS distancias_localidades (
            id SERIAL PRIMARY KEY, clave VARCHAR(300) NOT NULL UNIQUE, tipo VARCHAR(12) DEFAULT 'LOCALIDAD',
            localidad VARCHAR(120) NOT NULL, provincia VARCHAR(80) DEFAULT '', destino_texto VARCHAR(300) DEFAULT '',
            origen_texto VARCHAR(300) DEFAULT '', origen_clave VARCHAR(300) DEFAULT '',
            km_ida DOUBLE PRECISION NOT NULL, proveedor VARCHAR(40) DEFAULT '', ruta_ref TEXT DEFAULT '',
            estado VARCHAR(12) DEFAULT 'CALCULADA', fuente VARCHAR(200) DEFAULT '',
            cargado_por_id INTEGER REFERENCES usuarios(id), actualizado_at TIMESTAMPTZ DEFAULT now())"""))
    b.execute(text("""
        CREATE TABLE IF NOT EXISTS promociones_comerciales (
            id SERIAL PRIMARY KEY, nombre VARCHAR(150) NOT NULL, tipo VARCHAR(20) NOT NULL,
            valor DOUBLE PRECISION NOT NULL, producto VARCHAR(20) DEFAULT 'PISCINA', desde DATE NOT NULL,
            hasta DATE NOT NULL, requiere_reserva_fecha BOOLEAN DEFAULT TRUE, activa BOOLEAN DEFAULT TRUE,
            autorizada_por_id INTEGER REFERENCES usuarios(id), nota TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT now())"""))
    for col, tipo in (("flete_bruto", "DOUBLE PRECISION"), ("descuento_flete", "DOUBLE PRECISION"),
                      ("promocion_id", "INTEGER"), ("precio_total_acordado", "DOUBLE PRECISION"),
                      ("fecha_entrega_solicitada", "DATE")):
        b.execute(text(f"ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS {col} {tipo}"))


def downgrade() -> None:
    raise RuntimeError("Downgrade de 0043 deshabilitado: borraría distancias verificadas y promociones")
