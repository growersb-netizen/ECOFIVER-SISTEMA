"""
Genera los valores de las variables secretas para el .env.
Ejecutar una vez durante el setup.

Uso:
    python scripts/generate_secrets.py
"""

import secrets
from cryptography.fernet import Fernet

print("\n=== Variables a agregar al .env ===\n")
print(f"SECRET_KEY={secrets.token_hex(32)}")
print(f"JWT_SECRET_KEY={secrets.token_hex(32)}")
print(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")
print("\nCopiar estos valores al .env. Nunca compartirlos ni commitearlos.\n")
