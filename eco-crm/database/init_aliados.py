"""
Inicialización idempotente de Aliados.
- Garantiza que growersb@gmail.com sea admin CRM.
- Crea los socios fundadores (primer batch) si no existen.
- Activa todos los aliados registrados (postulante/en_evaluacion) y les asigna
  contraseña temporal si aún no tienen una.
"""
import logging
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database.models import Aliado

log = logging.getLogger(__name__)
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEMP_PASSWORD = "EcoFiver2026!"

_SOCIOS_SEED = [
    {"nombre": "Gustavo González",       "email": "gustavo11gonzalez6@gmail.com"},
    {"nombre": "Carlos Osvaldo Vega",    "email": "sstaffuno@gmail.com"},
    {"nombre": "Andrés Alberto Samudio", "email": "samudioandres088@gmail.com"},
    {"nombre": "José Antonio González",  "email": "josegonzalez823@gmail.com"},
    {"nombre": "Guillermo Jofre",        "email": "giofre.gegsol@gmail.com"},
    {"nombre": "Diego Fratini",          "email": "diegofratini@gmail.com"},
]

ADMIN_EMAIL = "growersb@gmail.com"


def _next_codigo(db: Session) -> str:
    ultimo = db.query(Aliado).order_by(Aliado.id.desc()).first()
    if ultimo and ultimo.codigo and ultimo.codigo.upper().startswith("AL-"):
        try:
            n = int(ultimo.codigo.split("-")[-1]) + 1
        except Exception:
            n = (ultimo.id or 0) + 1
    elif ultimo:
        n = (ultimo.id or 0) + 1
    else:
        n = 1
    return f"AL-{n:03d}"


def init_aliados(db: Session) -> None:
    # 1. Admin growersb
    admin = db.query(Aliado).filter(Aliado.email == ADMIN_EMAIL).first()
    if admin:
        if not admin.es_admin_crm:
            admin.es_admin_crm = True
            log.info(f"[init_aliados] {ADMIN_EMAIL} → es_admin_crm=True")
    else:
        log.info(f"[init_aliados] {ADMIN_EMAIL} no encontrado — se creará si se registra")

    # 2. Socios fundadores (idempotente por email)
    _hash = _pwd.hash(TEMP_PASSWORD)
    for s in _SOCIOS_SEED:
        existing = db.query(Aliado).filter(Aliado.email == s["email"]).first()
        if not existing:
            codigo = _next_codigo(db)
            nuevo = Aliado(
                codigo=codigo,
                nombre=s["nombre"],
                email=s["email"],
                password_hash=_hash,
                estado="activo",
                whatsapp_verificado=False,
                email_verificado=True,
                primer_login=True,
            )
            db.add(nuevo)
            db.flush()  # para que el próximo _next_codigo vea el ID
            log.info(f"[init_aliados] Creado socio {codigo} — {s['nombre']}")

    # 3. Activar todos los registrados sin activar; asignar contraseña temporal si no tienen
    pendientes = db.query(Aliado).filter(
        Aliado.estado.in_(["postulante", "en_evaluacion"])
    ).all()
    for a in pendientes:
        a.estado = "activo"
        if not a.password_hash:
            a.password_hash = _hash
            a.primer_login = True
        log.info(f"[init_aliados] Activado {a.codigo} ({a.nombre})")

    # 4. Socios activos sin contraseña → asignar temporal
    sin_pass = db.query(Aliado).filter(
        Aliado.estado == "activo",
        Aliado.password_hash == None,  # noqa: E711
    ).all()
    for a in sin_pass:
        a.password_hash = _hash
        a.primer_login = True
        log.info(f"[init_aliados] Contraseña temporal asignada a {a.codigo} ({a.nombre})")

    db.commit()
    log.info("[init_aliados] Completado")
