"""
Verifica y suscribe los WABAs accesibles al Meta App EcoFiver.
Ejecutar: railway run python scripts/suscribir_wabas.py
"""
import os, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
APP_ID = "1628184734950660"
API = "https://graph.facebook.com/v20.0"

if not TOKEN:
    print("ERROR: token no encontrado"); exit(1)

# WABAs accesibles con META_PAGE_ACCESS_TOKEN
WABAS = [
    ("933806039223386",  "Danisa Diaz"),
    ("2280170016141749", "Tu Vivienda en Cuotas - Pablo"),
    ("1387556889776132", "Minipiscinas 2 - Pablo"),
    ("1398647545019322", "viviendas premium - Javier"),
]

print(f"App ID: {APP_ID}")
print("=" * 60)

for waba_id, name in WABAS:
    # Verificar estado
    try:
        url = f"{API}/{waba_id}/subscribed_apps?access_token={TOKEN}"
        with urlopen(Request(url), timeout=15) as r:
            data = json.loads(r.read())
        apps = data.get("data", [])
        suscripto = any(
            a.get("whatsapp_business_api_data", {}).get("id") == APP_ID
            for a in apps
        )
        if suscripto:
            print(f"OK  {name}: ya suscripto al app EcoFiver")
        else:
            print(f"SUB {name}: NO suscripto -> suscribiendo...")
            post_url = f"{API}/{waba_id}/subscribed_apps"
            post_req = Request(
                post_url,
                data=f"access_token={TOKEN}".encode(),
                method="POST",
            )
            with urlopen(post_req, timeout=15) as r2:
                result = json.loads(r2.read())
            print(f"    resultado: {result}")
    except HTTPError as e:
        print(f"ERR {name}: HTTP {e.code} - {e.read().decode()[:200]}")
