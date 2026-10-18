"""
Verifica el estado del webhook del Meta App y la suscripción del WABA de Javier.
Ejecutar: railway run python scripts/check_webhook_status.py
"""
import os, json
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
APP_ID = "1628184734950660"
WABA_JAVIER = "1398647545019322"
API = "https://graph.facebook.com/v20.0"

def get(path, **kw):
    qs = urlencode({"access_token": TOKEN, **kw})
    try:
        with urlopen(f"{API}/{path}?{qs}", timeout=15) as r:
            return json.loads(r.read()), None
    except HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:400]}"

# 1. Webhook subscriptions del app
print("=== App subscriptions (fields suscriptos al webhook) ===")
data, err = get(f"{APP_ID}/subscriptions")
if err:
    print(f"Error: {err}")
else:
    for s in (data or {}).get("data", []):
        print(f"  object={s.get('object')} | active={s.get('active')} | fields={s.get('fields')}")

# 2. WABAs suscritas al app
print("\n=== WABAs suscritas al app ===")
data2, err2 = get(f"{APP_ID}/whatsapp_business_accounts")
if err2:
    print(f"  Error (esperado si no hay permisos): {err2}")
else:
    for w in (data2 or {}).get("data", []):
        print(f"  {w.get('id')} — {w.get('name')}")

# 3. Estado subscripción WABA Javier
print("\n=== Subscribed apps del WABA de Javier ===")
data3, err3 = get(f"{WABA_JAVIER}/subscribed_apps")
if err3:
    print(f"Error: {err3}")
else:
    print(json.dumps(data3, indent=2))
