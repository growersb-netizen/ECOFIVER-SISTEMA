"""
Seguridad: JWT, hashing de contraseñas y cifrado de tokens OAuth.
Los tokens de redes sociales se cifran con Fernet antes de guardar en DB.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# ─── Contraseñas ─────────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT ─────────────────────────────────────────────────────────────────────

def create_access_token(subject: Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode(
        {"sub": str(subject), "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(subject: Any) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "refresh"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """Lanza JWTError si el token es inválido o expiró."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ─── Cifrado de tokens OAuth ──────────────────────────────────────────────────
# Los access/refresh tokens de redes sociales nunca se guardan en texto plano.

def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError("ENCRYPTION_KEY no configurada — generar con Fernet.generate_key()")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plain_token: str) -> str:
    """Cifra un token OAuth para almacenar en DB."""
    return _get_fernet().encrypt(plain_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Descifra un token OAuth almacenado en DB."""
    return _get_fernet().decrypt(encrypted_token.encode()).decode()
