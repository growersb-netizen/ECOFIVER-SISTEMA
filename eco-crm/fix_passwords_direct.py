"""
EJECUTAR DESDE EL SHELL DE RAILWAY (no local):
  python fix_passwords_direct.py

Resetea admin + aliados AL-020..AL-024 sin depender de los modulos del app.
"""
import os, sys
import psycopg2
import bcrypt

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL no disponible en el entorno")
    sys.exit(1)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

def make_hash(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt(12)).decode()

# --- Admin ---
admin_email = "rodrigo@ecomodulos.com"
admin_hash = make_hash("EcoAdmin2024!")
cur.execute("UPDATE usuarios SET password_hash = %s WHERE email = %s", (admin_hash, admin_email))
print(f"Admin {admin_email}: {cur.rowcount} fila(s) actualizada(s)  pw=EcoAdmin2024!")

# --- Aliados AL-020..AL-024 ---
aliados_hash = make_hash("ECO1234")
for codigo in ["AL-020", "AL-021", "AL-022", "AL-023", "AL-024"]:
    cur.execute(
        "UPDATE aliados SET password_hash = %s, primer_login = TRUE WHERE codigo = %s",
        (aliados_hash, codigo)
    )
    if cur.rowcount:
        cur.execute("SELECT nombre, email, telefono FROM aliados WHERE codigo = %s", (codigo,))
        row = cur.fetchone()
        print(f"  {codigo}  {row[0]}  email={row[1]}  tel={row[2]}  pw=ECO1234")
    else:
        print(f"  {codigo}: NO ENCONTRADO")

conn.commit()
cur.close()
conn.close()
print("\nContrasenas actualizadas.")
