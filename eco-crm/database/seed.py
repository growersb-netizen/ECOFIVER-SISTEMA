"""
Datos de prueba iniciales para el sistema.
Se ejecuta solo si la base de datos está vacía.
"""
import json
from datetime import datetime, timedelta

from passlib.context import CryptContext

from database.database import SessionLocal
from database.models import (
    Usuario, Lead, VentaFinanciada, Empleado, Asistencia,
    OrdenFabricaPiscina, StockPiscina, StockPanel, ConfiguracionSistema
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_pw(pw: str) -> str:
    return pwd_context.hash(pw)


def seed_database():
    db = SessionLocal()
    try:
        if db.query(Usuario).count() > 0:
            return  # Ya tiene datos

        print("[SEED] Iniciando seed de base de datos...")

        # ─── USUARIOS ─────────────────────────────────────────────────────────
        usuarios = [
            {
                "nombre": "Rodrigo",
                "email": "rodrigo@ecomodulos.com",
                "password": "admin123",
                "roles": ["ADMIN"]
            },
            {
                "nombre": "Stefania",
                "email": "stefania@ecomodulos.com",
                "password": "eco123",
                "roles": ["ASESOR_APERTURA", "SUPERVISOR_CIERRE"]
            },
            {
                "nombre": "Santiago",
                "email": "santiago@ecomodulos.com",
                "password": "eco123",
                "roles": ["ASESOR_APERTURA", "SUPERVISOR_CIERRE"]
            },
            {
                "nombre": "Daniel",
                "email": "daniel@ecomodulos.com",
                "password": "eco123",
                "roles": ["ASESOR_APERTURA", "SUPERVISOR_CIERRE"]
            },
            {
                "nombre": "Hernán",
                "email": "hernan@ecomodulos.com",
                "password": "eco123",
                "roles": ["ASESOR_APERTURA", "SUPERVISOR_CIERRE"]
            },
            {
                "nombre": "Renzo",
                "email": "renzo@ecomodulos.com",
                "password": "eco123",
                "roles": ["COORDINADOR_OPERATIVO"]
            },
            {
                "nombre": "Cobrador",
                "email": "cobrador@ecomodulos.com",
                "password": "eco123",
                "roles": ["COBRANZAS"]
            },
            {
                "nombre": "Fábrica",
                "email": "fabrica@ecomodulos.com",
                "password": "eco123",
                "roles": ["FABRICA", "ADMINISTRACION"]
            },
        ]

        created_users = {}
        for u_data in usuarios:
            user = Usuario(
                nombre=u_data["nombre"],
                email=u_data["email"],
                password_hash=hash_pw(u_data["password"]),
                roles_json=json.dumps(u_data["roles"]),
                activo=True,
            )
            db.add(user)
            db.flush()
            created_users[u_data["nombre"]] = user

        # ─── LEADS DE PRUEBA ──────────────────────────────────────────────────
        leads_data = [
            {
                "nombre": "Carlos Martínez",
                "telefono": "1145678901",
                "localidad": "Pilar, Buenos Aires",
                "producto_interes": "PISCINA",
                "modelo_especifico": "Minimalista Mediana",
                "forma_pago": "PMI",
                "estado": "CALIFICADO",
                "origen": "INSTAGRAM",
                "asesor": "Stefania",
                "notas": "Interesado en instalación para verano. Tiene espacio de 8x4m.",
            },
            {
                "nombre": "Ana Laura Gómez",
                "telefono": "1167890123",
                "localidad": "Tigre, Buenos Aires",
                "producto_interes": "MODULO",
                "modelo_especifico": "Módulo 36m²",
                "forma_pago": "PMI",
                "estado": "VIDEOLLAMADA_AGENDADA",
                "origen": "WHATSAPP",
                "asesor": "Santiago",
                "notas": "Consulta para casa en terreno propio. Presupuesto aprobado.",
            },
            {
                "nombre": "Roberto Silva",
                "telefono": "1123456789",
                "localidad": "Zárate, Buenos Aires",
                "producto_interes": "COMBO",
                "modelo_especifico": "Arco Romano Grande Recto",
                "forma_pago": "CONTADO",
                "estado": "CONTACTADO",
                "origen": "REFERIDO",
                "asesor": "Daniel",
                "notas": "Viene referido por un cliente de la zona. Quiere combo módulo+piscina.",
            },
        ]

        for l_data in leads_data:
            asesor = created_users.get(l_data["asesor"])
            lead = Lead(
                nombre=l_data["nombre"],
                telefono=l_data["telefono"],
                localidad=l_data["localidad"],
                producto_interes=l_data["producto_interes"],
                modelo_especifico=l_data["modelo_especifico"],
                forma_pago=l_data["forma_pago"],
                estado=l_data["estado"],
                origen=l_data["origen"],
                asesor_apertura_id=asesor.id if asesor else None,
                notas=l_data["notas"],
            )
            db.add(lead)

        # ─── VENTA FINANCIADA CON CUOTAS ──────────────────────────────────────
        fecha_inicio = datetime.now() - timedelta(days=90)
        fecha_vcto = datetime.now() - timedelta(days=60)

        asesor = created_users.get("Stefania")
        supervisor = created_users.get("Santiago")

        venta_fin = VentaFinanciada(
            cliente_nombre="Marcela Rodríguez",
            cliente_telefono="1198765432",
            cliente_localidad="Campana, Buenos Aires",
            producto="PISCINA",
            modelo_especifico="Playa y Abanico Mediana",
            color="Celeste",
            forma_pago="PMI",
            precio_total=2_800_000,
            anticipo=280_000,
            cantidad_cuotas=24,
            valor_cuota=105_000,
            fecha_inicio_plan=fecha_inicio,
            fecha_primer_vencimiento=fecha_vcto,
            cuotas_pagas=3,
            asesor_apertura_id=asesor.id if asesor else None,
            supervisor_cierre_id=supervisor.id if supervisor else None,
            estado_plan="ACTIVO",
            estado_admision="APROBADO",
            notas="Cliente con buen comportamiento de pago.",
        )
        db.add(venta_fin)

        # Segunda venta con atraso
        fecha_inicio2 = datetime.now() - timedelta(days=120)
        fecha_vcto2 = datetime.now() - timedelta(days=90)
        daniel = created_users.get("Daniel")

        venta_fin2 = VentaFinanciada(
            cliente_nombre="Jorge Herrera",
            cliente_telefono="1154321987",
            cliente_localidad="Escobar, Buenos Aires",
            producto="MODULO",
            modelo_especifico="Módulo 24m²",
            forma_pago="DIRECTA_50",
            precio_total=4_500_000,
            anticipo=2_250_000,
            cantidad_cuotas=12,
            valor_cuota=187_500,
            fecha_inicio_plan=fecha_inicio2,
            fecha_primer_vencimiento=fecha_vcto2,
            cuotas_pagas=2,
            asesor_apertura_id=daniel.id if daniel else None,
            estado_plan="ATRASADO",
            notas="Contactar urgente. 2 cuotas sin pagar.",
        )
        db.add(venta_fin2)

        # ─── EMPLEADOS ────────────────────────────────────────────────────────
        empleados_data = [
            {
                "nombre": "Luis Fernández",
                "rol_empresa": "Técnico de instalación",
                "tipo_tarifa": "POR_DIA",
                "monto_tarifa": 15000,
                "sabado_recargo": True,
                "multiplicador_sabado": 1.5,
            },
            {
                "nombre": "Pablo González",
                "rol_empresa": "Operario de fábrica",
                "tipo_tarifa": "POR_DIA",
                "monto_tarifa": 12000,
                "sabado_recargo": True,
                "multiplicador_sabado": 1.5,
            },
            {
                "nombre": "Martín López",
                "rol_empresa": "Conductor / Logística",
                "tipo_tarifa": "POR_DIA",
                "monto_tarifa": 14000,
                "sabado_recargo": False,
                "multiplicador_sabado": 1.0,
            },
        ]

        for e_data in empleados_data:
            emp = Empleado(
                nombre=e_data["nombre"],
                rol_empresa=e_data["rol_empresa"],
                tipo_tarifa=e_data["tipo_tarifa"],
                monto_tarifa=e_data["monto_tarifa"],
                sabado_recargo=e_data["sabado_recargo"],
                multiplicador_sabado=e_data["multiplicador_sabado"],
                activo=True,
            )
            db.add(emp)
            db.flush()

            # Registrar asistencia esta semana
            for dias_atras in range(4, 0, -1):
                fecha = datetime.now() - timedelta(days=dias_atras)
                a = Asistencia(
                    empleado_id=emp.id,
                    fecha=fecha.replace(hour=8, minute=0, second=0),
                    tipo="PRESENTE",
                )
                db.add(a)

        # ─── ORDEN DE FÁBRICA ─────────────────────────────────────────────────
        orden = OrdenFabricaPiscina(
            cliente_nombre="Marcela Rodríguez",
            modelo="Playa y Abanico Mediana",
            color="Celeste",
            fecha_inicio=datetime.now() - timedelta(days=10),
            fecha_estimada_fin=datetime.now() + timedelta(days=5),
            estado="EN_PROCESO",
            notas="Cliente de Campana. Prioridad alta.",
        )
        db.add(orden)

        # ─── STOCK PISCINAS ───────────────────────────────────────────────────
        stock_piscinas = [
            ("Minimalista Chica", "Blanco", 3),
            ("Minimalista Mediana", "Celeste", 2),
            ("Minimalista Mediana", "Azul", 1),
            ("Arco Romano Mediano Recto", "Beige", 2),
            ("Miniportante", "Blanco", 0),
            ("Autoportante", "Verde agua", 1),
        ]

        for modelo, color, cantidad in stock_piscinas:
            s = StockPiscina(modelo=modelo, color=color, cantidad=cantidad)
            db.add(s)

        # ─── STOCK PANELES ────────────────────────────────────────────────────
        paneles = [
            ("Panel NCE Estándar 1.2m x 2.4m", 45, 10),
            ("Panel NCE Reforzado 1.2m x 2.4m", 20, 8),
            ("Panel NCE Angular", 30, 5),
            ("Panel NCE Techo", 25, 8),
        ]

        from database.models import StockPanel
        for tipo, cantidad, minimo in paneles:
            s = StockPanel(tipo_panel=tipo, cantidad=cantidad, stock_minimo=minimo)
            db.add(s)

        db.commit()
        print("[SEED] Completado!")
        print("\n[SEED] USUARIOS CREADOS:")
        print("-" * 50)
        for u_data in usuarios:
            roles_str = ", ".join(u_data["roles"])
            print(f"  Email: {u_data['email']}")
            print(f"  Pass:  {u_data['password']}")
            print(f"  Roles: {roles_str}")
            print()

    except Exception as e:
        db.rollback()
        print(f"[SEED ERROR] {e}")
        raise
    finally:
        db.close()


_CONFIG_DEFAULTS = {
    "flete_precio_km":           ("3000",                        "precios"),
    "flete_miniportante_km":     ("2000",                        "precios"),
    "descuento_combo_pct":       ("25",                          "precios"),
    "empresa_nombre":            ("EcoFiver",      "empresa"),
    "empresa_dir_planta":        ("Zárate, Buenos Aires",        "empresa"),
    "empresa_dir_showroom":      ("Av. Paseo Colón 1013, CABA", "empresa"),
    "ml_renovacion_automatica":  ("false",                       "ml_config"),

    # ── Plantilla de descripción ML ──────────────────────────────────────────
    "ml_desc_encabezado": (
        "EcoFiver — Fábrica de piscinas de fibra de vidrio y módulos habitacionales Wood Frame en Zárate, Buenos Aires.\n\n"
        "Fabricamos, transportamos e instalamos en todo el territorio argentino. "
        "El precio publicado incluye fabricación completa + flete hasta tu domicilio + instalación + puesta en marcha del sistema de filtrado. "
        "No hay costos adicionales ni sorpresas al momento de la entrega.\n\n"
        "Más de 15 años fabricando productos de primera calidad para familias argentinas.",
        "ml_config"
    ),
    "ml_desc_pie": (
        "Garantía en estructura: 5 años. "
        "Financiación propia en cuotas (consultanos las condiciones vigentes). "
        "Zona de instalación: Buenos Aires, GBA y provincias del interior (consultar cobertura y logística). "
        "Respondemos todas las preguntas en menos de 24 hs hábiles. "
        "EcoFiver — Zárate, Buenos Aires.",
        "ml_config"
    ),
    "ml_desc_encabezado_referencia": (
        "PRECIO DE REFERENCIA — SOLICITA TU COTIZACION PERSONALIZADA SIN COSTO\n\n"
        "El precio publicado es orientativo y sirve para iniciar el contacto. "
        "El valor final de tu piscina o módulo incluye fabricación, transporte e instalación y varía según el modelo elegido, "
        "la zona de entrega y las opciones adicionales. "
        "Para recibir tu cotización exacta y personalizada, envianos una pregunta o escribinos por WhatsApp — "
        "respondemos en menos de 24 hs hábiles.\n\n"
        "EcoFiver — Fábrica propia en Zárate, Buenos Aires. Instalamos en todo el país.",
        "ml_config"
    ),
    "ml_desc_pie_referencia": (
        "Como solicitar tu cotizacion: envianos una pregunta con el modelo que te interesa y tu zona de instalacion. "
        "Te respondemos con el precio completo (fabricación + flete + instalación) en menos de 24 hs hábiles. "
        "Sin compromiso. Sin costo. "
        "EcoFiver — Zárate, Buenos Aires.",
        "ml_config"
    ),
    "ml_desc_keywords": (
        "Buscas pileta, piscina, natatorio o spa de fibra de vidrio? "
        "Fabricamos piletas prefabricadas, piscinas de fibra de vidrio, natatorios familiares y piletas autoportantes. "
        "También producimos módulos habitacionales Wood Frame, casas prefabricadas, ampliaciones y viviendas modulares llave en mano. "
        "Instalamos en Buenos Aires, GBA, Rosario, Córdoba, Santa Fe, Mendoza y todo el interior del país.",
        "ml_config"
    ),
    # Distribución de leads
    "leads_modo_distribucion":   ("ROUND_ROBIN",                 "leads"),
    "leads_rotacion_horas":      ("24",                          "leads"),
    # Notificaciones
    "tel_rodrigo":               ("",                            "notificaciones"),
    "equipo_codigo_acceso":      ("ECO2026",                     "notificaciones"),
}


def seed_config_defaults():
    """
    Inserta valores por defecto para claves de configuración que aún no existen
    o cuyo valor está vacío. Se ejecuta en cada inicio (idempotente).
    Los valores ML de descripción se completan aunque la clave exista vacía.
    """
    ML_KEYS = {"ml_desc_encabezado", "ml_desc_pie", "ml_desc_encabezado_referencia",
               "ml_desc_pie_referencia", "ml_desc_keywords"}
    db = SessionLocal()
    try:
        for clave, (valor, categoria) in _CONFIG_DEFAULTS.items():
            existing = db.query(ConfiguracionSistema).filter(
                ConfiguracionSistema.clave == clave
            ).first()
            if not existing:
                db.add(ConfiguracionSistema(
                    clave=clave,
                    valor=valor,
                    es_secreto=False,
                    categoria=categoria,
                    estado="activa",
                ))
            elif clave in ML_KEYS and not (existing.valor or "").strip():
                # Completar campos ML vacíos sin sobreescribir valores personalizados
                existing.valor = valor
                existing.estado = "activa"
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def seed_rr_defaults():
    """
    Inicializa el pool de round-robin con Hernán, Stefania y Santiago
    si la clave aún no existe. Se ejecuta en cada inicio (idempotente).
    """
    db = SessionLocal()
    try:
        existing = db.query(ConfiguracionSistema).filter(
            ConfiguracionSistema.clave == "leads_rr_asesores"
        ).first()
        if existing:
            return  # Ya configurado, no tocar

        nombres_default = ["Hernán", "Stefania", "Santiago"]
        usuarios = db.query(Usuario).filter(
            Usuario.activo == True,
            Usuario.nombre.in_(nombres_default)
        ).all()

        ids = [u.id for u in usuarios] if usuarios else []
        db.add(ConfiguracionSistema(
            clave="leads_rr_asesores",
            valor=json.dumps(ids),
            es_secreto=False,
            categoria="leads",
            estado="activa",
        ))
        db.commit()
        print(f"[SEED] Pool round-robin inicializado con {len(ids)} asesores: {[u.nombre for u in usuarios]}")
    except Exception as e:
        db.rollback()
        print(f"[SEED] Error inicializando pool RR: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    from database.database import engine
    from database.models import Base
    Base.metadata.create_all(bind=engine)
    seed_database()
    seed_config_defaults()
    seed_rr_defaults()
