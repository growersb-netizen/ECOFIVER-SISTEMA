from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base
import enum


# ─── ENUMS ────────────────────────────────────────────────────────────────────

class RolEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    ASESOR_APERTURA = "ASESOR_APERTURA"
    SUPERVISOR_CIERRE = "SUPERVISOR_CIERRE"
    COORDINADOR_OPERATIVO = "COORDINADOR_OPERATIVO"
    COBRANZAS = "COBRANZAS"
    FABRICA = "FABRICA"
    ADMINISTRACION = "ADMINISTRACION"


class EstadoLead(str, enum.Enum):
    NUEVO = "NUEVO"
    CONTACTADO = "CONTACTADO"
    CALIFICADO = "CALIFICADO"
    VIDEOLLAMADA_AGENDADA = "VIDEOLLAMADA_AGENDADA"
    CERRADO = "CERRADO"
    PERDIDO = "PERDIDO"


class ProductoInteres(str, enum.Enum):
    MODULO = "MODULO"
    PISCINA = "PISCINA"
    COMBO = "COMBO"


class FormaPago(str, enum.Enum):
    PMI = "PMI"
    DIRECTA_50 = "DIRECTA_50"
    CONTADO = "CONTADO"
    SIN_DEFINIR = "SIN_DEFINIR"


