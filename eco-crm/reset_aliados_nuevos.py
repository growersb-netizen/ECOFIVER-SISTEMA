"""
Script puntual: resetea contraseñas de aliados AL-020..AL-024 a ECO1234
y activa primer_login=True para que puedan ingresar al panel.

Ejecutar en Railway shell:
  python reset_aliados_nuevos.py
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
NEW_PASSWORD = "ECO1234"
CODIGOS = ["AL-020", "AL-021", "AL-022", "AL-023", "AL-024"]

db = SessionLocal()
try:
    for codigo in CODIGOS:
        al = db.query(Aliado).filter(Aliado.codigo == codigo).first()
        if not al:
            print(f"NO ENCONTRADO: {codigo}")
            continue
        al.password_hash = pwd_context.hash(NEW_PASSWORD)
        al.primer_login = True
        print(f"OK  {codigo}  {al.nombre}  ({al.email or al.telefono})  → {NEW_PASSWORD}")
    db.commit()
    print("\nContraseñas actualizadas. Los socios ya pueden ingresar al panel.")
finally:
    db.close()
