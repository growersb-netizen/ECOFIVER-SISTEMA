"""
Movimientos de stock atómicos.

Antes se leía el stock, se restaba en Python y se guardaba: dos ventas
simultáneas de la última unidad leían 1, ambas "descontaban" y el stock quedaba
en 0 con dos unidades vendidas. Acá el control y el descuento son una sola
sentencia UPDATE ... WHERE cantidad >= n (PostgreSQL bloquea la fila hasta el
commit; SQLite serializa la escritura).
"""
from __future__ import annotations

import math


def _cantidad_valida(cantidad) -> bool:
    try:
        c = float(cantidad)
    except (TypeError, ValueError):
        return False
    return math.isfinite(c) and c > 0


def descontar(db, modelo, id_, columna: str, cantidad) -> bool:
    """Resta `cantidad` solo si alcanza. True si se descontó."""
    if not _cantidad_valida(cantidad):
        return False
    col = getattr(modelo, columna)
    n = (db.query(modelo)
         .filter(modelo.id == id_, col >= cantidad)
         .update({col: col - cantidad}, synchronize_session=False))
    return n == 1


def sumar(db, modelo, id_, columna: str, cantidad) -> bool:
    if not _cantidad_valida(cantidad):
        return False
    col = getattr(modelo, columna)
    n = (db.query(modelo).filter(modelo.id == id_)
         .update({col: col + cantidad}, synchronize_session=False))
    return n == 1
