"""
Utilidades de encriptación para valores sensibles (API keys, tokens).
Usa Fernet (AES-128-CBC + HMAC) con clave desde env var ENCRYPTION_KEY.

Si ENCRYPTION_KEY no está configurado, los valores se guardan en texto plano
con una advertencia. Para producción siempre configurar la clave.

Generar una clave válida:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
import base64
import hashlib
from typing import Optional


def _get_fernet_key() -> Optional[bytes]:
    """Devuelve una clave Fernet-compatible desde la env var ENCRYPTION_KEY."""
    raw = os.getenv("ENCRYPTION_KEY", "").strip()
    if not raw:
        return None

    # Si ya es una clave Fernet válida (44 chars URL-safe base64), usarla directo
    if len(raw) == 44:
        try:
            base64.urlsafe_b64decode(raw + "==")
            return raw.encode()
        except Exception:
            pass

    # Si no, derivar clave de 32 bytes con SHA-256
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _is_fernet_token(s: str) -> bool:
    """Los tokens Fernet siempre empiezan con 'gAAAAA' (versión byte 0x80 en base64)."""
    return bool(s) and s.startswith("gAAAAA")


def encrypt_value(value: str) -> str:
    """
    Encripta un string. Si no hay ENCRYPTION_KEY, devuelve el valor sin cambios.
    """
    if not value:
        return value
    key = _get_fernet_key()
    if not key:
        return value  # Sin clave: guardar en claro (warn en logs de startup)
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).encrypt(value.encode()).decode()
    except Exception:
        return value  # Fallback a texto plano si falla


def decrypt_value(stored: str) -> str:
    """
    Desencripta un string. Si el valor no parece encriptado, lo devuelve tal cual.
    Esto permite coexistencia de valores en claro (antes de configurar la clave)
    con valores encriptados (después).
    """
    if not stored:
        return stored
    if not _is_fernet_token(stored):
        return stored  # Texto plano, devolver tal cual
    key = _get_fernet_key()
    if not key:
        return ""  # Hay token encriptado pero no hay clave
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(stored.encode()).decode()
    except Exception:
        return ""  # Token dañado o clave incorrecta


def has_encryption_key() -> bool:
    return bool(_get_fernet_key())
