"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-21

"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from database.models import Base  # noqa: E402

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    # Seed solicitud_contador if empty
    from sqlalchemy import text

    exists = bind.execute(
        text("SELECT COUNT(*) FROM solicitud_contador")
    ).scalar()
    if not exists:
        bind.execute(
            text(
                "INSERT INTO solicitud_contador (id, prefijo, ultimo_numero) "
                "VALUES (1, '000', 13860152)"
            )
        )


def downgrade() -> None:
    from database.models import Base  # noqa: E402

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
