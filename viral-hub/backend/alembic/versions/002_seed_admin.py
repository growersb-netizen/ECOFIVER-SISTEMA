"""seed admin user (delegated to app startup)

Revision ID: 002
Revises: 001
Create Date: 2026-08-23 00:01:00.000000

El seed del admin se realiza en el lifespan de FastAPI (app/main.py)
para poder usar el contexto async y passlib correctamente.
Esta migración es un placeholder que mantiene la cadena de revisiones.
"""
from typing import Sequence, Union
from alembic import op

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Seed delegado al lifespan de FastAPI en app/main.py
    pass


def downgrade() -> None:
    pass
