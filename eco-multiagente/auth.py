"""
Autenticación del sistema — Eco Módulos & Piscinas IA
Usuario único administrador: email + contraseña
"""
import os


ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL",    "admin@ecomodulosypiscinas.com.ar")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "NOAH2027")


def check_credentials(email: str, password: str) -> bool:
    """Valida email + contraseña del administrador."""
    if not email or not password:
        return False
    return (
        email.strip().lower() == ADMIN_EMAIL.strip().lower()
        and password == ADMIN_PASSWORD
    )


def check_password(pw: str) -> bool:
    """
    Valida solo la contraseña (usado en cabeceras X-Panel-Password de la API).
    Mantiene compatibilidad con todos los endpoints existentes.
    """
    return bool(pw) and pw == ADMIN_PASSWORD


def is_admin(pw: str) -> bool:
    """Siempre admin si la contraseña es correcta (único usuario)."""
    return check_password(pw)


def get_user_role(pw: str) -> str:
    """Devuelve 'admin' o 'none'."""
    return "admin" if check_password(pw) else "none"
