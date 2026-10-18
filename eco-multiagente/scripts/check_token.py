"""Verifica tipo y permisos del token Meta. Ejecutar: railway run python scripts/check_token.py"""
import os, json, sys
from urllib.request import urlopen
from urllib.error import HTTPError

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
if not TOKEN:
    print("No hay token"); sys.exit(1)

print(f"Token (primeros 20): {TOKEN[:20]}...")
print(f"Longitud: {len(TOKEN)}")

def get(url):
    try:
        with urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()[:300]}

# Debug token
data = get(f"https://graph.facebook.com/v20.0/debug_token?input_token={TOKEN}&access_token={TOKEN}")
di = data.get("data") or data
print(f"\nTipo: {di.get('type')}")
print(f"App ID: {di.get('app_id')}")
print(f"User ID: {di.get('user_id')}")
print(f"Scopes: {di.get('scopes', [])}")
print(f"Profiles: {di.get('profile_ids', [])}")
print(f"Error: {di.get('error', {})}")
