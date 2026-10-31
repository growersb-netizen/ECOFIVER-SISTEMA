"""Fallas de entrega informadas por Meta: se cuentan (antes solo quedaban en el log)."""
import os

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import entregas_wa


def test_cuenta_entregas_y_fallas_por_codigo():
    entregas_wa._stats.update(por_estado={}, fallas_por_codigo={}, ultima_falla=None)
    entregas_wa.registrar_estado({"status": "sent"})
    entregas_wa.registrar_estado({"status": "delivered"})
    entregas_wa.registrar_estado({"status": "failed", "errors": [{"code": 131047, "title": "Re-engagement message"}]})
    s = entregas_wa.stats()
    assert s["por_estado"] == {"sent": 1, "delivered": 1, "failed": 1}
    assert s["fuera_de_ventana_24h"] == 1 and "plantilla" in s["ultima_falla"]["descripcion"]
    assert "phone" not in str(s)


def test_endpoint_publico_sin_datos_personales():
    from fastapi.testclient import TestClient
    import main
    d = TestClient(main.app).get("/health/whatsapp").json()
    assert {"entregas", "salientes_autorizacion"} <= set(d)
