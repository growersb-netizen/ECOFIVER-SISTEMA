"""
Script puntual: resetea la contraseña de Rodrigo (admin) a EcoAdmin2024!
Ejecutar en Fly.io:
  flyctl ssh console -a eco-crm-app
  python /app/reset_admin_password.py
"""
import sys
for path in ['.', '/app']:
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv
load_dotenv()

from database.database import SessionLocal
from database.models import Usuario
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

NEW_PASSWORD = "EcoAdmin2024!"
EMAIL = "rodrigo@ecomodulos.com"

db = SessionLocal()
try:
    user = db.query(Usuario).filter(Usuario.email == EMAIL).first()
    if not user:
        print(f"ERROR: No se encontro usuario con email {EMAIL}")
    else:
        user.password_hash = pwd_context.hash(NEW_PASSWORD)
        db.commit()
        print(f"OK Contrasena de {user.nombre} ({user.email}) actualizada a: {NEW_PASSWORD}")
        print(f"   Roles: {user.roles_json}")
finally:
    db.close()
