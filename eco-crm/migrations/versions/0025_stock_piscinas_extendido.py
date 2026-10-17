"""Extiende stock_piscinas con categoría/ubicación y carga stock inicial 13/10

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("stock_piscinas")}

    if "categoria" not in cols:
        op.add_column("stock_piscinas", sa.Column("categoria", sa.String(50), nullable=True, server_default="AUTOPORTANTE"))

    if "ubicacion" not in cols:
        op.add_column("stock_piscinas", sa.Column("ubicacion", sa.String(100), nullable=True))

    if "disponible" not in cols:
        op.add_column("stock_piscinas", sa.Column("disponible", sa.Boolean(), nullable=True, server_default="true"))

    if "notas" not in cols:
        op.add_column("stock_piscinas", sa.Column("notas", sa.Text(), nullable=True))

    # Limpiar stock viejo y cargar datos frescos del snapshot 13/10/2026
    bind.execute(sa.text("DELETE FROM stock_piscinas"))

    items = [
        # (categoria, modelo, color, cantidad, ubicacion, notas)
        # ── PILETAS DE POZO ──────────────────────────────────────────
        ("POZO", "Pileta con ondas en el ala", "Celeste", 1, "Showroom", None),
        ("POZO", "Playa Húmeda 5.20", "Beige", 1, "Afuera", None),
        ("POZO", "Pileta riñón", "Celeste", 1, "Afuera", None),
        ("POZO", "Arco Romano 7x3", "Celeste", 1, "Afuera", None),
        ("POZO", "Minimalista chica 3.97", "Blanca", 1, "Showroom", "Ingresada 29/9"),
        ("POZO", "Arco Romano 6.45x2.92x140 asiento 50cm", "Verde", 1, "Showroom", None),
        ("POZO", "Arco Romano 4.60", "Verde", 1, "Showroom", None),
        ("POZO", "Playa Húmeda 5.20", "Blanca", 1, "Showroom", None),
        ("POZO", "Playa Húmeda 5.20", "Azul", 1, "Showroom", None),
        ("POZO", "Arco Romano 7x3", "Blanca", 1, "Showroom", None),
        # ── AUTOPORTANTE ─────────────────────────────────────────────
        ("AUTOPORTANTE", "Autoportante", "Azul", 6, "Showroom", None),
        ("AUTOPORTANTE", "Autoportante", "Verde", 5, "Showroom", None),
        ("AUTOPORTANTE", "Autoportante", "Blanca", 1, "Paso del Rey", None),
        ("AUTOPORTANTE", "Autoportante", "Gris", 1, "Showroom", None),
        ("AUTOPORTANTE", "Autoportante", "Blanca", 1, "Showroom", None),
        ("AUTOPORTANTE", "Autoportante", "Beige", 1, "Showroom", None),
        # ── MINIPORTANTE ─────────────────────────────────────────────
        ("MINIPORTANTE", "Miniportante", "Beige", 1, "Paso del Rey", None),
        ("MINIPORTANTE", "Miniportante", "Verde", 8, "Showroom", None),
        ("MINIPORTANTE", "Miniportante", "Azul", 1, "Showroom", None),
        ("MINIPORTANTE", "Miniportante", "Beige", 2, "Showroom", None),
        ("MINIPORTANTE", "Miniportante", "Blanca", 1, "Showroom", None),
        # ── MINI DECK ────────────────────────────────────────────────
        ("MINI_DECK", "Mini Deck 3x2", "Beige", 1, "Showroom", None),
        ("MINI_DECK", "Mini Deck 3x2", "Azul", 2, "Showroom", None),
        ("MINI_DECK", "Mini Deck 3x2", "Verde", 3, "Showroom", None),
        ("MINI_DECK", "Mini Deck 3x2", "Gris", 1, "Showroom", None),
        ("MINI_DECK", "Mini Deck 3x2", "Celeste", 1, "Showroom", None),
        ("MINI_DECK", "Mini Deck 3x2", "Blanca", 1, "Showroom", None),
        # ── PLAYA HÚMEDA ADICIONAL ───────────────────────────────────
        ("PLAYA_ADICIONAL", "Playa Húmeda Adicional", "Azul", 2, "Showroom", None),
        # ── HIDROMASAJES ─────────────────────────────────────────────
        ("HIDROMASAJE", "Hidromasaje", "Varios", 30, "Showroom", "30 en total"),
        # ── REPOSERAS ────────────────────────────────────────────────
        ("REPOSERA", "Reposera", "Verde", 3, "Showroom", None),
        ("REPOSERA", "Reposera", "Blanca", 1, "Showroom", None),
        ("REPOSERA", "Reposera", "Azul", 1, "Showroom", None),
    ]

    for (cat, modelo, color, cant, ubic, notas) in items:
        bind.execute(sa.text(
            "INSERT INTO stock_piscinas (categoria, modelo, color, cantidad, ubicacion, disponible, notas) "
            "VALUES (:cat, :modelo, :color, :cant, :ubic, true, :notas)"
        ), {"cat": cat, "modelo": modelo, "color": color, "cant": cant, "ubic": ubic, "notas": notas})


def downgrade() -> None:
    pass
