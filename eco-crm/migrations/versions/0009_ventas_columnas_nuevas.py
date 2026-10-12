"""ventas_contado y ventas_financiadas: columnas agregadas sin migración

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect as _ins
    bind = op.get_bind()
    tables = _ins(bind).get_table_names()

    # ── equipos_instaladores (necesario para FK en ventas_contado) ───────────
    if "equipos_instaladores" not in tables:
        op.create_table(
            "equipos_instaladores",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("nombre", sa.String(100), nullable=False),
            sa.Column("tipo", sa.String(20), server_default="PROPIO"),
            sa.Column("responsable", sa.String(100), server_default=""),
            sa.Column("integrantes", sa.Text(), server_default=""),
            sa.Column("telefono", sa.String(30), server_default=""),
            sa.Column("zonas_cobertura", sa.Text(), server_default=""),
            sa.Column("activo", sa.Boolean(), server_default="true"),
            sa.Column("notas", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── ventas_contado: columnas sin migración ───────────────────────────────
    if "ventas_contado" in tables:
        vc = [c["name"] for c in _ins(bind).get_columns("ventas_contado")]

        for col in ("desde_stock", "con_banio", "con_cocina", "con_puerta_ingreso", "con_ventana_balcon"):
            if col not in vc:
                op.add_column("ventas_contado", sa.Column(col, sa.Boolean(), server_default="false", nullable=True))

        if "sobre_piso" not in vc:
            op.add_column("ventas_contado", sa.Column("sobre_piso", sa.String(10), nullable=True))
        if "modalidad_cobro" not in vc:
            op.add_column("ventas_contado", sa.Column("modalidad_cobro", sa.String(20), server_default="PREVIO", nullable=True))
        if "equipo_instalador_id" not in vc:
            op.add_column("ventas_contado", sa.Column("equipo_instalador_id", sa.Integer(), nullable=True))
        if "tarifa_instalacion" not in vc:
            op.add_column("ventas_contado", sa.Column("tarifa_instalacion", sa.Float(), nullable=True))
        if "cobro_estado" not in vc:
            op.add_column("ventas_contado", sa.Column("cobro_estado", sa.String(20), nullable=True))
        if "cobro_monto_real" not in vc:
            op.add_column("ventas_contado", sa.Column("cobro_monto_real", sa.Float(), nullable=True))
        if "cobro_fecha" not in vc:
            op.add_column("ventas_contado", sa.Column("cobro_fecha", sa.DateTime(timezone=True), nullable=True))
        if "cobro_notas" not in vc:
            op.add_column("ventas_contado", sa.Column("cobro_notas", sa.Text(), server_default="", nullable=True))
        if "aliado_codigo" not in vc:
            op.add_column("ventas_contado", sa.Column("aliado_codigo", sa.String(20), nullable=True))
        if "confirmacion_48hs_en" not in vc:
            op.add_column("ventas_contado", sa.Column("confirmacion_48hs_en", sa.DateTime(timezone=True), nullable=True))
        if "contrato_generado_en" not in vc:
            op.add_column("ventas_contado", sa.Column("contrato_generado_en", sa.DateTime(timezone=True), nullable=True))
        if "cliente_domicilio" not in vc:
            op.add_column("ventas_contado", sa.Column("cliente_domicilio", sa.String(300), nullable=True))
        if "cliente_email" not in vc:
            op.add_column("ventas_contado", sa.Column("cliente_email", sa.String(150), nullable=True))

    # ── ventas_financiadas: columnas sin migración ───────────────────────────
    if "ventas_financiadas" in tables:
        vf = [c["name"] for c in _ins(bind).get_columns("ventas_financiadas")]

        datetime_cols = [
            "inscripcion_pagada_en", "contrato_generado_en", "primera_sena_en",
            "sena_vence_en", "recibo_generado_en", "link_confirmacion_confirmada_en",
            "auditoria_bienvenida_en", "licitacion_solicitada_en", "solicitud_recibo_en",
            "declaracion_jurada_confirmada_en", "ultima_indexacion", "updated_at",
        ]
        for col in datetime_cols:
            if col not in vf:
                op.add_column("ventas_financiadas", sa.Column(col, sa.DateTime(timezone=True), nullable=True))

        str_cols = {
            "numero_solicitud": sa.String(30),
            "cliente_dni": sa.String(20),
            "cliente_cuil": sa.String(20),
            "cliente_domicilio": sa.String(300),
            "cliente_estado_civil": sa.String(30),
            "cliente_ocupacion": sa.String(100),
            "cliente_email": sa.String(150),
            "link_confirmacion_token": sa.String(64),
            "solicitud_recibo_comprobante": sa.String(500),
            "solicitud_recibo_estado": sa.String(20),
            "aliado_codigo": sa.String(20),
            "estado_admision": sa.String(20),
        }
        for col, typ in str_cols.items():
            if col not in vf:
                op.add_column("ventas_financiadas", sa.Column(col, typ, nullable=True))

        float_cols = [
            "monto_inscripcion", "cac_pct", "cac_excepcion_pct",
            "monto_pagado_inscripcion", "solicitud_recibo_monto",
        ]
        for col in float_cols:
            if col not in vf:
                op.add_column("ventas_financiadas", sa.Column(col, sa.Float(), nullable=True))

        text_cols = ["solicitud_recibo_notas", "solicitud_recibo_notas_admin"]
        for col in text_cols:
            if col not in vf:
                op.add_column("ventas_financiadas", sa.Column(col, sa.Text(), nullable=True))

        if "scoring_situacion" not in vf:
            op.add_column("ventas_financiadas", sa.Column("scoring_situacion", sa.Integer(), nullable=True))
        if "declaracion_jurada_requerida" not in vf:
            op.add_column("ventas_financiadas", sa.Column("declaracion_jurada_requerida", sa.Boolean(), server_default="false", nullable=True))


def downgrade() -> None:
    pass
