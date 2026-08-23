"""seed admin user

Revision ID: 002
Revises: 001
Create Date: 2026-08-23 00:01:00.000000

Crea el usuario administrador inicial de Viral Hub.
Idempotente: verifica si ya existe antes de insertar.
"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

# revision identifiers
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Admin credentials
ADMIN_EMAIL = "admin@viralhub.io"
ADMIN_PASSWORD = "F9@KAx3y9jjRPM!n"
ADMIN_FULL_NAME = "Administrador"
WORKSPACE_NAME = "Viral Hub"
WORKSPACE_SLUG = "viral-hub"


def _hash_password(password: str) -> str:
    """Hash usando passlib/bcrypt (misma librería que la app)."""
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return ctx.hash(password)


def upgrade() -> None:
    conn = op.get_bind()

    # Verificar si ya existe el admin
    result = conn.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": ADMIN_EMAIL}
    )
    if result.fetchone():
        print(f"  ✓ Admin {ADMIN_EMAIL} ya existe — skip.")
        return

    now = datetime.now(timezone.utc)
    hashed = _hash_password(ADMIN_PASSWORD)

    # Insertar usuario
    result = conn.execute(
        sa.text("""
            INSERT INTO users (email, hashed_password, full_name, is_active, is_superadmin, created_at, updated_at)
            VALUES (:email, :pwd, :name, true, true, :now, :now)
            RETURNING id
        """),
        {"email": ADMIN_EMAIL, "pwd": hashed, "name": ADMIN_FULL_NAME, "now": now}
    )
    user_id = result.fetchone()[0]

    # Verificar si ya existe el workspace
    result = conn.execute(
        sa.text("SELECT id FROM workspaces WHERE slug = :slug"),
        {"slug": WORKSPACE_SLUG}
    )
    ws_row = result.fetchone()
    if ws_row:
        workspace_id = ws_row[0]
    else:
        result = conn.execute(
            sa.text("""
                INSERT INTO workspaces (name, slug, is_active, created_at, updated_at)
                VALUES (:name, :slug, true, :now, :now)
                RETURNING id
            """),
            {"name": WORKSPACE_NAME, "slug": WORKSPACE_SLUG, "now": now}
        )
        workspace_id = result.fetchone()[0]

    # Membresía owner
    conn.execute(
        sa.text("""
            INSERT INTO memberships (workspace_id, user_id, role, is_active, invited_at, joined_at)
            VALUES (:wid, :uid, 'owner', true, :now, :now)
        """),
        {"wid": workspace_id, "uid": user_id, "now": now}
    )

    # Suscripción enterprise
    import json
    plan_config = json.dumps({
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
    })
    conn.execute(
        sa.text("""
            INSERT INTO subscriptions (workspace_id, plan_name, status, plan_config, created_at)
            VALUES (:wid, 'enterprise', 'active', :cfg::jsonb, :now)
        """),
        {"wid": workspace_id, "cfg": plan_config, "now": now}
    )

    # Grupo "Todas" por defecto
    conn.execute(
        sa.text("""
            INSERT INTO channel_groups (workspace_id, name, is_system, created_at)
            VALUES (:wid, 'Todas', true, :now)
        """),
        {"wid": workspace_id, "now": now}
    )

    print(f"\n{'='*50}")
    print(f"  ✅ Admin creado")
    print(f"  Email:    {ADMIN_EMAIL}")
    print(f"  Password: {ADMIN_PASSWORD}")
    print(f"  Plan:     Enterprise")
    print(f"{'='*50}")


def downgrade() -> None:
    conn = op.get_bind()
    # Borrar datos de seed (no las tablas — eso lo hace 001 downgrade)
    conn.execute(sa.text("DELETE FROM channel_groups WHERE is_system = true AND workspace_id IN (SELECT id FROM workspaces WHERE slug = 'viral-hub')"))
    conn.execute(sa.text("DELETE FROM subscriptions WHERE workspace_id IN (SELECT id FROM workspaces WHERE slug = 'viral-hub')"))
    conn.execute(sa.text("DELETE FROM memberships WHERE workspace_id IN (SELECT id FROM workspaces WHERE slug = 'viral-hub')"))
    conn.execute(sa.text("DELETE FROM workspaces WHERE slug = 'viral-hub'"))
    conn.execute(sa.text("DELETE FROM users WHERE email = 'admin@viralhub.io'"))
