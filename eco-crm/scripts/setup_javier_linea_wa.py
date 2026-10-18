"""
Registra la línea WhatsApp de Javier Ruiz (AL-044) como MetaPagina en el CRM.
Ejecutar con: railway run python scripts/setup_javier_linea_wa.py
(desde el directorio eco-crm, con el proyecto Railway linkeado)
"""
import os, sys, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

CRM_URL = "https://eco-crm-production.up.railway.app"

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("ERROR: API_KEY no encontrada en entorno Railway")
    sys.exit(1)

payload = json.dumps({
    "nombre": "Aliados EcoFiver — Javier Ruiz",
    "numero": "5491176201171",
    "wa_phone_id": "910994205421879",
    "aliado_codigo": "AL-044",
    "vendedor_slug": "javier",
}).encode()

req = Request(
    f"{CRM_URL}/api/admin/lineas-wa",
    data=payload,
    method="POST",
    headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
)

try:
    with urlopen(req, timeout=15) as r:
        body = r.read().decode()
    print(f"HTTP 200: {body}")
    print("✓ MetaPagina de Javier registrada correctamente.")
    print("  wa_phone_id : 910994205421879")
    print("  aliado_codigo: AL-044")
except HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()}")
    print("✗ Error al registrar. Revisá el output de arriba.")
    sys.exit(1)
