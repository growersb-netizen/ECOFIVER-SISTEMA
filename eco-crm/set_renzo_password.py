"""
Script puntual: actualiza la contraseña de Renzo a Renzo2024!
Ejecutar desde la raíz del proyecto:
  python set_renzo_password.py            (entorno local)
  docker exec <container> python /app/set_renzo_password.py   (Docker)
"""
import sys
import os

# Soporte tanto local como Docker
for path in ['.', '/app']:
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv
load_dotenv()

from database.database import SessionLocal
from database.models import Usuario
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

NEW_PASSWORD = "Renzo2024!"
EMAIL = "renzo@ecomodulos.com"

db = SessionLocal()
try:
    renzo = db.query(Usuario).filter(Usuario.email == EMAIL).first()
    if not renzo:
        print(f"ERROR: No se encontró usuario con email {EMAIL}")
    else:
        renzo.password_hash = pwd_context.hash(NEW_PASSWORD)
        db.commit()
        print(f"✓ Contraseña de {renzo.nombre} ({renzo.email}) actualizada a: {NEW_PASSWORD}")
        print(f"  Rol: {renzo.roles_json}")
        print(f"  IMPORTANTE: Renzo debe cambiar la contraseña desde /perfil al primer ingreso.")
finally:
    db.close()
