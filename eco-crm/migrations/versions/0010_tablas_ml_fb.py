"""tablas ML y Facebook sin cobertura de migración

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-13
"""
from alembic import op
from sqlalchemy import text

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS ml_categoria_linea (
            id               SERIAL PRIMARY KEY,
            linea            VARCHAR(40)  UNIQUE NOT NULL,
            categoria_id     VARCHAR(20)  NOT NULL,
            categoria_nombre VARCHAR(150) DEFAULT '',
            atributos_json   TEXT         DEFAULT '[]',
            titulo_referencia VARCHAR(200) DEFAULT '',
            updated_at       TIMESTAMPTZ  DEFAULT now()
        )
    """))

    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS borradores_ml (
            id                  SERIAL PRIMARY KEY,
            origen              VARCHAR(20)  DEFAULT 'manual',
            titulo              VARCHAR(200) DEFAULT '',
            descripcion         TEXT         DEFAULT '',
            categoria           VARCHAR(20)  DEFAULT '',
            categoria_nombre    VARCHAR(150) DEFAULT '',
            seller_sku          VARCHAR(80)  DEFAULT '',
            producto            VARCHAR(20),
            precio              FLOAT        DEFAULT 0,
            costo               FLOAT,
            cantidad            INTEGER      DEFAULT 1,
            condicion           VARCHAR(20)  DEFAULT 'new',
            listing_type        VARCHAR(30)  DEFAULT 'gold_special',
            cuotas_sin_interes  INTEGER      DEFAULT 0,
            precio_contado      FLOAT,
            incluir_envio       BOOLEAN      DEFAULT false,
            costo_flete         FLOAT,
            fotos_json          TEXT         DEFAULT '[]',
            atributos_json      TEXT         DEFAULT '[]',
            precio_referencia   FLOAT,
            precio_competencia  FLOAT,
            estado              VARCHAR(20)  DEFAULT 'borrador',
            item_id             VARCHAR(50),
            permalink           VARCHAR(300),
            error_msg           TEXT         DEFAULT '',
            variante_de         INTEGER,
            tipo_precio         VARCHAR(20)  DEFAULT 'completo',
            modelo_nombre       VARCHAR(150) DEFAULT '',
            created_by_id       INTEGER,
            created_at          TIMESTAMPTZ  DEFAULT now()
        )
    """))

    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS facebook_interacciones (
            id                SERIAL PRIMARY KEY,
            page_id           VARCHAR(50)  NOT NULL,
            tipo              VARCHAR(30)  NOT NULL,
            post_id           VARCHAR(150),
            objeto_id         VARCHAR(150),
            usuario_nombre    VARCHAR(200),
            usuario_id        VARCHAR(50),
            contenido         TEXT,
            sentimiento       VARCHAR(20)  DEFAULT 'neutro',
            accion            VARCHAR(30)  DEFAULT 'pendiente',
            respuesta_enviada TEXT,
            created_at        TIMESTAMPTZ  DEFAULT now()
        )
    """))

    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS foto_ml (
            id            SERIAL PRIMARY KEY,
            nombre        VARCHAR(200),
            url           TEXT         NOT NULL,
            tipo_producto VARCHAR(50),
            modelo        VARCHAR(100),
            tag           VARCHAR(200),
            orden         INTEGER      DEFAULT 0,
            created_at    TIMESTAMPTZ  DEFAULT now()
        )
    """))

    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS set_fotos_ml (
            id            SERIAL PRIMARY KEY,
            nombre        VARCHAR(200) NOT NULL,
            tipo_producto VARCHAR(50),
            modelo        VARCHAR(100),
            foto_ids_json TEXT         DEFAULT '[]',
            created_at    TIMESTAMPTZ  DEFAULT now(),
            updated_at    TIMESTAMPTZ  DEFAULT now()
        )
    """))

    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS respuestas_auto_ml (
            id              SERIAL PRIMARY KEY,
            question_id     VARCHAR(50),
            item_id         VARCHAR(50),
            item_titulo     VARCHAR(500),
            comprador_nick  VARCHAR(200),
            pregunta_texto  TEXT         NOT NULL,
            respuesta_texto TEXT         NOT NULL,
            respondida_por  VARCHAR(20)  DEFAULT 'auto',
            created_at      TIMESTAMPTZ  DEFAULT now()
        )
    """))


def downgrade() -> None:
    pass
