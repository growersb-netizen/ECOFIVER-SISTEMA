"""Configuración común de pruebas del multiagente."""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _control_sin_red(request):
    """Por defecto el estado de agentes del CRM no está disponible (sin red en las pruebas):
    entrante se atiende, saliente no se envía. test_control_agentes.py lo controla explícitamente."""
    if request.node.get_closest_marker("control_real"):
        yield
        return
    from tools import control_agentes
    control_agentes._reset_para_tests()
    with patch.object(control_agentes, "_leer", AsyncMock(return_value=None)):
        yield


def pytest_configure(config):
    config.addinivalue_line("markers", "control_real: usa el control de agentes con un CRM simulado explícito")
