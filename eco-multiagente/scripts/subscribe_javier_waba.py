"""
Verifica y suscribe el WABA de Javier (1398647545019322) al Meta App de eco-multiagente
(app EcoFiver 1628184734950660) para que lleguen webhooks al bot.

Ejecutar con: railway run python scripts/subscribe_javier_waba.py
(desde el directorio eco-multiagente, con el proyecto Railway linkeado)
"""
import os, sys, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode

WABA_JAVIER = "1398647545019322"
META_APP_ID  = "1628184734950660"
API = "https://graph.facebook.com/v20.0"

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
if not TOKEN:
    print("ERROR: META_PAGE_ACCESS_TOKEN / WA_TOKEN no encontrada en entorno Railway")
    sys.exit(1)

def graph_get(path, params=None):
    qs = urlencode({**(params or {}), "access_token": TOKEN})
    with urlopen(f"{API}/{path}?{qs}", timeout=15) as r:
        return json.loads(r.read())

def graph_post(path, params=None):
    qs = urlencode({**(params or {}), "access_token": TOKEN})
    req = Request(f"{API}/{path}?{qs}", data=b"", method="POST")
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# 1. Verificar suscripciones actuales
try:
    data = graph_get(f"{WABA_JAVIER}/subscribed_apps").get("data", [])
    print(f"Apps suscritas al WABA {WABA_JAVIER}: {[a.get('id') for a in data]}")
    already = any(a.get("id") == META_APP_ID for a in data)
    if already:
        print(f"✓ WABA ya está suscrito al app {META_APP_ID}. No se necesita acción.")
        sys.exit(0)
except HTTPError as e:
    print(f"Error verificando suscripciones: {e.code} {e.read().decode()}")

# 2. Suscribir
print(f"Suscribiendo WABA {WABA_JAVIER} al app {META_APP_ID}...")
try:
    result = graph_post(f"{WABA_JAVIER}/subscribed_apps")
    print(f"Respuesta: {result}")
    if result.get("success"):
        print(f"✓ WABA suscrito correctamente.")
    else:
        print("✗ La API no confirmó éxito. Revisá el output arriba.")
        sys.exit(1)
except HTTPError as e:
    print(f"Error suscribiendo: {e.code} {e.read().decode()}")
    sys.exit(1)
