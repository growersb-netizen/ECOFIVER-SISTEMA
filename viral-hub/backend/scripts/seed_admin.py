"""
Crea el usuario administrador inicial de Viral Hub.

Uso:
    cd backend
    python scripts/seed_admin.py

Requiere DATABASE_SYNC_URL configurada en .env (o variable de entorno).
Ejecutar DESPUÉS de: alembic upgrade head
"""

import sys
import os

# Agregar el directorio padre al path para importar la app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User
from app.models.workspace import Workspace, Membership, Subscription, MemberRole

settings = get_settings()

# ─── Credenciales del admin ───────────────────────────────────────────────────
ADMIN_EMAIL = "admin@viralhub.io"
ADMIN_PASSWORD = "F9@KAx3y9jjRPM!n"   # Cambiar después del primer login
ADMIN_FULL_NAME = "Administrador"
WORKSPACE_NAME = "Viral Hub"
WORKSPACE_SLUG = "viral-hub"

# ─── Config plan admin (sin límites) ─────────────────────────────────────────
ADMIN_PLAN_CONFIG = {
    "max_channels": 9999,
    "max_users": 99,
    "max_storage_gb": 9999,
    "max_publications_per_month": 999999,
    "features": {
        "analytics": True,
        "api_access": True,
        "custom_groups": True,
        "admin_panel": True,
    }
}


def seed():
    engine = create_engine(settings.DATABASE_SYNC_URL, echo=False)

    with Session(engine) as session:
        # Verificar si ya existe
        existing = session.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing:
            print(f"✓ El usuario {ADMIN_EMAIL} ya existe — nada que hacer.")
            return

        print(f"Creando usuario admin: {ADMIN_EMAIL}")

        # Crear usuario
        user = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            full_name=ADMIN_FULL_NAME,
            is_active=True,
            is_superadmin=True,
        )
        session.add(user)
        session.flush()

        # Crear workspace
        workspace = Workspace(
            name=WORKSPACE_NAME,
            slug=WORKSPACE_SLUG,
            is_active=True,
        )
        session.add(workspace)
        session.flush()

        # Membresía owner
        membership = Membership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MemberRole.owner,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
        session.add(membership)

        # Suscripción Enterprise (sin límites)
        subscription = Subscription(
            workspace_id=workspace.id,
            plan_name="enterprise",
            plan_config=ADMIN_PLAN_CONFIG,
        )
        session.add(subscription)

        # Grupo "Todas" del workspace
        from app.models.channel import ChannelGroup
        all_group = ChannelGroup(
            workspace_id=workspace.id,
            name="Todas",
            description="Todos los canales conectados",
            is_system=True,
        )
        session.add(all_group)

        session.commit()
        print(f"\n{'='*50}")
        print(f"  ✅ Admin creado exitosamente")
        print(f"{'='*50}")
        print(f"  Email:     {ADMIN_EMAIL}")
        print(f"  Password:  {ADMIN_PASSWORD}")
        print(f"  Workspace: {WORKSPACE_NAME}")
        print(f"  Plan:      Enterprise (sin límites)")
        print(f"{'='*50}")
        print(f"  ⚠️  Cambiar la contraseña después del primer login")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    seed()
