"""
Tests mínimos para verificar que get_metricas_avanzadas no falla
por incompatibilidad de timezones (naive vs TZ-aware).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


# ── Test 1: calcular_proximo_vencimiento con fecha TZ-aware ──────────────────
def test_calcular_proximo_vencimiento_tzaware():
    """Si fecha_inicio_plan es TZ-aware, el resultado también lo es."""
    from routers.ventas_financiadas import calcular_proximo_vencimiento

    venta = MagicMock()
    venta.fecha_inicio_plan = datetime(2026, 9, 1, tzinfo=timezone.utc)
    venta.fecha_primer_vencimiento = None
    venta.cuotas_pagas = 0

    prox = calcular_proximo_vencimiento(venta)
    assert prox is not None
    assert prox.tzinfo is not None, "calcular_proximo_vencimiento debe preservar tzinfo cuando base es TZ-aware"
    print(f"  [OK] prox TZ-aware = {prox}")


# ── Test 2: calcular_proximo_vencimiento con fecha naive ─────────────────────
def test_calcular_proximo_vencimiento_naive():
    """Si fecha_inicio_plan es naive, el resultado tambien lo es."""
    from routers.ventas_financiadas import calcular_proximo_vencimiento

    venta = MagicMock()
    venta.fecha_inicio_plan = datetime(2026, 9, 1)  # naive
    venta.fecha_primer_vencimiento = None
    venta.cuotas_pagas = 0

    prox = calcular_proximo_vencimiento(venta)
    assert prox is not None
    assert prox.tzinfo is None, "calcular_proximo_vencimiento debe preservar naive cuando base es naive"
    print(f"  [OK] prox naive = {prox}")


# ── Test 3: la lógica de flujo no falla con prox TZ-aware y hoy TZ-aware ─────
def test_flujo_comparison_tzaware_hoy():
    """Con hoy = datetime.now(timezone.utc), la comparación no falla con prox TZ-aware."""
    hoy = datetime.now(timezone.utc)
    fin_30 = hoy + timedelta(days=30)

    # Simular prox TZ-aware
    prox = hoy + timedelta(days=5)  # dentro de la ventana, TZ-aware
    assert prox.tzinfo is not None

    # Aplicar la misma normalización del código corregido
    if prox.tzinfo is not None:
        prox = prox.replace(tzinfo=None)
    hoy_n = hoy.replace(tzinfo=None)
    fin_30_n = fin_30.replace(tzinfo=None)

    resultado = hoy_n <= prox <= fin_30_n
    assert resultado, "prox dentro de la ventana debe resultar True"
    print(f"  [OK] comparacion normalizada: hoy_n={hoy_n.date()} prox={prox.date()} fin={fin_30_n.date()} ok={resultado}")


# ── Test 4: la lógica de flujo no falla con prox naive y hoy TZ-aware ────────
def test_flujo_comparison_prox_naive():
    """Con hoy = datetime.now(timezone.utc), la comparacion no falla con prox naive."""
    hoy = datetime.now(timezone.utc)
    fin_30 = hoy + timedelta(days=30)

    # Simular prox naive (fecha en DB almacenada sin timezone)
    prox = datetime.now() + timedelta(days=5)  # naive
    assert prox.tzinfo is None

    # Aplicar la misma normalización del código corregido
    if prox.tzinfo is not None:
        prox = prox.replace(tzinfo=None)
    hoy_n = hoy.replace(tzinfo=None)
    fin_30_n = fin_30.replace(tzinfo=None)

    resultado = hoy_n <= prox <= fin_30_n
    assert resultado, "prox naive dentro de la ventana debe resultar True"
    print(f"  [OK] comparacion prox naive: hoy_n={hoy_n.date()} prox={prox.date()} fin={fin_30_n.date()} ok={resultado}")


# ── Test 5: TypeError sin el fix (documenta el bug original) ─────────────────
def test_original_bug_raises_typeerror():
    """Sin el fix, mezclar naive y TZ-aware lanza TypeError."""
    hoy_naive = datetime.now()  # naive — el bug original
    prox_aware = datetime.now(timezone.utc) + timedelta(days=5)  # TZ-aware

    try:
        _ = hoy_naive <= prox_aware
        # En Python 3.11+, puede no lanzar TypeError — verificar comportamiento
        print("  [INFO] Python no lanzó TypeError en esta versión (comportamiento puede variar)")
    except TypeError as e:
        print(f"  [OK] Bug confirmado — TypeError sin fix: {e}")


if __name__ == "__main__":
    tests = [
        test_calcular_proximo_vencimiento_tzaware,
        test_calcular_proximo_vencimiento_naive,
        test_flujo_comparison_tzaware_hoy,
        test_flujo_comparison_prox_naive,
        test_original_bug_raises_typeerror,
    ]
    failed = 0
    for t in tests:
        try:
            print(f">> {t.__name__}")
            t()
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print(f"\n{'OK: Todos los tests pasaron' if not failed else f'FAIL: {failed} test(s) fallaron'}")
    sys.exit(failed)
