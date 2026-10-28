"""
Lista todas las MetaPaginas/líneas WA registradas en el CRM.
Ejecutar: railway run python scripts/listar_lineas_wa.py
"""
import os, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

API_KEY = os.getenv("API_KEY", "")
CRM = "https://eco-crm-production.up.railway.app"

req = Request(f"{CRM}/api/admin/lineas-wa",
              headers={"x-api-key": API_KEY})
try:
    with urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
except HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()}"); exit(1)

lineas = data.get("lineas", [])
print(f"{'page_id':<25} {'wa_phone_id':<22} {'numero':<20} {'nombre':<35} {'aliado':<10} {'activa'}")
print("-" * 120)
for l in lineas:
    print(f"{str(l.get('page_id','')):<25} {str(l.get('wa_phone_id','')):<22} {str(l.get('numero_whatsapp','')):<20} {str(l.get('nombre','')):<35} {str(l.get('aliado_codigo','')):<10} {l.get('activa')}")
print(f"\nTotal: {len(lineas)}")
