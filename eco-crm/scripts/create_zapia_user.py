"""
Script one-shot: crea el usuario Zapia con rol ADMIN en la DB de producción.
Ejecutar: python scripts/create_zapia_user.py
"""
import sys
import os
import json

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from database.database import SessionLocal
from database.models import Usuario
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

EMAIL    = "zapia@ecomodulos.com"
PASSWORD = "ZapiaEco2026!"
NOMBRE   = "Zapia Bot"
ROLES    = ["ADMIN", "ASESOR_APERTURA", "SUPERVISOR_CIERRE", "COORDINADOR_OPERATIVO",
            "COBRANZAS", "FABRICA", "ADMINISTRACION"]

db = SessionLocal()

existing = db.query(Usuario).filter(Usuario.email == EMAIL).first()
if existing:
    # Actualizar por si acaso
    existing.password_hash = pwd_context.hash(PASSWORD)
    existing.roles_json    = json.dumps(ROLES)
    existing.activo        = True
    db.commit()
    print(f"✓ Usuario '{EMAIL}' actualizado con todos los roles.")
else:
    user = Usuario(
        nombre        = NOMBRE,
        email         = EMAIL,
        password_hash = pwd_context.hash(PASSWORD),
        roles_json    = json.dumps(ROLES),
        activo        = True,
    )
    db.add(user)
    db.commit()
    print(f"✓ Usuario '{EMAIL}' creado con todos los roles.")

db.close()
print(f"\n  Email:    {EMAIL}")
print(f"  Password: {PASSWORD}")
print(f"  Roles:    {ROLES}")
print(f"\n  API token: POST /api/auth/token  username={EMAIL}  password={PASSWORD}")
