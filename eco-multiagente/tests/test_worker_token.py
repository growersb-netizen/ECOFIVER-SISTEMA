"""El multiagente envía el token del Worker de Cloudflare cuando está configurado."""
from tools import cloudflare_client as cf


def test_sin_token_no_envia_encabezado(monkeypatch):
    for k in ("ECO_WORKER_TOKEN", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert cf._headers_worker() == {}


def test_con_token_envia_bearer(monkeypatch):
    monkeypatch.setenv("ECO_WORKER_TOKEN", "t0k")
    assert cf._headers_worker() == {"Authorization": "Bearer t0k"}
