"""
Lee WA_TOKEN del entorno y lo pone en system_token_enc de portafolios sin token.
Ejecutar: python init_portafolio_tokens.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from database.database import SessionLocal
from database.models import MetaPortafolio
from database.encryption import encrypt_value

wa_token = os.getenv("WA_TOKEN", "").strip()
if not wa_token:
    print("ERROR: WA_TOKEN no está configurado en el entorno.")
    sys.exit(1)

db = SessionLocal()
try:
    pfs = db.query(MetaPortafolio).all()
    actualizados = []
    for p in pfs:
        if not p.system_token_enc:
            p.system_token_enc = encrypt_value(wa_token)
            actualizados.append(p.nombre)
    db.commit()
    if actualizados:
        print(f"✓ Token seteado en {len(actualizados)} portafolio(s): {', '.join(actualizados)}")
    else:
        print("Todos los portafolios ya tienen token configurado.")
finally:
    db.close()
