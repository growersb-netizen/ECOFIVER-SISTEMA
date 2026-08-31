from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eco_crm.db")

_is_sqlite = "sqlite" in DATABASE_URL
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:
    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        """WAL: lecturas y escrituras concurrentes sin bloqueo. busy_timeout=30s."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """Agrega columnas nuevas a tablas existentes (SQLite no soporta ALTER TABLE automático)."""
    with engine.connect() as conn:
        from sqlalchemy import text
        migrations = [
            "ALTER TABLE leads ADD COLUMN session_id TEXT",
            "ALTER TABLE leads ADD COLUMN agente_asignado TEXT DEFAULT 'valentina'",
            # VentaContado: flag stock vs fabricación
            "ALTER TABLE ventas_contado ADD COLUMN desde_stock BOOLEAN DEFAULT 0",
            # Entrega: campos para el circuito de confirmación
            "ALTER TABLE entregas ADD COLUMN fecha_original_venta DATETIME",
            "ALTER TABLE entregas ADD COLUMN confirmada BOOLEAN DEFAULT 0",
            "ALTER TABLE entregas ADD COLUMN confirmada_por_id INTEGER",
            "ALTER TABLE entregas ADD COLUMN requiere_fabricacion BOOLEAN DEFAULT 0",
            "ALTER TABLE entregas ADD COLUMN auto_generada BOOLEAN DEFAULT 0",
            # Fábrica: columna notificado (por si la tabla existía sin ella)
            "ALTER TABLE ordenes_fabrica_piscinas ADD COLUMN notificado BOOLEAN DEFAULT 0",
            "ALTER TABLE ordenes_fabrica_modulos ADD COLUMN notificado BOOLEAN DEFAULT 0",
            # Config y ML (nuevas tablas, create_all las crea — pero por si acaso)
            "ALTER TABLE configuracion_sistema ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
            # Ecopost
            "ALTER TABLE contenido_ecopost ADD COLUMN imagen_prompt TEXT DEFAULT ''",
            "ALTER TABLE contenido_ecopost ADD COLUMN copy_hashtags TEXT DEFAULT ''",
            # Leads: seguimiento programado
            "ALTER TABLE leads ADD COLUMN proximo_seguimiento DATETIME",
            # Empleados: token para panel operario sin login
            "ALTER TABLE empleados ADD COLUMN token_operario TEXT",
            # ── Usuarios: agentes IA ──────────────────────────────────────────
            "ALTER TABLE usuarios ADD COLUMN es_agente_ia BOOLEAN DEFAULT 0",
            "ALTER TABLE usuarios ADD COLUMN agente_key TEXT",
            # ── VentaContado: instalación y cobro contraentrega ───────────────
            "ALTER TABLE ventas_contado ADD COLUMN modalidad_cobro TEXT DEFAULT 'PREVIO'",
            "ALTER TABLE ventas_contado ADD COLUMN equipo_instalador_id INTEGER",
            "ALTER TABLE ventas_contado ADD COLUMN tarifa_instalacion REAL",
            "ALTER TABLE ventas_contado ADD COLUMN cobro_estado TEXT",
            "ALTER TABLE ventas_contado ADD COLUMN cobro_monto_real REAL",
            "ALTER TABLE ventas_contado ADD COLUMN cobro_fecha DATETIME",
            "ALTER TABLE ventas_contado ADD COLUMN cobro_notas TEXT DEFAULT ''",
            # ── VentaContado: vendedor para ranking ───────────────────────────
            "ALTER TABLE ventas_contado ADD COLUMN vendedor_id INTEGER",
            # ── Herramientas: campos pañolero ─────────────────────────────────
            "ALTER TABLE herramientas ADD COLUMN descripcion TEXT DEFAULT ''",
            "ALTER TABLE herramientas ADD COLUMN categoria TEXT DEFAULT 'GENERAL'",
            "ALTER TABLE herramientas ADD COLUMN codigo TEXT DEFAULT ''",
            "ALTER TABLE herramientas ADD COLUMN sector_base TEXT DEFAULT 'DEPOSITO'",
            "ALTER TABLE herramientas ADD COLUMN ubicacion_actual TEXT DEFAULT 'Depósito'",
            "ALTER TABLE herramientas ADD COLUMN responsable_actual_id INTEGER",
            # ── PrestamoHerramienta: sector + motivo + usuario CRM ────────────
            "ALTER TABLE prestamos_herramienta ADD COLUMN sector TEXT DEFAULT ''",
            "ALTER TABLE prestamos_herramienta ADD COLUMN motivo_uso TEXT DEFAULT ''",
            "ALTER TABLE prestamos_herramienta ADD COLUMN usuario_crm_id INTEGER",
            # ── Inventario: valorización y fecha de adquisición ───────────────────
            "ALTER TABLE herramientas ADD COLUMN precio_costo REAL",
            "ALTER TABLE herramientas ADD COLUMN fecha_adquisicion DATETIME",
            # ── Insumos: categoría ────────────────────────────────────────────────
            "ALTER TABLE materiales_inventario ADD COLUMN categoria TEXT DEFAULT 'CONSUMIBLE'",
            # ── Leads: UTM tracking + seguimiento multitouch + token entrega ─────
            "ALTER TABLE leads ADD COLUMN utm_source TEXT",
            "ALTER TABLE leads ADD COLUMN utm_medium TEXT",
            "ALTER TABLE leads ADD COLUMN utm_campaign TEXT",
            "ALTER TABLE leads ADD COLUMN intentos_seguimiento INTEGER DEFAULT 0",
            "ALTER TABLE leads ADD COLUMN seguimiento_token TEXT",
            # ── Leads: recirculación de rellamados ─────────────────────────────
            "ALTER TABLE leads ADD COLUMN veces_recirculado INTEGER DEFAULT 0",
            "ALTER TABLE leads ADD COLUMN en_rellamados BOOLEAN DEFAULT 0",
            # ── Consumo por sector (Producción vs Instalación) ─────────────────
            "ALTER TABLE movimientos_material ADD COLUMN destino_area TEXT",
            "ALTER TABLE prestamos_herramienta ADD COLUMN destino_area TEXT",
            # ── Canal Aliados Comerciales ──────────────────────────────────────
            "ALTER TABLE leads ADD COLUMN aliado_codigo TEXT",
            "ALTER TABLE leads ADD COLUMN dni_cliente TEXT",
            "ALTER TABLE leads ADD COLUMN timestamp_comprobante DATETIME",
            "ALTER TABLE leads ADD COLUMN estado_verificacion TEXT DEFAULT 'pendiente'",
            "ALTER TABLE aliados ADD COLUMN pin TEXT",
            "ALTER TABLE borradores_ml ADD COLUMN costo REAL",
            "ALTER TABLE borradores_ml ADD COLUMN cuotas_sin_interes INTEGER DEFAULT 0",
            "ALTER TABLE borradores_ml ADD COLUMN categoria_nombre TEXT DEFAULT ''",
            "ALTER TABLE borradores_ml ADD COLUMN seller_sku TEXT DEFAULT ''",
            # ── Bandeja de entrada — modo de atención ─────────────────────────
            "ALTER TABLE leads ADD COLUMN modo_atencion TEXT DEFAULT 'bot'",
            # ── VentaContado: particularidades módulo ──────────────────────────
            "ALTER TABLE ventas_contado ADD COLUMN con_banio BOOLEAN DEFAULT 0",
            "ALTER TABLE ventas_contado ADD COLUMN con_cocina BOOLEAN DEFAULT 0",
            "ALTER TABLE ventas_contado ADD COLUMN con_puerta_ingreso BOOLEAN DEFAULT 0",
            "ALTER TABLE ventas_contado ADD COLUMN con_ventana_balcon BOOLEAN DEFAULT 0",
            "ALTER TABLE ventas_contado ADD COLUMN sobre_piso TEXT",
            # ── VentaFinanciada: ficha completa para importación de contratos históricos ──
            "ALTER TABLE ventas_financiadas ADD COLUMN numero_solicitud TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN cliente_dni TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN cliente_cuil TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN cliente_domicilio TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN cliente_estado_civil TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN cliente_ocupacion TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN cliente_email TEXT",
            # ── Contrato: snapshot de datos usado para render HTML/PDF ─────────
            "ALTER TABLE contratos ADD COLUMN numero_solicitud TEXT",
            "ALTER TABLE contratos ADD COLUMN datos_json TEXT",
            "ALTER TABLE contratos ADD COLUMN tipo_documento TEXT DEFAULT 'CONTRATO'",
            # ── VentaFinanciada: objetivo real de pago_inicial (saldo de inscripción) ──
            "ALTER TABLE ventas_financiadas ADD COLUMN monto_inscripcion REAL",
            # ── Indexación ICAC mensual (módulos/viviendas) ──
            "ALTER TABLE ventas_financiadas ADD COLUMN cac_pct REAL",
            "ALTER TABLE ventas_financiadas ADD COLUMN ultima_indexacion TIMESTAMP",
            "ALTER TABLE clientes_cobranza_historica ADD COLUMN ultima_indexacion TIMESTAMP",
            # ── Excepción de CAC por cliente (reemplaza al % general al indexar) ──
            "ALTER TABLE ventas_financiadas ADD COLUMN cac_excepcion_pct REAL",
            "ALTER TABLE clientes_cobranza_historica ADD COLUMN cac_excepcion_pct REAL",
            # ── Meta: page_token para leer feed/insights de cada página ──────────
            "ALTER TABLE meta_paginas ADD COLUMN page_token TEXT",
            # ── BorradorML: tipo de precio y modelo para fichas ML ────────────────
            "ALTER TABLE borradores_ml ADD COLUMN tipo_precio TEXT DEFAULT 'completo'",
            "ALTER TABLE borradores_ml ADD COLUMN modelo_nombre TEXT DEFAULT ''",
            # ── BorradorML: precio contado base + flete integrado ─────────────────
            "ALTER TABLE borradores_ml ADD COLUMN precio_contado REAL",
            "ALTER TABLE borradores_ml ADD COLUMN incluir_envio INTEGER DEFAULT 0",
            "ALTER TABLE borradores_ml ADD COLUMN costo_flete REAL",
            # ── Ecopost: token público para URL de imagen sin autenticación ────────
            "ALTER TABLE contenido_ecopost ADD COLUMN public_token TEXT",
            # ── Ecopost: soporte de video, carrusel, programación ─────────────────
            "ALTER TABLE contenido_ecopost ADD COLUMN media_type TEXT DEFAULT 'photo'",
            "ALTER TABLE contenido_ecopost ADD COLUMN video_token TEXT",
            "ALTER TABLE contenido_ecopost ADD COLUMN subtitulos TEXT DEFAULT ''",
            "ALTER TABLE contenido_ecopost ADD COLUMN duracion_seg INTEGER",
            "ALTER TABLE contenido_ecopost ADD COLUMN publish_at DATETIME",
            "ALTER TABLE contenido_ecopost ADD COLUMN redes_publicadas TEXT DEFAULT '{}'",
            "ALTER TABLE contenido_ecopost ADD COLUMN carousel_urls TEXT DEFAULT '[]'",
            # ── Ecopost: publicación programada multi-página + tipo ────────────────
            "ALTER TABLE contenido_ecopost ADD COLUMN publish_pages_json TEXT DEFAULT '[]'",
            "ALTER TABLE contenido_ecopost ADD COLUMN publish_tipo TEXT DEFAULT 'post'",
            # ── Plataforma de Socios Comerciales — cuenta de acceso propia ──────────
            "ALTER TABLE aliados ADD COLUMN email TEXT",
            "ALTER TABLE aliados ADD COLUMN password_hash TEXT",
            "ALTER TABLE aliados ADD COLUMN whatsapp_verificado BOOLEAN DEFAULT 0",
            "ALTER TABLE aliados ADD COLUMN codigo_verificacion TEXT",
            "ALTER TABLE aliados ADD COLUMN codigo_verificacion_expira DATETIME",
            "ALTER TABLE aliados ADD COLUMN intentos_fallidos INTEGER DEFAULT 0",
            "ALTER TABLE aliados ADD COLUMN bloqueado_hasta DATETIME",
            "ALTER TABLE aliados ADD COLUMN doc_monotributo_path TEXT",
            "ALTER TABLE aliados ADD COLUMN doc_dni_path TEXT",
            "ALTER TABLE aliados ADD COLUMN email_verificado BOOLEAN DEFAULT 0",
            "ALTER TABLE aliados ADD COLUMN codigo_verificacion_email TEXT",
            "ALTER TABLE aliados ADD COLUMN codigo_verificacion_email_expira DATETIME",
            "ALTER TABLE aliados ADD COLUMN perfil_completo BOOLEAN DEFAULT 0",
            "ALTER TABLE aliados ADD COLUMN origen_registro TEXT",
            "ALTER TABLE aliados ADD COLUMN comisiones_aceptadas_en DATETIME",
            "ALTER TABLE aliados ADD COLUMN interes_venta TEXT",
            # ── VentaContado: domicilio/email del cliente + flete (canal Aliados) ──
            "ALTER TABLE ventas_contado ADD COLUMN cliente_domicilio TEXT",
            "ALTER TABLE ventas_contado ADD COLUMN cliente_email TEXT",
            # ── VentaFinanciada: flete (canal Aliados) ─────────────────────────
            "ALTER TABLE ventas_financiadas ADD COLUMN distancia_km REAL",
            "ALTER TABLE ventas_financiadas ADD COLUMN flete_calculado REAL",
            "ALTER TABLE materiales_socio ADD COLUMN origen TEXT DEFAULT 'manual'",
            "ALTER TABLE ventas_financiadas ADD COLUMN monto_pagado_inscripcion REAL DEFAULT 0",
            "ALTER TABLE ventas_financiadas ADD COLUMN primera_sena_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN sena_vence_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN recibo_generado_en DATETIME",
            # ── Socios: venta cargada de punta a punta por el socio ─────────────────
            "ALTER TABLE ventas_financiadas ADD COLUMN aliado_codigo TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN scoring_situacion INTEGER",
            "ALTER TABLE ventas_financiadas ADD COLUMN declaracion_jurada_requerida BOOLEAN DEFAULT 0",
            "ALTER TABLE ventas_financiadas ADD COLUMN declaracion_jurada_confirmada_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN inscripcion_pagada_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN contrato_generado_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN link_confirmacion_token TEXT",
            "ALTER TABLE ventas_financiadas ADD COLUMN link_confirmacion_confirmada_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN auditoria_bienvenida_en DATETIME",
            "ALTER TABLE ventas_financiadas ADD COLUMN licitacion_solicitada_en DATETIME",
            "ALTER TABLE ventas_contado ADD COLUMN aliado_codigo TEXT",
            "ALTER TABLE ventas_contado ADD COLUMN confirmacion_48hs_en DATETIME",
            "ALTER TABLE comisiones ADD COLUMN venta_financiada_id INTEGER",
            "ALTER TABLE comisiones ADD COLUMN venta_contado_id INTEGER",
            "ALTER TABLE comisiones ADD COLUMN factura_path TEXT",
            # ── Facebook Automatización (MetaPagina + nueva tabla interacciones) ──
            "ALTER TABLE meta_paginas ADD COLUMN auto_reply_comentarios BOOLEAN DEFAULT 0",
            "ALTER TABLE meta_paginas ADD COLUMN auto_reply_mensajes BOOLEAN DEFAULT 0",
            "ALTER TABLE meta_paginas ADD COLUMN auto_eliminar_negativos BOOLEAN DEFAULT 0",
            "ALTER TABLE meta_paginas ADD COLUMN webhook_subscribed BOOLEAN DEFAULT 0",
            "ALTER TABLE meta_paginas ADD COLUMN numero_whatsapp TEXT DEFAULT '1144498854'",
        ]
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists

        # ── Semilla de continuidad de numeración de solicitudes ───────────────
        # Último número emitido manualmente: 000-13860152 → el próximo debe ser
        # 000-13860153. Idempotente: sólo inserta si la tabla está vacía.
        try:
            existe = conn.execute(text("SELECT COUNT(*) FROM solicitud_contador")).scalar()
            if not existe:
                conn.execute(text(
                    "INSERT INTO solicitud_contador (id, prefijo, ultimo_numero) "
                    "VALUES (1, '000', 13860152)"
                ))
                conn.commit()
        except Exception:
            pass  # la tabla aún no existe (se crea con create_all) o ya está sembrada

        # ── Backfill PublicacionML desde borradores publicados ─────────────────
        # Copia todos los borradores con estado='publicada' e item_id que aún no
        # tengan registro en publicaciones_ml. INSERT OR IGNORE es idempotente.
        # Corre una sola vez al deploy; sin endpoint ni botón en la UI.
        try:
            conn.execute(text("""
                INSERT OR IGNORE INTO publicaciones_ml
                    (item_id, titulo, descripcion, precio, estado_ml)
                SELECT
                    b.item_id,
                    COALESCE(b.titulo, ''),
                    COALESCE(b.descripcion, ''),
                    COALESCE(b.precio, 0),
                    'active'
                FROM borradores_ml b
                WHERE b.item_id IS NOT NULL
                  AND b.estado  = 'publicada'
            """))
            conn.commit()
        except Exception:
            pass  # tabla aún no creada en este arranque; create_all la crea después
