import sys
sys.path.insert(0, '/app')
from database.database import SessionLocal
from database.models import Usuario
from routers.auth import hash_password

PASSWORDS = {
    1: 'EcoAdmin2025',
    2: 'EcoVentas2025',
    3: 'EcoVentas2025',
    4: 'EcoVentas2025',
    5: 'EcoVentas2025',
    6: 'EcoRenzo2025',
    7: 'EcoCobros2025',
    8: 'EcoFabrica2025',
}

db = SessionLocal()
for u in db.query(Usuario).all():
    p = PASSWORDS.get(u.id)
    if p:
        u.password_hash = hash_password(p)
        print(f'OK: {u.nombre} ({u.email}) -> {p}')
db.commit()
db.close()
print('Contraseñas actualizadas.')
