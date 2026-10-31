"""[COTIZAR:...] en la conversación: el precio lo pone el CRM, nunca el modelo de IA."""
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import cotizador


@pytest.mark.asyncio
async def test_reemplaza_por_precio_final_unico():
    q = {"ok": True, "precio_final": 2670000, "interno": {"flete_bruto": 180000}}
    with patch.object(cotizador, "_cotizar", AsyncMock(return_value=q)) as c:
        out = await cotizador.procesar_cotizaciones(
            "La Minideck en Pilar te queda en [COTIZAR:Minideck|Pilar|Buenos Aires], todo incluido.", "camila")
    assert out == "La Minideck en Pilar te queda en $2.670.000, todo incluido."
    assert "180" not in out                                              # no se desglosa el traslado
    assert c.await_args.args == ("camila", "Minideck", "Pilar", "Buenos Aires", "")


@pytest.mark.asyncio
async def test_informa_promocion_con_condicion_de_reserva():
    q = {"ok": True, "precio_final": 2670000,
         "promocion_disponible": {"precio_final_con_promocion": 2580000, "hasta": "2026-11-07"}}
    with patch.object(cotizador, "_cotizar", AsyncMock(return_value=q)):
        out = await cotizador.procesar_cotizaciones("Te queda en [COTIZAR:Minideck|Pilar].", "camila")
    assert "$2.670.000" in out and "$2.580.000 si reservás la fecha de instalación" in out and "07/11" in out


@pytest.mark.asyncio
async def test_sin_distancia_verificada_no_inventa_y_avisa():
    q = {"ok": False, "motivo": "distancia_no_disponible", "detalle": "Falla del proveedor para 'Bariloche'"}
    with patch.object(cotizador, "_cotizar", AsyncMock(return_value=q)), \
         patch.object(cotizador, "_avisar_equipo", AsyncMock()) as aviso:
        out = await cotizador.procesar_cotizaciones("Te queda en [COTIZAR:Minideck|Bariloche|Río Negro].", "camila")
    assert "$" not in out and "te confirmo el precio final" in out
    assert "Bariloche" in aviso.await_args.args[0]


@pytest.mark.asyncio
async def test_crm_caido_no_inventa():
    with patch.object(cotizador, "_cotizar", AsyncMock(side_effect=RuntimeError("503"))):
        out = await cotizador.procesar_cotizaciones("Queda en [COTIZAR:Minideck|Pilar].", "camila")
    assert "$" not in out and "[COTIZAR" not in out


@pytest.mark.asyncio
async def test_sin_senal_no_toca_nada():
    with patch.object(cotizador, "_cotizar", AsyncMock()) as c:
        assert await cotizador.procesar_cotizaciones("Hola, ¿qué modelo te interesa?", "camila") == "Hola, ¿qué modelo te interesa?"
    c.assert_not_awaited()


def test_camila_tiene_las_reglas_del_flujo():
    from agents.camila import _SYSTEM_PROMPT as p
    for regla in ("[COTIZAR:", "NO desgloses el traslado", "UN SOLO PRECIO FINAL", "RESERVA LA FECHA DE INSTALACIÓN",
                  "No hace falta seña", "4,10 m", "Garantía de 10 años", "cerrar_venta_contado",
                  "fecha_entrega_solicitada", "pendiente de entrega y cobro", "excavación"):
        assert regla in p, regla
    from tools.crm_context import AGENT_CRM_NEEDS
    assert "flete" not in AGENT_CRM_NEEDS["Camila"]


@pytest.mark.asyncio
async def test_localidad_ambigua_pregunta_la_provincia():
    q = {"ok": False, "motivo": "localidad_ambigua", "candidatos": ["Buenos Aires", "Córdoba"]}
    with patch.object(cotizador, "_cotizar", AsyncMock(return_value=q)), \
         patch.object(cotizador, "_avisar_equipo", AsyncMock()) as aviso:
        out = await cotizador.procesar_cotizaciones("Te queda en [COTIZAR:Minideck|Pilar].", "camila")
    assert "¿Pilar de Buenos Aires o Córdoba?" in out and "$" not in out
    aviso.assert_not_awaited()


@pytest.mark.asyncio
async def test_direccion_exacta_se_envia():
    with patch.object(cotizador, "_cotizar", AsyncMock(return_value={"ok": True, "precio_final": 1})) as c:
        await cotizador.procesar_cotizaciones("[COTIZAR:Minideck|Campana|Buenos Aires|Belgrano 123]", "camila")
    assert c.await_args.args == ("camila", "Minideck", "Campana", "Buenos Aires", "Belgrano 123")