class OrigenLead(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    INSTAGRAM = "INSTAGRAM"
    WEB = "WEB"
    REFERIDO = "REFERIDO"
    IMPORTADO = "IMPORTADO"


class EstadoVideollamada(str, enum.Enum):
    AGENDADA = "AGENDADA"
    REALIZADA = "REALIZADA"
    NO_SE_PRESENTO = "NO_SE_PRESENTO"
    REPROGRAMAR = "REPROGRAMAR"


class ResultadoVideollamada(str, enum.Enum):
    AVANZO = "AVANZO"
    NO_CALIFICO = "NO_CALIFICO"
    CERRO = "CERRO"
    PENDIENTE = "PENDIENTE"


class EstadoAdmision(str, enum.Enum):
    POSTULADO = "POSTULADO"
    EN_REVISION = "EN_REVISION"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"


class EstadoPlan(str, enum.Enum):
    ACTIVO = "ACTIVO"
    ATRASADO = "ATRASADO"
    CANCELADO = "CANCELADO"
    FINALIZADO = "FINALIZADO"


class EstadoVentaContado(str, enum.Enum):
    COORDINADO = "COORDINADO"
    INSTALADO = "INSTALADO"
    COBRADO = "COBRADO"


class EstadoOrdenFabrica(str, enum.Enum):
    EN_ESPERA = "EN_ESPERA"
    EN_PROCESO = "EN_PROCESO"
    TERMINADA = "TERMINADA"
    ENTREGADA = "ENTREGADA"


class EstadoEntrega(str, enum.Enum):
    COORDINADA = "COORDINADA"
    EN_CAMINO = "EN_CAMINO"
    INSTALADA = "INSTALADA"
    CON_PROBLEMA = "CON_PROBLEMA"


class EstadoContrato(str, enum.Enum):
    BORRADOR = "BORRADOR"
    ENVIADO = "ENVIADO"
    FIRMADO = "FIRMADO"


class EstadoReclamo(str, enum.Enum):
    NUEVO = "NUEVO"
    EN_GESTION = "EN_GESTION"
    RESUELTO = "RESUELTO"


class TipoAsistencia(str, enum.Enum):
    PRESENTE = "PRESENTE"
    AUSENTE = "AUSENTE"
    MEDIO_DIA = "MEDIO_DIA"
    FERIADO = "FERIADO"
    ENFERMO = "ENFERMO"


class TipoTarifa(str, enum.Enum):
    POR_HORA = "POR_HORA"
    POR_DIA = "POR_DIA"


class EstadoPedidoMaterial(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    ENVIADO = "ENVIADO"
    RECIBIDO = "RECIBIDO"


class ResultadoGestion(str, enum.Enum):
    PROMETIO_PAGAR = "PROMETIO_PAGAR"
    PAGO = "PAGO"
    NO_CONTESTO = "NO_CONTESTO"
    RECLAMA = "RECLAMA"
    ACUERDO_ESPECIAL = "ACUERDO_ESPECIAL"


class CanalGestion(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    LLAMADA = "LLAMADA"
    PRESENCIAL = "PRESENCIAL"


# ─── TABLAS DE ASOCIACIÓN ─────────────────────────────────────────────────────

from sqlalchemy import Table
usuario_roles = Table(
    "usuario_roles",
    Base.metadata,
    Column("usuario_id", Integer, ForeignKey("usuarios.id")),
    Column("rol", String(50))
)


# ─── MODELOS ──────────────────────────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    roles_json = Column(Text, default="[]")  # JSON list of roles
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ── Agentes IA ──────────────────────────────────────────────────────────────
    es_agente_ia = Column(Boolean, default=False)   # True = cuenta de agente IA
    agente_key   = Column(String(100), nullable=True, unique=True)  # API key propia del agente

    leads_apertura = relationship("Lead", foreign_keys="Lead.asesor_apertura_id", back_populates="asesor_apertura")
    leads_cierre = relationship("Lead", foreign_keys="Lead.supervisor_cierre_id", back_populates="supervisor_cierre")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    telefono = Column(String(30), nullable=False)
    localidad = Column(String(100))
    producto_interes = Column(String(20), default="SIN_DEFINIR")
    modelo_especifico = Column(String(150))
    forma_pago = Column(String(20), default="SIN_DEFINIR")
    # Estados válidos: NUEVO | INTENTADO | CONTACTADO | EN_SEGUIMIENTO | CALIFICADO |
    # COTIZADO | NEGOCIANDO | VIDEOLLAMADA_AGENDADA | ESPERANDO_ADMISION | ADMITIDO |
    # RECHAZADO_ADMISION | CERRADO_GANADO | CERRADO_PERDIDO | INACTIVO
    estado = Column(String(30), default="NUEVO")
    asesor_apertura_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    supervisor_cierre_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    origen = Column(String(20), default="WHATSAPP")
    notas = Column(Text, default="")
    session_id = Column(String(100), nullable=True, index=True)
    agente_asignado = Column(String(50), default="valentina")
    proximo_seguimiento = Column(DateTime(timezone=True), nullable=True)
    # ── UTM tracking (origen de marketing) ───────────────────────────────────
    utm_source   = Column(String(80), nullable=True)   # google, facebook, instagram, wa, referido
    utm_medium   = Column(String(80), nullable=True)   # cpc, organic, direct, social
    utm_campaign = Column(String(150), nullable=True)  # nombre de campaña
    # ── Seguimiento automático (multitouch) ──────────────────────────────────
    intentos_seguimiento = Column(Integer, default=0)  # 0→1→2→3 (FRIO después del 3ro)
    # ── Recirculación de rellamados ───────────────────────────────────────────
    veces_recirculado = Column(Integer, default=0)   # cuántas veces se recirculó un INTENTADO (máx 3)
    en_rellamados = Column(Boolean, default=False)   # True = ya agotó las 3 recirculaciones → base RELLAMADOS
    # ── Canal Aliados Comerciales ─────────────────────────────────────────────
    aliado_codigo = Column(String(20), nullable=True, index=True)   # NULL = lead directo (no de canal)
    dni_cliente = Column(String(20), nullable=True, index=True)     # DNI del cliente (anti-duplicados entre aliados)
    timestamp_comprobante = Column(DateTime(timezone=True), nullable=True)  # desempate en disputas de atribución
    estado_verificacion = Column(String(20), default="pendiente")   # pendiente | verificado | rechazado
    # ── Token para tracking público de entrega ───────────────────────────────
    seguimiento_token = Column(String(40), nullable=True, unique=True)
    # ── Bandeja de entrada — control bot/humano ──────────────────────────────
    modo_atencion = Column(String(20), default="bot")  # bot | humano | pausado
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    asesor_apertura = relationship("Usuario", foreign_keys=[asesor_apertura_id], back_populates="leads_apertura")
    supervisor_cierre = relationship("Usuario", foreign_keys=[supervisor_cierre_id], back_populates="leads_cierre")
    videollamadas = relationship("Videollamada", back_populates="lead")
    mensajes = relationship("MensajeConversacion", back_populates="lead")
    interacciones = relationship("Interaccion", back_populates="lead", order_by="Interaccion.created_at")
    inbox_mensajes = relationship("InboxMensaje", back_populates="lead", order_by="InboxMensaje.created_at")


class Videollamada(Base):
    __tablename__ = "videollamadas"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    cliente_nombre = Column(String(150), nullable=False)
    cliente_telefono = Column(String(30))
    producto_interes = Column(String(20))
    forma_pago = Column(String(20))
    asesor_apertura_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    supervisor_cierre_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_hora = Column(DateTime(timezone=True))
    estado = Column(String(30), default="AGENDADA")
    estado_admision = Column(String(20), nullable=True)
    resultado = Column(String(30), default="PENDIENTE")
    notas = Column(Text, default="")
    comision_asesor_pct = Column(Float, default=0)
    comision_supervisor_pct = Column(Float, default=0)
    recordatorio_enviado = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="videollamadas")
    asesor_apertura = relationship("Usuario", foreign_keys=[asesor_apertura_id])
    supervisor_cierre = relationship("Usuario", foreign_keys=[supervisor_cierre_id])


class VentaContado(Base):
    __tablename__ = "ventas_contado"

    id = Column(Integer, primary_key=True, index=True)
    cliente_nombre = Column(String(150), nullable=False)
    cliente_telefono = Column(String(30))
    cliente_localidad = Column(String(100))
    producto = Column(String(20))
    modelo_especifico = Column(String(150))
    color = Column(String(50), nullable=True)
    superficie_m2 = Column(Float, nullable=True)
    precio_final = Column(Float, default=0)
    forma_pago = Column(String(30), default="CONTADO")
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_instalacion = Column(DateTime(timezone=True), nullable=True)
    rango_horario = Column(String(50), nullable=True)
    distancia_km = Column(Float, nullable=True)
    flete_calculado = Column(Float, nullable=True)
    estado = Column(String(20), default="COORDINADO")
    notas = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    desde_stock = Column(Boolean, default=False)   # True = sale desde stock, no crea OrdenFabrica

    # ── Módulo: particularidades ──────────────────────────────────────────────
    con_banio          = Column(Boolean, default=False)   # +$1.000.000
    con_cocina         = Column(Boolean, default=False)   # +$500.000
    con_puerta_ingreso = Column(Boolean, default=False)
    con_ventana_balcon = Column(Boolean, default=False)
    sobre_piso         = Column(String(10), nullable=True)  # 'PISO' | 'TIERRA'

    # ── Sistema de instalación y cobro ──────────────────────────────────────────
    # PREVIO       = el cliente pagó antes de la entrega (transferencia, MP, etc.)
    # CONTRAENTREGA = se cobra en el domicilio antes de descargar e instalar
    modalidad_cobro         = Column(String(20), default="PREVIO")
    equipo_instalador_id    = Column(Integer, ForeignKey("equipos_instaladores.id"), nullable=True)
    tarifa_instalacion      = Column(Float, nullable=True)   # monto cobrado por instalación
    # Estado del cobro contraentrega
    cobro_estado            = Column(String(20), nullable=True)  # PENDIENTE | COBRADO | PROBLEMA
    cobro_monto_real        = Column(Float, nullable=True)
    cobro_fecha             = Column(DateTime(timezone=True), nullable=True)
    cobro_notas             = Column(Text, default="")

    vendedor           = relationship("Usuario", foreign_keys=[vendedor_id])
    equipo_instalador  = relationship("EquipoInstalador", foreign_keys=[equipo_instalador_id])


class VentaFinanciada(Base):
    __tablename__ = "ventas_financiadas"

    id = Column(Integer, primary_key=True, index=True)
    cliente_nombre = Column(String(150), nullable=False)
    cliente_telefono = Column(String(30))
    cliente_localidad = Column(String(100))
    producto = Column(String(20))
    modelo_especifico = Column(String(150))
    color = Column(String(50), nullable=True)
    superficie_m2 = Column(Float, nullable=True)
    forma_pago = Column(String(20))
    precio_total = Column(Float, default=0)
    anticipo = Column(Float, default=0)
    monto_inscripcion = Column(Float, nullable=True)  # objetivo de pago_inicial (distinto de precio_total)
    cantidad_cuotas = Column(Integer, default=1)
    valor_cuota = Column(Float, default=0)
    fecha_inicio_plan = Column(DateTime(timezone=True), nullable=True)
    fecha_primer_vencimiento = Column(DateTime(timezone=True), nullable=True)
    cuotas_pagas = Column(Integer, default=0)
    asesor_apertura_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    supervisor_cierre_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    estado_plan = Column(String(20), default="ACTIVO")
    estado_admision = Column(String(20), nullable=True)
    notas = Column(Text, default="")
    numero_solicitud = Column(String(30), nullable=True, index=True)
    cliente_dni = Column(String(20), nullable=True)
    cliente_cuil = Column(String(20), nullable=True)
    cliente_domicilio = Column(String(300), nullable=True)
    cliente_estado_civil = Column(String(30), nullable=True)
    cliente_ocupacion = Column(String(100), nullable=True)
    cliente_email = Column(String(150), nullable=True)
    cac_pct = Column(Float, nullable=True)  # último % de ICAC aplicado (solo módulos/viviendas)
    cac_excepcion_pct = Column(Float, nullable=True)  # % propio de este cliente — reemplaza al % general en "Aplicar ICAC"
    ultima_indexacion = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    asesor_apertura = relationship("Usuario", foreign_keys=[asesor_apertura_id])
    supervisor_cierre = relationship("Usuario", foreign_keys=[supervisor_cierre_id])
    pagos = relationship("Pago", back_populates="venta_financiada")
    gestiones_cobranza = relationship("GestionCobranza", back_populates="venta_financiada")


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"))
    monto = Column(Float, nullable=False)
    fecha_pago = Column(DateTime(timezone=True), server_default=func.now())
    notas = Column(Text, default="")

    venta_financiada = relationship("VentaFinanciada", back_populates="pagos")


class GestionCobranza(Base):
    __tablename__ = "gestiones_cobranza"

    id = Column(Integer, primary_key=True, index=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"))
    fecha_contacto = Column(DateTime(timezone=True), server_default=func.now())
    canal = Column(String(20))
    resultado = Column(String(30))
    notas = Column(Text, default="")

    venta_financiada = relationship("VentaFinanciada", back_populates="gestiones_cobranza")


class StockPiscina(Base):
    __tablename__ = "stock_piscinas"

    id = Column(Integer, primary_key=True, index=True)
    modelo = Column(String(150), nullable=False)
    color = Column(String(50), nullable=False)
    cantidad = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class OrdenFabricaPiscina(Base):
    __tablename__ = "ordenes_fabrica_piscinas"

    id = Column(Integer, primary_key=True, index=True)
    venta_contado_id = Column(Integer, ForeignKey("ventas_contado.id"), nullable=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"), nullable=True)
    cliente_nombre = Column(String(150))
    modelo = Column(String(150))
    color = Column(String(50))
    fecha_inicio = Column(DateTime(timezone=True), nullable=True)
    fecha_estimada_fin = Column(DateTime(timezone=True), nullable=True)
    estado = Column(String(20), default="EN_ESPERA")
    notas = Column(Text, default="")
    notificado = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StockPanel(Base):
    __tablename__ = "stock_paneles"

    id = Column(Integer, primary_key=True, index=True)
    tipo_panel = Column(String(100), nullable=False)
    cantidad = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=5)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class OrdenFabricaModulo(Base):
    __tablename__ = "ordenes_fabrica_modulos"

    id = Column(Integer, primary_key=True, index=True)
    venta_contado_id = Column(Integer, ForeignKey("ventas_contado.id"), nullable=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"), nullable=True)
    cliente_nombre = Column(String(150))
    superficie_m2 = Column(Float)
    configuracion = Column(Text, default="")
    fecha_inicio = Column(DateTime(timezone=True), nullable=True)
    fecha_estimada_fin = Column(DateTime(timezone=True), nullable=True)
    estado = Column(String(20), default="EN_ESPERA")
    notas = Column(Text, default="")
    notificado = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PedidoMaterial(Base):
    __tablename__ = "pedidos_materiales"

    id = Column(Integer, primary_key=True, index=True)
    orden_modulo_id = Column(Integer, ForeignKey("ordenes_fabrica_modulos.id"), nullable=True)
    material = Column(String(200), nullable=False)
    cantidad = Column(Float, nullable=False)
    unidad = Column(String(30), default="unidades")
    proveedor = Column(String(150), default="")
    estado = Column(String(20), default="PENDIENTE")
    fecha_pedido = Column(DateTime(timezone=True), server_default=func.now())
    fecha_recepcion = Column(DateTime(timezone=True), nullable=True)
    notas = Column(Text, default="")


class Entrega(Base):
    __tablename__ = "entregas"

    id = Column(Integer, primary_key=True, index=True)
    venta_contado_id = Column(Integer, ForeignKey("ventas_contado.id"), nullable=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"), nullable=True)
    cliente_nombre = Column(String(150))
    cliente_localidad = Column(String(100))
    producto = Column(String(150))
    fecha_instalacion = Column(DateTime(timezone=True))       # fecha de trabajo (puede ser modificada por Renzo)
    fecha_original_venta = Column(DateTime(timezone=True), nullable=True)  # fecha pactada por el vendedor, nunca cambia
    rango_horario = Column(String(50))
    equipo_asignado = Column(String(200), default="")
    estado = Column(String(20), default="COORDINADA")
    notas = Column(Text, default="")
    confirmada = Column(Boolean, default=False)               # True cuando Renzo confirma la fecha con el cliente
    confirmada_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    requiere_fabricacion = Column(Boolean, default=False)     # True si hay OrdenFabrica asociada
    auto_generada = Column(Boolean, default=False)            # True si fue creada automáticamente desde la venta
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    confirmada_por = relationship("Usuario", foreign_keys=[confirmada_por_id])


class PushSubscription(Base):
    """Suscripciones Web Push por usuario/dispositivo."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    usuario = relationship("Usuario", foreign_keys=[usuario_id])


class ConfiguracionSistema(Base):
    """Tabla de configuración del sistema — API keys, precios, datos de empresa, etc."""
    __tablename__ = "configuracion_sistema"

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(100), unique=True, nullable=False, index=True)
    valor = Column(Text, nullable=True)             # encriptado si es_secreto=True
    es_secreto = Column(Boolean, default=False)
    categoria = Column(String(50), default="general")
    estado = Column(String(20), default="sin_configurar")   # activa | inactiva | error | sin_configurar
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    updated_by_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    updated_by = relationship("Usuario", foreign_keys=[updated_by_id])


class PublicacionML(Base):
    """Cache local de publicaciones de MercadoLibre vinculadas al catálogo interno."""
    __tablename__ = "publicaciones_ml"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String(50), unique=True, nullable=False, index=True)   # ID de ML ej. MLA1234567890
    titulo = Column(String(200), default="")
    descripcion = Column(Text, default="")
    precio = Column(Float, default=0)
    estado_ml = Column(String(20), default="active")      # active | paused | closed
    producto = Column(String(20), nullable=True)           # PISCINA | MODULO
    modelo_especifico = Column(String(150), nullable=True)
    renovacion_auto = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class MLCategoriaLinea(Base):
    """
    Cache de la categoría de MercadoLibre resuelta (vía category_predictor) para
    cada línea de producto propia (piscinas, módulos, depósitos, garitas, etc.).
    Evita repetir la predicción en cada publicación y sirve de base para
    autocompletar los atributos requeridos por esa categoría.
    """
    __tablename__ = "ml_categoria_linea"

    id = Column(Integer, primary_key=True, index=True)
    linea = Column(String(40), unique=True, nullable=False, index=True)
    categoria_id = Column(String(20), nullable=False)
    categoria_nombre = Column(String(150), default="")
    atributos_json = Column(Text, default="[]")        # atributos requeridos de la categoría [{id,name,...}]
    titulo_referencia = Column(String(200), default="")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class Reclamo(Base):
    __tablename__ = "reclamos"

    id = Column(Integer, primary_key=True, index=True)
    venta_contado_id = Column(Integer, ForeignKey("ventas_contado.id"), nullable=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"), nullable=True)
    cliente_nombre = Column(String(150))
    cliente_telefono = Column(String(30))
    fecha_reclamo = Column(DateTime(timezone=True), server_default=func.now())
    descripcion = Column(Text)
    estado = Column(String(20), default="NUEVO")
    solucion = Column(Text, default="")
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


class Contrato(Base):
    __tablename__ = "contratos"

    id = Column(Integer, primary_key=True, index=True)
    venta_contado_id = Column(Integer, ForeignKey("ventas_contado.id"), nullable=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"), nullable=True)
    cliente_nombre = Column(String(150))
    tipo_contrato = Column(String(50))
    fecha_generacion = Column(DateTime(timezone=True), server_default=func.now())
    archivo_pdf = Column(String(500), nullable=True)
    estado = Column(String(20), default="BORRADOR")
    notas = Column(Text, default="")
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    numero_solicitud = Column(String(30), nullable=True, index=True)
    datos_json = Column(Text, nullable=True)  # snapshot completo usado para renderizar el documento
    tipo_documento = Column(String(20), default="CONTRATO")  # CONTRATO | RECIBO


class Empleado(Base):
    __tablename__ = "empleados"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    rol_empresa = Column(String(100))
    tipo_tarifa = Column(String(20), default="POR_DIA")
    monto_tarifa = Column(Float, default=0)
    sabado_recargo = Column(Boolean, default=False)
    multiplicador_sabado = Column(Float, default=1.5)
    fecha_ingreso = Column(DateTime(timezone=True), server_default=func.now())
    activo = Column(Boolean, default=True)
    token_operario = Column(String(100), nullable=True, unique=True, index=True)

    asistencias = relationship("Asistencia", back_populates="empleado")
    adelantos = relationship("AdelantoSueldo", back_populates="empleado")


class Asistencia(Base):
    __tablename__ = "asistencias"

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"))
    fecha = Column(DateTime(timezone=True))
    tipo = Column(String(20), default="PRESENTE")
    horas = Column(Float, nullable=True)
    registrado_en = Column(DateTime(timezone=True), server_default=func.now())
    editado_hasta = Column(DateTime(timezone=True), nullable=True)

    empleado = relationship("Empleado", back_populates="asistencias")


class LiquidacionSemanal(Base):
    __tablename__ = "liquidaciones_semanales"

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"))
    fecha_inicio_semana = Column(DateTime(timezone=True))
    fecha_fin_semana = Column(DateTime(timezone=True))
    dias_trabajados = Column(Float, default=0)
    horas_trabajadas = Column(Float, nullable=True)
    monto_total = Column(Float, default=0)
    pagado = Column(Boolean, default=False)
    fecha_pago = Column(DateTime(timezone=True), nullable=True)
    detalle_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    empleado = relationship("Empleado")


class MensajeConversacion(Base):
    __tablename__ = "mensajes_conversacion"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    user_msg = Column(Text, default="")
    agent_reply = Column(Text, default="")
    agent_name = Column(String(50), default="")
    msg_type = Column(String(20), default="text")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="mensajes")


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    titulo = Column(String(200))
    mensaje = Column(Text)
    leida = Column(Boolean, default=False)
    tipo = Column(String(50), default="INFO")
    referencia_id = Column(Integer, nullable=True)
    referencia_tipo = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Interaccion(Base):
    """Historial de interacciones por lead (llamadas, WA, notas, visitas)."""
    __tablename__ = "interacciones"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    # WHATSAPP | LLAMADA | EMAIL | NOTA | VISITA | VENTA
    tipo = Column(String(20), nullable=False)
    # ENVIADO | RESPONDIO | ATENDIO | NO_ATENDIO | NO_CONTESTA | NUMERO_INVALIDO |
    # NO_INTERESA | INTERESADO | VENTA_CONCRETADA
    resultado = Column(String(30), nullable=False)
    notas = Column(Text, default="")
    asesor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="interacciones")
    asesor = relationship("Usuario", foreign_keys=[asesor_id])


class PrecioHistorial(Base):
    """Auditoría de cambios de precios en el catálogo."""
    __tablename__ = "precios_historial"

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(200), nullable=False)      # ej: "modulos.12" o "piscinas.Minimalista Chica"
    valor_anterior = Column(Float, nullable=True)
    valor_nuevo = Column(Float, nullable=False)
    cambiado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cambiado_por = relationship("Usuario", foreign_keys=[cambiado_por_id])


class ContenidoEcopost(Base):
    """Contenido de redes sociales — Ecopost."""
    __tablename__ = "contenido_ecopost"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), default="")
    tipo = Column(String(20), default="flyer")          # flyer | story | carrusel | reel
    producto = Column(String(20), nullable=True)        # PISCINA | MODULO | COMBO
    modelo_especifico = Column(String(150), nullable=True)
    copy_texto = Column(Text, default="")               # cuerpo del copy generado
    copy_hashtags = Column(Text, default="")            # hashtags separados por espacio
    imagen_prompt = Column(Text, default="")            # prompt usado para generar la imagen
    imagen_base64 = Column(Text, nullable=True)         # base64 PNG (preview / descarga)
    imagen_url = Column(String(500), nullable=True)     # URL pública si se sube a Drive/CDN
    estado = Column(String(20), default="borrador")     # borrador | aprobado | publicado | archivado
    notas = Column(Text, default="")
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    aprobado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    creado_por = relationship("Usuario", foreign_keys=[creado_por_id])
    aprobado_por = relationship("Usuario", foreign_keys=[aprobado_por_id])


class SolicitudMelanie(Base):
    """Solicitud de Llamada de Confirmación enviada por el agente Melanie vía Webhook."""
    __tablename__ = "solicitudes_melanie"

    id               = Column(Integer, primary_key=True, index=True)
    # Datos del cliente recibidos de Melanie
    nombre           = Column(String(100), default="")
    apellido         = Column(String(100), default="")
    telefono         = Column(String(30), nullable=False, index=True)
    provincia        = Column(String(100), default="")
    localidad        = Column(String(100), default="")
    producto         = Column(String(80), default="")
    modelo           = Column(String(150), default="")
    plan             = Column(String(100), default="")
    estado_terreno   = Column(String(100), default="")
    fecha_preferida  = Column(String(100), default="")
    horario_preferido= Column(String(100), default="")
    resumen_melanie  = Column(Text, default="")
    historial_chat   = Column(JSON, default=list)       # lista de mensajes
    agente_origen    = Column(String(50), default="melanie")
    datos_extra      = Column(JSON, default=dict)       # extensible sin migración
    # Vínculos internos
    lead_id          = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    # Auditoría
    ip_origen        = Column(String(50), default="")
    estado_procesamiento = Column(String(20), default="recibido")  # recibido | procesado | error
    error_mensaje    = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    lead  = relationship("Lead", foreign_keys=[lead_id])
    tarea = relationship("TareaLlamadaConfirmacion", back_populates="solicitud", uselist=False)


class TareaLlamadaConfirmacion(Base):
    """Tarea de Llamada de Confirmación generada automáticamente al recibir solicitud de Melanie."""
    __tablename__ = "tareas_llamada_confirmacion"

    id                 = Column(Integer, primary_key=True, index=True)
    lead_id            = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    solicitud_id       = Column(Integer, ForeignKey("solicitudes_melanie.id"), nullable=True)
    codigo_validacion  = Column(String(4), unique=True, index=True, nullable=False)
    estado             = Column(String(20), default="PENDIENTE")    # PENDIENTE | EN_CURSO | COMPLETADA | CANCELADA
    prioridad          = Column(String(10), default="NORMAL")        # NORMAL | ALTA | URGENTE
    fecha_preferida    = Column(String(100), default="")
    horario_preferido  = Column(String(100), default="")
    notas_asesor       = Column(Text, default="")
    asesor_id          = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    updated_at         = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    lead      = relationship("Lead", foreign_keys=[lead_id])
    solicitud = relationship("SolicitudMelanie", back_populates="tarea")
    asesor    = relationship("Usuario", foreign_keys=[asesor_id])


class EcopostReferencia(Base):
    """Imágenes de referencia de estilo para guiar la generación de imágenes IA en Ecopost."""
    __tablename__ = "ecopost_referencias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), default="")
    descripcion = Column(Text, default="")
    tipo = Column(String(30), default="estilo")      # estilo | producto | marca | color
    imagen_base64 = Column(Text, nullable=True)
    subido_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subido_por = relationship("Usuario", foreign_keys=[subido_por_id])


# ─── MATERIALES Y COMPRAS ──────────────────────────────────────────────────────

class PedidoMaterialCompras(Base):
    """C-MAT 1 — Pedidos de materiales del equipo."""
    __tablename__ = "pedidos_material"

    id = Column(Integer, primary_key=True, index=True)
    material_descripcion = Column(String(300), nullable=False)
    cantidad = Column(String(100), default="")          # "3 litros", "500 unidades"
    unidad = Column(String(50), default="")
    urgencia = Column(String(20), default="ESTA_SEMANA")  # HOY | ESTA_SEMANA | CUANDO_SE_PUEDA
    para_orden = Column(String(200), default="")         # "módulo de Gino"
    solicitado_por_nombre = Column(String(150), default="")
    solicitado_por_empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=True)
    estado = Column(String(20), default="PENDIENTE")     # PENDIENTE | COMPRADO | RECHAZADO | EN_PEDIDO
    notas_rodrigo = Column(Text, default="")
    precio_compra = Column(Float, nullable=True)
    fecha_compra = Column(DateTime(timezone=True), nullable=True)
    comprado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    solicitado_por = relationship("Empleado", foreign_keys=[solicitado_por_empleado_id])
    comprado_por = relationship("Usuario", foreign_keys=[comprado_por_id])


class MaterialInventario(Base):
    """C-MAT 2 — Inventario de materiales en fábrica."""
    __tablename__ = "materiales_inventario"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    unidad = Column(String(50), default="unidad")        # litros, kg, unidades, metros, m²
    stock_actual = Column(Float, default=0)
    stock_minimo = Column(Float, default=0)
    ubicacion = Column(String(200), default="")          # "galpón principal / estantería A"
    proveedor = Column(String(200), default="")
    precio_referencia = Column(Float, nullable=True)
    categoria = Column(String(50), default="CONSUMIBLE")  # CONSUMIBLE|QUIMICO|FIJACION|ELECTRICO|PINTURA|LIMPIEZA|OTRO
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    movimientos = relationship("MovimientoMaterial", back_populates="material")


class MovimientoMaterial(Base):
    """Entradas y salidas de stock de un material."""
    __tablename__ = "movimientos_material"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materiales_inventario.id"), nullable=False)
    tipo = Column(String(20), nullable=False)             # ENTRADA | SALIDA | AJUSTE
    cantidad = Column(Float, nullable=False)
    motivo = Column(String(300), default="")
    destino_area = Column(String(20), nullable=True)      # PRODUCCION | INSTALACION | OTRO (para qué sector se consumió)
    pedido_id = Column(Integer, ForeignKey("pedidos_material.id"), nullable=True)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    material = relationship("MaterialInventario", back_populates="movimientos")
    creado_por = relationship("Usuario", foreign_keys=[creado_por_id])


class Herramienta(Base):
    """C-MAT 3 — Registro de herramientas."""
    __tablename__ = "herramientas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, default="")
    categoria = Column(String(50), default="GENERAL")    # MANUAL | ELECTRICA | MEDICION | CORTE | ELEVACION | LIMPIEZA | GENERAL
    codigo = Column(String(50), default="")              # código interno / etiqueta
    numero_serie = Column(String(100), default="")
    estado = Column(String(20), default="OK")            # OK | ROTA | EN_REPARACION | BAJA
    sector_base = Column(String(50), default="DEPOSITO")  # sector donde vive permanentemente
    ubicacion_actual = Column(String(200), default="Depósito")
    responsable_actual_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    activa = Column(Boolean, default=True)
    notas = Column(Text, default="")
    precio_costo = Column(Float, nullable=True)                    # valor de adquisición (patrimonio)
    fecha_adquisicion = Column(DateTime(timezone=True), nullable=True)  # fecha de compra/ingreso
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    prestamos = relationship("PrestamoHerramienta", back_populates="herramienta",
                             order_by="PrestamoHerramienta.created_at.desc()")
    responsable_actual = relationship("Usuario", foreign_keys=[responsable_actual_id])


class PrestamoHerramienta(Base):
    """Registro de préstamo/devolución de herramientas."""
    __tablename__ = "prestamos_herramienta"

    id = Column(Integer, primary_key=True, index=True)
    herramienta_id = Column(Integer, ForeignKey("herramientas.id"), nullable=False)
    empleado_nombre = Column(String(150), default="")
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=True)
    usuario_crm_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)  # usuario CRM que retira
    sector = Column(String(50), default="")              # FABRICA | INSTALACION | MANTENIMIENTO | DEPOSITO | OTRO
    destino_area = Column(String(20), nullable=True)     # PRODUCCION | INSTALACION | OTRO (sector de consumo)
    motivo_uso = Column(String(200), default="")         # descripción libre del uso
    destino = Column(String(300), default="")            # "instalación Gino" / dirección de obra
    fecha_salida = Column(DateTime(timezone=True), server_default=func.now())
    fecha_devolucion_esperada = Column(DateTime(timezone=True), nullable=True)
    fecha_devolucion_real = Column(DateTime(timezone=True), nullable=True)
    devuelto = Column(Boolean, default=False)
    notas = Column(Text, default="")
    registrado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    herramienta = relationship("Herramienta", back_populates="prestamos")
    empleado = relationship("Empleado", foreign_keys=[empleado_id])
    usuario_crm = relationship("Usuario", foreign_keys=[usuario_crm_id])
    registrado_por = relationship("Usuario", foreign_keys=[registrado_por_id])


# ─── ÓRDENES DE PRODUCCIÓN ────────────────────────────────────────────────────

class OrdenProduccion(Base):
    """C-OP 1 — Orden formal de fabricación."""
    __tablename__ = "ordenes_produccion"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(20), unique=True, nullable=False, index=True)  # OP-2026-001
    producto = Column(String(20), nullable=False)        # MODULO | PISCINA | COMBO
    modelo = Column(String(150), default="")
    color = Column(String(100), default="")
    superficie_m2 = Column(Float, nullable=True)
    aberturas_json = Column(Text, default="{}")          # JSON: ventanas, puertas
    cliente_nombre = Column(String(150), default="")
    venta_contado_id = Column(Integer, ForeignKey("ventas_contado.id"), nullable=True)
    venta_financiada_id = Column(Integer, ForeignKey("ventas_financiadas.id"), nullable=True)
    prioridad = Column(String(20), default="NORMAL")     # NORMAL | URGENTE
    fecha_compromiso = Column(DateTime(timezone=True), nullable=True)
    operario_ids_json = Column(Text, default="[]")       # JSON list of empleado IDs
    estado = Column(String(30), default="PENDIENTE")     # PENDIENTE | EN_PROCESO | CONTROL_CALIDAD | TERMINADO | DESPACHADO
    etapa_actual = Column(String(30), default="ESTRUCTURA")  # ESTRUCTURA | REVESTIMIENTO | TERMINACIONES | CONTROL
    notas = Column(Text, default="")
    mensaje_operario = Column(Text, default="")          # Mensaje del día de Rodrigo
    created_by_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    etapas = relationship("EtapaOrden", back_populates="orden")
    created_by = relationship("Usuario", foreign_keys=[created_by_id])


class EtapaOrden(Base):
    """Registro de avance por etapa de una orden de producción."""
    __tablename__ = "etapas_orden"

    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes_produccion.id"), nullable=False)
    etapa = Column(String(30), nullable=False)           # ESTRUCTURA | REVESTIMIENTO | TERMINACIONES | CONTROL
    estado = Column(String(20), default="PENDIENTE")     # PENDIENTE | EN_PROCESO | TERMINADO
    notas = Column(Text, default="")
    foto_url = Column(String(500), nullable=True)
    registrado_por_nombre = Column(String(150), default="")
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    orden = relationship("OrdenProduccion", back_populates="etapas")
    empleado = relationship("Empleado", foreign_keys=[empleado_id])


# ─── FLOTA ────────────────────────────────────────────────────────────────────

class Vehiculo(Base):
    """F1 — Registro de vehículos de la empresa."""
    __tablename__ = "vehiculos"

    id = Column(Integer, primary_key=True, index=True)
    patente = Column(String(20), nullable=False, unique=True, index=True)
    tipo = Column(String(30), default="CAMIONETA")       # CAMIONETA | AUTO | UTILITARIO | ACOPLADO
    marca = Column(String(100), default="")
    modelo = Column(String(100), default="")
    anio = Column(Integer, nullable=True)
    color = Column(String(50), default="")
    estado = Column(String(30), default="OPERATIVO")     # OPERATIVO | EN_REPARACION | FUERA_DE_SERVICIO
    vencimiento_vtv = Column(DateTime(timezone=True), nullable=True)
    vencimiento_seguro = Column(DateTime(timezone=True), nullable=True)
    observaciones = Column(Text, default="")
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    asignaciones = relationship("AsignacionVehiculo", back_populates="vehiculo")
    mantenimientos = relationship("MantenimientoVehiculo", back_populates="vehiculo")
    gastos = relationship("GastoFlota", back_populates="vehiculo")
    incidentes = relationship("IncidenteVehiculo", back_populates="vehiculo")


class AsignacionVehiculo(Base):
    """F2 — Asignación diaria de vehículos."""
    __tablename__ = "asignaciones_vehiculo"

    id = Column(Integer, primary_key=True, index=True)
    vehiculo_id = Column(Integer, ForeignKey("vehiculos.id"), nullable=False)
    conductor_nombre = Column(String(150), default="")
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=True)
    destino = Column(String(300), default="")
    trabajo = Column(String(300), default="")
    fecha = Column(DateTime(timezone=True), nullable=False)
    horario_salida_estimado = Column(String(10), default="")   # "08:00"
    horario_regreso_estimado = Column(String(10), default="")  # "17:00"
    km_salida = Column(Float, nullable=True)
    km_regreso = Column(Float, nullable=True)
    estado = Column(String(20), default="PROGRAMADA")   # PROGRAMADA | EN_VIAJE | COMPLETADA | CANCELADA
    notas = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehiculo = relationship("Vehiculo", back_populates="asignaciones")
    empleado = relationship("Empleado", foreign_keys=[empleado_id])


class MantenimientoVehiculo(Base):
    """F4 — Mantenimiento preventivo y reparaciones."""
    __tablename__ = "mantenimientos_vehiculo"

    id = Column(Integer, primary_key=True, index=True)
    vehiculo_id = Column(Integer, ForeignKey("vehiculos.id"), nullable=False)
    tipo = Column(String(20), default="PREVENTIVO")      # PREVENTIVO | REPARACION
    descripcion = Column(Text, default="")
    fecha = Column(DateTime(timezone=True), nullable=True)
    km_al_momento = Column(Float, nullable=True)
    costo = Column(Float, nullable=True)
    taller = Column(String(200), default="")
    proximo_service_fecha = Column(DateTime(timezone=True), nullable=True)
    proximo_service_km = Column(Float, nullable=True)
    estado = Column(String(20), default="PENDIENTE")     # PENDIENTE | EN_TALLER | RESUELTO
    notas = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehiculo = relationship("Vehiculo", back_populates="mantenimientos")


class GastoFlota(Base):
    """F5 — Gastos de flota (nafta, peajes, reparaciones, etc.)."""
    __tablename__ = "gastos_flota"

    id = Column(Integer, primary_key=True, index=True)
    vehiculo_id = Column(Integer, ForeignKey("vehiculos.id"), nullable=False)
    tipo = Column(String(30), default="NAFTA")           # NAFTA | PEAJE | ESTACIONAMIENTO | REPARACION | SEGURO | VTV | MULTA | OTRO
    monto = Column(Float, nullable=False)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    descripcion = Column(String(300), default="")
    quien_pago = Column(String(150), default="")
    registrado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehiculo = relationship("Vehiculo", back_populates="gastos")
    registrado_por = relationship("Usuario", foreign_keys=[registrado_por_id])


class IncidenteVehiculo(Base):
    """F6 — Incidentes y daños."""
    __tablename__ = "incidentes_vehiculo"

    id = Column(Integer, primary_key=True, index=True)
    vehiculo_id = Column(Integer, ForeignKey("vehiculos.id"), nullable=False)
    fecha = Column(DateTime(timezone=True), nullable=True)
    lugar = Column(String(200), default="")
    descripcion = Column(Text, default="")
    conductor_nombre = Column(String(150), default="")
    foto_urls_json = Column(Text, default="[]")
    seguro_involucrado = Column(Boolean, default=False)
    numero_siniestro = Column(String(100), default="")
    estado_reclamo = Column(String(50), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehiculo = relationship("Vehiculo", back_populates="incidentes")


# ─── PERSONAL — ADELANTOS ─────────────────────────────────────────────────────

class AdelantoSueldo(Base):
    """B4 — Adelantos de sueldo a operarios."""
    __tablename__ = "adelantos_sueldo"

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    monto = Column(Float, nullable=False)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    motivo = Column(String(300), default="")
    descontado = Column(Boolean, default=False)          # True cuando se descuenta de la liquidación
    liquidacion_id = Column(Integer, ForeignKey("liquidaciones_semanales.id"), nullable=True)
    registrado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    empleado = relationship("Empleado", back_populates="adelantos")
    registrado_por = relationship("Usuario", foreign_keys=[registrado_por_id])


# ─── GASTOS OPERATIVOS ────────────────────────────────────────────────────────

class Gasto(Base):
    """Registro de gastos operativos — fábrica, instalaciones, ventas, admin."""
    __tablename__ = "gastos"

    id = Column(Integer, primary_key=True, index=True)

    # Qué y cuánto
    fecha = Column(Date, nullable=False)
    monto = Column(Float, nullable=False)
    descripcion = Column(Text, nullable=False)

    # Clasificación
    # MATERIALES | COMBUSTIBLE | COMIDA | HERRAMIENTAS | FLETE | INSTALACION
    # PRODUCCION | ADMINISTRATIVO | VEHICULO | SUELDO | OTRO
    categoria = Column(String(50), nullable=False, default="OTRO")
    # FABRICA | OPERACIONES | VENTAS | ADMINISTRACION | GENERAL
    sector = Column(String(50), nullable=False, default="GENERAL")

    proveedor = Column(String(150), default="")
    imagen_url = Column(String(500), nullable=True)   # path relativo en /uploads/gastos/
    notas = Column(Text, default="")

    # Vinculación automática al trabajo/pedido correspondiente
    cliente_nombre = Column(String(150), default="")   # referencia rápida
    venta_contado_id      = Column(Integer, ForeignKey("ventas_contado.id"),          nullable=True)
    venta_financiada_id   = Column(Integer, ForeignKey("ventas_financiadas.id"),      nullable=True)
    entrega_id            = Column(Integer, ForeignKey("entregas.id"),                nullable=True)
    orden_piscina_id      = Column(Integer, ForeignKey("ordenes_fabrica_piscinas.id"),nullable=True)
    orden_modulo_id       = Column(Integer, ForeignKey("ordenes_fabrica_modulos.id"), nullable=True)

    # Meta
    registrado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    # REGISTRADO | REVISADO
    estado  = Column(String(20), default="REGISTRADO")
    # MANUAL | ZAPIA | APP
    origen  = Column(String(20), default="MANUAL")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    registrado_por    = relationship("Usuario",              foreign_keys=[registrado_por_id])
    venta_contado     = relationship("VentaContado",         foreign_keys=[venta_contado_id])
    venta_financiada  = relationship("VentaFinanciada",      foreign_keys=[venta_financiada_id])
    entrega           = relationship("Entrega",              foreign_keys=[entrega_id])
    orden_piscina     = relationship("OrdenFabricaPiscina",  foreign_keys=[orden_piscina_id])
    orden_modulo      = relationship("OrdenFabricaModulo",   foreign_keys=[orden_modulo_id])


# ─── ENVÍOS VÍA CARGO ─────────────────────────────────────────────────────────

class EnvioViaCargo(Base):
    """
    Envíos de productos terminados por Vía Cargo u otras empresas de transporte terrestre.
    Cubre la venta remota de módulos (estilo IKEA) y piscinas portables sin instalación propia.
    """
    __tablename__ = "envios_via_cargo"

    id = Column(Integer, primary_key=True, index=True)

    # ── Producto ──────────────────────────────────────────────────────────────
    producto            = Column(String(20),  nullable=False)   # PISCINA | MODULO
    modelo_especifico   = Column(String(150), default="")
    color               = Column(String(50),  default="")
    cantidad            = Column(Integer,     default=1)
    desde_stock         = Column(Boolean,     default=False)    # sale de stock existente

    # ── Cliente / destino ─────────────────────────────────────────────────────
    cliente_nombre      = Column(String(150), nullable=False)
    cliente_telefono    = Column(String(30),  default="")
    cliente_localidad   = Column(String(150), default="")
    provincia           = Column(String(100), default="")
    # Sucursal Vía Cargo destino (ej: "Via Cargo Córdoba - Av. Colón 123")
    sucursal_cargo      = Column(String(300), default="")

    # ── Precios ───────────────────────────────────────────────────────────────
    precio_producto     = Column(Float, default=0)
    costo_flete         = Column(Float, nullable=True)          # estimado o acordado
    total               = Column(Float, default=0)
    forma_pago          = Column(String(30),  default="TRANSFERENCIA")

    # ── Venta y vendedor asociados ────────────────────────────────────────────
    venta_contado_id    = Column(Integer, ForeignKey("ventas_contado.id"),  nullable=True)
    vendedor_id         = Column(Integer, ForeignKey("usuarios.id"),        nullable=True)

    # ── Tracking Vía Cargo ────────────────────────────────────────────────────
    # Estados: PENDIENTE | EMPACADO | DESPACHADO | EN_TRANSITO | ENTREGADO | PROBLEMA
    estado              = Column(String(20), default="PENDIENTE")
    numero_remito       = Column(String(100), default="")       # Nro de remito / guía
    empresa_transporte  = Column(String(100), default="VIA_CARGO")
    fecha_despacho      = Column(DateTime(timezone=True), nullable=True)
    fecha_entrega_est   = Column(DateTime(timezone=True), nullable=True)
    fecha_entrega_real  = Column(DateTime(timezone=True), nullable=True)

    notas               = Column(Text, default="")
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    venta_contado   = relationship("VentaContado", foreign_keys=[venta_contado_id])
    vendedor        = relationship("Usuario",       foreign_keys=[vendedor_id])


# ─── CONTROL CENTER DE AGENTES ────────────────────────────────────────────────

class ComandoAgente(Base):
    """
    Registro de instrucciones enviadas al orquestador multiagente.
    Permite trazabilidad completa: quién ordenó qué, cuándo y con qué resultado.
    """
    __tablename__ = "comandos_agente"

    id              = Column(Integer, primary_key=True, index=True)

    # Metadata de la orden
    tipo            = Column(String(20), default="LIBRE")   # LIBRE | RAPIDO | CEO
    area            = Column(String(30), default="GENERAL") # VENTAS | COBRANZAS | FABRICA | LOGISTICA | ADMIN | MARKETING
    prioridad       = Column(String(10), default="NORMAL")  # URGENTE | NORMAL | BAJA
    titulo          = Column(String(200), default="")       # Resumen corto (auto o manual)

    # Contenido
    instruccion     = Column(Text, nullable=False)
    contexto        = Column(JSON, default={})              # Datos extras para el agente

    # Ejecución
    agente_destino  = Column(String(100), default="")       # Agente o "ORQUESTADOR"
    estado          = Column(String(20), default="PENDIENTE") # PENDIENTE | ENVIADO | PROCESANDO | COMPLETADO | ERROR
    respuesta       = Column(Text, default="")
    error_detalle   = Column(Text, default="")
    http_status     = Column(Integer, nullable=True)        # HTTP status de la respuesta del orquestador

    # Auditoría
    enviado_por_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    enviado_por     = relationship("Usuario", foreign_keys=[enviado_por_id])


# ─── EQUIPOS INSTALADORES ────────────────────────────────────────────────────

class EquipoInstalador(Base):
    """
    Equipos o personas que realizan instalaciones en domicilio.
    Puede ser el propietario (Rodrigo) o equipos externos.
    """
    __tablename__ = "equipos_instaladores"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(100), nullable=False)   # "Rodrigo", "Equipo Norte", etc.
    tipo            = Column(String(20), default="PROPIO")  # PROPIO | EXTERNO
    responsable     = Column(String(100), default="")       # nombre del jefe de equipo
    integrantes     = Column(Text, default="")              # nombres separados por coma
    telefono        = Column(String(30), default="")
    zonas_cobertura = Column(Text, default="")              # provincias / zonas que cubre
    activo          = Column(Boolean, default=True)
    notas           = Column(Text, default="")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


# ─── TARIFAS DE INSTALACIÓN ──────────────────────────────────────────────────

class TarifaInstalacion(Base):
    """
    Tarifa de instalación por tipo de producto y modelo.
    Si modelo_especifico está vacío aplica a todos los modelos de ese producto.
    """
    __tablename__ = "tarifas_instalacion"

    id                  = Column(Integer, primary_key=True, index=True)
    producto            = Column(String(20), nullable=False)    # PISCINA | MODULO
    modelo_especifico   = Column(String(150), default="")       # "" = aplica a todos
    nombre_display      = Column(String(200), default="")       # ej: "Piscina Miniportante"
    tarifa              = Column(Float, default=0)              # ARS base de instalación
    tarifa_km_extra     = Column(Float, default=0)             # ARS por km adicional
    km_incluidos        = Column(Integer, default=0)            # km base incluidos en tarifa
    incluye_materiales  = Column(Boolean, default=False)        # si incluye materiales menores
    descripcion         = Column(Text, default="")
    activa              = Column(Boolean, default=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())


# ─── BANDEJA DE ENTRADA WHATSAPP ──────────────────────────────────────────────

class InboxMensaje(Base):
    """
    Historial individual de mensajes de la bandeja de entrada.
    Permite ver y responder conversaciones WhatsApp desde el CRM,
    y cambiar entre modo bot (agentes IA) y modo humano (admin).
    """
    __tablename__ = "inbox_mensajes"

    id              = Column(Integer, primary_key=True, index=True)
    lead_id         = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    canal           = Column(String(20), default="whatsapp")   # whatsapp | telegram
    phone           = Column(String(30), index=True)           # número E.164 sin +
    nombre_contacto = Column(String(150), default="")          # nombre del contacto
    direccion       = Column(String(5), nullable=False)        # IN | OUT
    contenido       = Column(Text, nullable=False)
    remitente       = Column(String(100), default="")          # "cliente" | agente_name | "admin"
    leido           = Column(Boolean, default=False)
    wa_message_id   = Column(String(200), nullable=True)       # wamid de Meta
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="inbox_mensajes")


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO ALIADOS COMERCIALES
# Canal de venta por referidos. No reemplaza nada del CRM: agrega tablas propias
# y se vincula a leads mediante Lead.aliado_codigo.
# ═══════════════════════════════════════════════════════════════════════════════

class Aliado(Base):
    """Aliado comercial (referidor). El código es la clave de negocio (ej. AL-004)."""
    __tablename__ = "aliados"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, nullable=False, index=True)   # AL-004
    nombre = Column(String(150), nullable=False)
    dni = Column(String(20), default="")
    cuit_monotributo = Column(String(30), default="")
    telefono = Column(String(30), default="")            # WhatsApp de contacto
    cbu_alias = Column(String(120), default="")          # para pago de comisiones
    zona = Column(String(120), default="")               # localidad / partido PBA
    # postulante | en_evaluacion | activo | inactivo | suspendido | rechazado
    estado = Column(String(20), default="postulante", index=True)
    fecha_alta = Column(DateTime(timezone=True), server_default=func.now())
    contrato_firmado = Column(Boolean, default=False)    # bloquea operativa si es False
    pin = Column(String(12), nullable=True)              # PIN para el portal de solo lectura del aliado
    notas = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Comision(Base):
    """Comisión devengada por un aliado sobre una solicitud emitida."""
    __tablename__ = "comisiones"

    id = Column(Integer, primary_key=True, index=True)
    aliado_codigo = Column(String(20), ForeignKey("aliados.codigo"), nullable=False, index=True)
    solicitud_numero = Column(String(30), default="", index=True)
    tipo = Column(String(20), default="entrada")          # entrada | cuota_3 | contado
    monto = Column(Float, default=0)                      # calculado, no editable a mano
    estado = Column(String(20), default="pendiente", index=True)  # pendiente | liquidada
    fecha_liquidacion = Column(DateTime(timezone=True), nullable=True)
    # Trazabilidad de excepciones: si se editó el monto a mano, queda registrado
    ajuste_manual = Column(Boolean, default=False)
    ajuste_motivo = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditoriaPaquete(Base):
    """
    Log de cada paquete 🟡 enviado por Franco a Telegram.
    Existe independientemente de los permisos de escritura sobre contratos:
    protege ante reclamos de 'mandé todo a tiempo y no me contestaron'.
    """
    __tablename__ = "auditoria_paquetes"

    id = Column(Integer, primary_key=True, index=True)
    aliado_codigo = Column(String(20), index=True)
    contenido = Column(Text, default="")                  # snapshot del paquete enviado
    timestamp_envio = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    # OK | FALTA | RECHAZO | sin_respuesta
    resultado = Column(String(20), default="sin_respuesta", index=True)
    timestamp_resultado = Column(DateTime(timezone=True), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SolicitudContador(Base):
    """
    Contador de numeración de solicitudes. Fila única.
    Semilla obligatoria: ultimo_numero = 13860152 → el próximo emitido es 000-13860153.
    El número se asigna sólo por código al confirmar un pago (no editable a mano).
    """
    __tablename__ = "solicitud_contador"

    id = Column(Integer, primary_key=True)
    prefijo = Column(String(10), default="000")
    ultimo_numero = Column(Integer, default=13860152)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class BorradorML(Base):
    """
    Borrador de publicación para MercadoLibre (cola de carga unificada).
    Origen: manual | masiva | catalogo. Se publica en lote vía API a ML.
    """
    __tablename__ = "borradores_ml"

    id = Column(Integer, primary_key=True, index=True)
    origen = Column(String(20), default="manual")          # manual | masiva | catalogo
    titulo = Column(String(200), default="")               # máx 60 en ML
    descripcion = Column(Text, default="")
    categoria = Column(String(20), default="")             # MLA... (si vacío, se infiere del producto)
    producto = Column(String(20), nullable=True)           # PISCINA | MODULO | COMBO
    precio = Column(Float, default=0)
    costo = Column(Float, nullable=True)                    # costo del producto (para calcular ganancia)
    cantidad = Column(Integer, default=1)
    condicion = Column(String(20), default="new")          # new | used
    listing_type = Column(String(30), default="gold_special")   # Clásica por defecto
    cuotas_sin_interes = Column(Integer, default=0)        # 0 = 1 pago; 3/6/9/12 = cuotas sin interés (Premium)
    fotos_json = Column(Text, default="[]")                # lista de URLs
    atributos_json = Column(Text, default="[]")            # atributos ML [{id,value_name}]
    # ── Competitividad ──
    precio_referencia = Column(Float, nullable=True)       # referencia manual del más barato
    precio_competencia = Column(Float, nullable=True)      # auto (buy-box de catálogo), si hay
    # ── Estado de publicación ──
    estado = Column(String(20), default="borrador")        # borrador | publicando | publicada | error
    item_id = Column(String(50), nullable=True)            # MLA... una vez publicada
    permalink = Column(String(300), nullable=True)
    error_msg = Column(Text, default="")
    variante_de = Column(Integer, nullable=True)           # id del borrador base si es variante
    created_by_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── COBRANZA HISTÓRICA (CONSTRUSOL) ───────────────────────────────────────────
# Cartera de cobranza totalmente independiente de VentaFinanciada/ventas_financiadas
# (EcoFiver). No comparte tablas, contadores ni queries con la cobranza de
# EcoFiver — separación exigida explícitamente por el negocio: "no se tocan ni
# se cruzan nunca los datos". "empresa" queda fijo en "construsol" (única por
# ahora); "linea" separa las dos carteras de Construsol (viviendas | piscinas).

class ClienteCobranzaHistorica(Base):
    __tablename__ = "clientes_cobranza_historica"

    id = Column(Integer, primary_key=True, index=True)
    empresa = Column(String(30), default="construsol", index=True)
    linea = Column(String(30), nullable=False, index=True)   # "viviendas" | "piscinas"
    proyecto = Column(String(100), nullable=True)             # ej. "Eco Zárate" (desarrollo específico, opcional)
    apellido_nombre = Column(String(150), nullable=False)
    telefono = Column(String(30), default="")
    dni = Column(String(20), nullable=True)
    metros_o_modelo = Column(String(100), nullable=True)     # metros del lote (viviendas) o modelo (piletas)
    cantidad_cuotas = Column(Integer, nullable=True)
    anticipo = Column(Float, nullable=True)
    precio_total = Column(Float, nullable=True)
    cuota_actual = Column(Float, default=0)                  # valor de la cuota vigente este mes (con CAC aplicado)
    cac_pct = Column(Float, nullable=True)                   # último coeficiente de ajuste aplicado (%)
    cac_excepcion_pct = Column(Float, nullable=True)         # % propio de este cliente — reemplaza al % general en "Aplicar ICAC"
    ultima_indexacion = Column(DateTime(timezone=True), nullable=True)
    estado_plan = Column(String(20), default="ACTIVO")       # ACTIVO | ATRASADO | FINALIZADO | CANCELADO
    notas = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    pagos = relationship("PagoCobranzaHistorica", back_populates="cliente")


class PagoCobranzaHistorica(Base):
    __tablename__ = "pagos_cobranza_historica"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes_cobranza_historica.id"), nullable=False, index=True)
    monto = Column(Float, nullable=False)
    mes_correspondiente = Column(String(20), nullable=True)  # ej. "2026-08" — a qué mes de cuota corresponde
    fecha_pago = Column(DateTime(timezone=True), server_default=func.now())
    notas = Column(Text, default="")

    cliente = relationship("ClienteCobranzaHistorica", back_populates="pagos")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class HistorialEdicionCobranza(Base):
    """
    Registro de auditoría campo por campo para ediciones manuales de
    operaciones de cobranza (EcoFiver y Construsol) — quién cambió qué,
    cuándo, y de qué valor a qué valor. Nunca se edita/borra este registro.
    """
    __tablename__ = "historial_edicion_cobranza"

    id = Column(Integer, primary_key=True, index=True)
    tabla_origen = Column(String(40), nullable=False, index=True)  # "ventas_financiadas" | "clientes_cobranza_historica"
    registro_id = Column(Integer, nullable=False, index=True)
    campo = Column(String(60), nullable=False)
    valor_anterior = Column(Text, nullable=True)
    valor_nuevo = Column(Text, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    usuario_nombre = Column(String(100), nullable=True)  # snapshot del nombre al momento del cambio
    motivo = Column(Text, default="")
    es_economico = Column(Boolean, default=False)  # afecta monto/plan — requirió confirmación explícita
    created_at = Column(DateTime(timezone=True), server_default=func.now())
