"""
Inicialización idempotente de Aliados.
Los datos sensibles (emails, nombres, contraseña) se leen de variables de entorno:

  ADMIN_ALIADO_EMAIL     — email del usuario que debe tener es_admin_crm=True
  INIT_SOCIOS_JSON       — JSON array: [{"nombre":"...", "email":"..."}, ...]
  INIT_TEMP_PASSWORD     — contraseña temporal para los socios seed/activados (default: EcoFiver2026!)

Qué hace en cada arranque (idempotente):
- Garantiza que ADMIN_ALIADO_EMAIL sea admin CRM.
- Crea los socios de INIT_SOCIOS_JSON si no existen (por email).
- Activa todos los aliados registrados (postulante/en_evaluacion) y les asigna
  contraseña temporal si aún no tienen una.
- Socios activos sin contraseña también reciben la contraseña temporal.
"""
import json
import logging
import os

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database.models import Aliado

log = logging.getLogger(__name__)
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    admin_email = os.getenv("ADMIN_ALIADO_EMAIL", "").strip().lower()
    temp_password = os.getenv("INIT_TEMP_PASSWORD", "EcoFiver2026!")
    socios_raw = os.getenv("INIT_SOCIOS_JSON", "[]")

    try:
        socios_seed = json.loads(socios_raw)
    except Exception:
        log.warning("[init_aliados] INIT_SOCIOS_JSON inválido — se omite seed de socios")
        socios_seed = []

    _hash = _pwd.hash(temp_password)

    # 1. Admin
    if admin_email:
        admin = db.query(Aliado).filter(Aliado.email == admin_email).first()
        if admin:
            if not admin.es_admin_crm:
                admin.es_admin_crm = True
                log.info(f"[init_aliados] {admin_email} → es_admin_crm=True")
        else:
            log.info(f"[init_aliados] {admin_email} aún no está registrado — se seteará cuando se registre")

    # 2. Socios fundadores (idempotente por email)
    for s in socios_seed:
        email = (s.get("email") or "").strip().lower()
        nombre = (s.get("nombre") or "").strip()
        if not email or not nombre:
            continue
        existing = db.query(Aliado).filter(Aliado.email == email).first()
        if existing:
            # Actualizar teléfono si viene en el JSON y el aliado no lo tiene
            tel = (s.get("telefono") or "").strip()
            if tel and not existing.telefono:
                existing.telefono = tel
            continue
        codigo = _next_codigo(db)
        tel = (s.get("telefono") or "").strip()
        nuevo = Aliado(
            codigo=codigo,
            nombre=nombre,
            email=email,
            telefono=tel or None,
            password_hash=_hash,
            estado="activo",
            whatsapp_verificado=False,
            email_verificado=True,
            primer_login=True,
        )
        db.add(nuevo)
        db.flush()
        log.info(f"[init_aliados] Creado socio {codigo} — {nombre}")

    # 3. Activar postulantes/en_evaluacion
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

    # 5. Resincronizar contraseña temporal para quienes aún no la cambiaron
    #    (primer_login=True → todavía tienen la temp, se actualiza si cambió INIT_TEMP_PASSWORD)
    pendientes_pw = db.query(Aliado).filter(Aliado.primer_login == True).all()  # noqa: E712
    for a in pendientes_pw:
        a.password_hash = _hash
        log.info(f"[init_aliados] Contraseña re-sincronizada para {a.codigo} ({a.nombre})")

    db.commit()
    log.info("[init_aliados] Completado")
