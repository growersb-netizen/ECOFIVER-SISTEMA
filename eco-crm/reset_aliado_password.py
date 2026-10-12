"""
Reset contraseña de un aliado por código o email.
Uso:
  railway run python reset_aliado_password.py AL-010 nuevapass123
"""
import sys
for path in ['.', '/app']:
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv
load_dotenv()

from database.database import SessionLocal
from database.models import Aliado
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

if len(sys.argv) < 3:
    print("Uso: python reset_aliado_password.py <codigo_o_email> <nueva_password>")
    sys.exit(1)

identificador = sys.argv[1].strip()
nueva_password = sys.argv[2].strip()

db = SessionLocal()
try:
    # Buscar por código (ej: AL-010 o 010) o por email
    aliado = db.query(Aliado).filter(Aliado.codigo == identificador).first()
    if not aliado:
        aliado = db.query(Aliado).filter(Aliado.email == identificador).first()
    if not aliado and identificador.isdigit():
        codigo_fmt = f"AL-{identificador.zfill(3)}"
        aliado = db.query(Aliado).filter(Aliado.codigo == codigo_fmt).first()

    if not aliado:
        print(f"ERROR: No se encontró aliado con código/email '{identificador}'")
        sys.exit(1)

    aliado.password_hash = pwd_context.hash(nueva_password)
    db.commit()
    print(f"OK: Contraseña de {aliado.nombre} ({aliado.codigo}) reseteada correctamente.")
    print(f"    Email: {aliado.email}")
    print(f"    Nueva contraseña: {nueva_password}")
finally:
    db.close()
