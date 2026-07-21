"""
Script para crear la usuaria Lourdes Agudo en el CRM con rol de vendedora.
También crea los otros vendedores si no existen.
Ejecutar desde eco-crm/ con el venv activado:
    python crear_lourdes.py
"""
import sys
import json
from sqlalchemy.orm import Session

sys.path.insert(0, ".")

from database.database import SessionLocal
from database.models import Usuario

# Vendedores a crear/verificar
VENDEDORES = [
    {"nombre": "Macarena Bordato",  "email": "macarena@ecomodulos.com"},
    {"nombre": "Natalia Bordato",   "email": "natalia@ecomodulos.com"},
    {"nombre": "Lautaro Roit",      "email": "lautaro@ecomodulos.com"},
    {"nombre": "Javier Ruiz",       "email": "javier@ecomodulos.com"},
]

# Lourdes - la que se crea con acceso completo de vendedora
LOURDES = {
    "nombre": "Lourdes Agudo",
    "email": "lourdes@ecomodulos.com",
    "password": "Lourdes2024!",
    "roles": ["ASESOR_APERTURA", "SUPERVISOR_CIERRE"],  # acceso a ventas contado y financiadas
}

def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def main():
    db: Session = SessionLocal()
    try:
        # Crear Lourdes
        existing = db.query(Usuario).filter(Usuario.email == LOURDES["email"]).first()
        if existing:
            print(f"✓ Lourdes ya existe (ID={existing.id}), actualizando roles y contraseña...")
            existing.roles_json = json.dumps(LOURDES["roles"])
            existing.password_hash = hash_password(LOURDES["password"])
            existing.activo = True
            db.commit()
            print(f"  → Roles: {LOURDES['roles']}")
            print(f"  → Contraseña actualizada a: {LOURDES['password']}")
        else:
            lourdes = Usuario(
                nombre=LOURDES["nombre"],
                email=LOURDES["email"],
                password_hash=hash_password(LOURDES["password"]),
                roles_json=json.dumps(LOURDES["roles"]),
                activo=True,
            )
            db.add(lourdes)
            db.commit()
            db.refresh(lourdes)
            print(f"✓ Lourdes Agudo creada (ID={lourdes.id})")
            print(f"  Email: {LOURDES['email']}")
            print(f"  Contraseña: {LOURDES['password']}")
            print(f"  Roles: {LOURDES['roles']}")

        print()

        # Crear otros vendedores (sin contraseña inicialmente — admin puede asignarla)
        for v in VENDEDORES:
            existing = db.query(Usuario).filter(Usuario.email == v["email"]).first()
            if existing:
                print(f"✓ {v['nombre']} ya existe (ID={existing.id})")
                # Asegurarse que tenga rol ASESOR_APERTURA para aparecer en el dropdown
                current_roles = json.loads(existing.roles_json or "[]")
                if "ASESOR_APERTURA" not in current_roles:
                    current_roles.append("ASESOR_APERTURA")
                    existing.roles_json = json.dumps(current_roles)
                    print(f"  → Rol ASESOR_APERTURA agregado")
            else:
                # Contraseña temporal = nombre sin espacios + "2024!"
                temp_pwd = v["nombre"].replace(" ", "") + "2024!"
                usuario = Usuario(
                    nombre=v["nombre"],
                    email=v["email"],
                    password_hash=hash_password(temp_pwd),
                    roles_json=json.dumps(["ASESOR_APERTURA"]),
                    activo=True,
                )
                db.add(usuario)
                db.commit()
                db.refresh(usuario)
                print(f"✓ {v['nombre']} creado (ID={usuario.id})")
                print(f"  Email: {v['email']}")
                print(f"  Contraseña temporal: {temp_pwd}")

        db.commit()
        print()
        print("=" * 50)
        print("Todos los usuarios procesados correctamente.")
        print()
        print("ACCESO LOURDES:")
        print(f"  URL: https://eco-crm.fly.dev (o la URL del CRM)")
        print(f"  Email: {LOURDES['email']}")
        print(f"  Contraseña: {LOURDES['password']}")
        print()
        print("Lourdes puede:")
        print("  - Registrar ventas de contado (módulos y piscinas)")
        print("  - Registrar ventas con plan de financiación")
        print("  - Seleccionar el vendedor/asesor al que pertenece cada venta")
        print("  - Ver el historial de ventas")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
