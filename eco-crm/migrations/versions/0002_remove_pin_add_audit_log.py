"""remove pin from aliados, add audit_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op as _op
    from sqlalchemy import inspect as _ins

    bind = _op.get_bind()
    inspector = _ins(bind)
    columns = {c["name"] for c in inspector.get_columns("aliados")}
    tables = set(inspector.get_table_names())

    # Drop pin only if it still exists (fresh PG via 0001 create_all won't have it)
    if "pin" in columns:
        with op.batch_alter_table("aliados") as batch_op:
            batch_op.drop_column("pin")

    # Create audit_logs only if it doesn't exist yet
    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("table_name", sa.String(100), nullable=False, index=True),
            sa.Column("record_id", sa.Integer(), nullable=True, index=True),
            sa.Column("action", sa.String(10), nullable=False),
            sa.Column("changed_fields", sa.Text(), nullable=True),
            sa.Column("usuario_id", sa.Integer(), nullable=True),
            sa.Column("usuario_nombre", sa.String(150), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                index=True,
            ),
        )


def downgrade() -> None:
    from alembic import op as _op
    from sqlalchemy import inspect as _ins

    bind = _op.get_bind()
    inspector = _ins(bind)
    tables = set(inspector.get_table_names())

    if "audit_logs" in tables:
        op.drop_table("audit_logs")
    with op.batch_alter_table("aliados") as batch_op:
        batch_op.add_column(sa.Column("pin", sa.String(12), nullable=True))
