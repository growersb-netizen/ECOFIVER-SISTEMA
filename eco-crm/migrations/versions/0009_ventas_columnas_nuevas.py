"""ventas_contado y ventas_financiadas: columnas agregadas sin migración

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── equipos_instaladores ─────────────────────────────────────────────────
    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS equipos_instaladores (
            id              SERIAL PRIMARY KEY,
            nombre          VARCHAR(100) NOT NULL,
            tipo            VARCHAR(20)  DEFAULT 'PROPIO',
            responsable     VARCHAR(100) DEFAULT '',
            integrantes     TEXT         DEFAULT '',
            telefono        VARCHAR(30)  DEFAULT '',
            zonas_cobertura TEXT         DEFAULT '',
            activo          BOOLEAN      DEFAULT true,
            notas           TEXT         DEFAULT '',
            created_at      TIMESTAMPTZ  DEFAULT now()
        )
    """))

    # ── ventas_contado: columnas nuevas ──────────────────────────────────────
    for stmt in [
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS desde_stock        BOOLEAN      DEFAULT false",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS con_banio           BOOLEAN      DEFAULT false",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS con_cocina          BOOLEAN      DEFAULT false",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS con_puerta_ingreso  BOOLEAN      DEFAULT false",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS con_ventana_balcon  BOOLEAN      DEFAULT false",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS sobre_piso          VARCHAR(10)",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS modalidad_cobro     VARCHAR(20)  DEFAULT 'PREVIO'",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS equipo_instalador_id INTEGER",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS tarifa_instalacion  FLOAT",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS cobro_estado        VARCHAR(20)",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS cobro_monto_real    FLOAT",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS cobro_fecha         TIMESTAMPTZ",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS cobro_notas         TEXT         DEFAULT ''",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS aliado_codigo       VARCHAR(20)",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS confirmacion_48hs_en TIMESTAMPTZ",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS contrato_generado_en TIMESTAMPTZ",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS cliente_domicilio   VARCHAR(300)",
        "ALTER TABLE ventas_contado ADD COLUMN IF NOT EXISTS cliente_email       VARCHAR(150)",
    ]:
        bind.execute(text(stmt))

    # ── ventas_financiadas: columnas nuevas ──────────────────────────────────
    for stmt in [
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS aliado_codigo                        VARCHAR(20)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS scoring_situacion                    INTEGER",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS declaracion_jurada_requerida         BOOLEAN DEFAULT false",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS declaracion_jurada_confirmada_en     TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS inscripcion_pagada_en                TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS contrato_generado_en                 TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS monto_pagado_inscripcion             FLOAT DEFAULT 0",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS primera_sena_en                      TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS sena_vence_en                        TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS recibo_generado_en                   TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS link_confirmacion_token              VARCHAR(64)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS link_confirmacion_confirmada_en      TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS auditoria_bienvenida_en              TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS licitacion_solicitada_en             TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS solicitud_recibo_en                  TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS solicitud_recibo_monto               FLOAT",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS solicitud_recibo_comprobante         VARCHAR(500)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS solicitud_recibo_notas               TEXT",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS solicitud_recibo_estado              VARCHAR(20)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS solicitud_recibo_notas_admin         TEXT",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS numero_solicitud                     VARCHAR(30)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cliente_dni                          VARCHAR(20)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cliente_cuil                         VARCHAR(20)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cliente_domicilio                    VARCHAR(300)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cliente_estado_civil                 VARCHAR(30)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cliente_ocupacion                    VARCHAR(100)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cliente_email                        VARCHAR(150)",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cac_pct                             FLOAT",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS cac_excepcion_pct                   FLOAT",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS ultima_indexacion                    TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS updated_at                           TIMESTAMPTZ",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS monto_inscripcion                    FLOAT",
        "ALTER TABLE ventas_financiadas ADD COLUMN IF NOT EXISTS estado_admision                      VARCHAR(20)",
    ]:
        bind.execute(text(stmt))


def downgrade() -> None:
    pass
