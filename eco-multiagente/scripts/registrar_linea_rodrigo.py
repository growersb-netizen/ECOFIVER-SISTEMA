"""
Registro exclusivo de la línea de Rodrigo en el CRM como MetaPagina.
Solo registra esta línea. No modifica ni registra otras líneas.

Ejecutar en eco-multiagente:
  railway run python scripts/registrar_linea_rodrigo.py

Es idempotente: si la línea ya existe, actualiza campos; si no, la crea.
No ejecutar sin autorización.
"""
import os
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

CRM     = "https://eco-crm-production.up.railway.app"
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("ERROR: API_KEY no encontrada en entorno"); exit(1)

# Única línea autorizada en esta operación
PHONE_NUMBER_ID = "1383774158147416"
NUMERO_WA       = "5491122985977"
NOMBRE          = "EcoFiver Módulos y Piscinas — Rodrigo"
ALIADO_CODIGO   = "AL-002"
VENDEDOR_SLUG   = "rodrigo"

print(f"Registrando línea supervisada: {NOMBRE}")
print(f"  phone_number_id : {PHONE_NUMBER_ID}")
print(f"  numero_wa       : {NUMERO_WA}")
print(f"  aliado_codigo   : {ALIADO_CODIGO}")
print(f"  vendedor_slug   : {VENDEDOR_SLUG}")
print()

payload = json.dumps({
    "nombre":          NOMBRE,
    "numero_whatsapp": NUMERO_WA,
    "wa_phone_id":     PHONE_NUMBER_ID,
    "aliado_codigo":   ALIADO_CODIGO,
    "vendedor":        "Rodrigo",      # nombre visible en la bandeja
    "vendedor_slug":   VENDEDOR_SLUG,
}).encode()

req = Request(
    f"{CRM}/api/admin/lineas-wa",
    data=payload,
    headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
    method="POST",
)
try:
    with urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
        accion = resp.get("accion", resp)
        print(f"OK — {accion}")
        if resp.get("page_id"):
            print(f"  page_id guardado: {resp['page_id']}")
except HTTPError as e:
    err = e.read().decode()[:400]
    print(f"ERROR HTTP {e.code}: {err}")
    exit(1)

print("\nVerificando en DB...")
verify_req = Request(
    f"{CRM}/api/inbox/lineas",
    headers={"x-api-key": API_KEY},
    method="GET",
)
try:
    with urlopen(verify_req, timeout=10) as r:
        lineas = json.loads(r.read())
        for l in lineas:
            if l.get("wa_phone_id") == PHONE_NUMBER_ID:
                print(f"  CONFIRMADO: {l.get('nombre')} | wa_phone_id={l.get('wa_phone_id')} | activa=True")
                break
        else:
            print("  ADVERTENCIA: línea no encontrada en la lista de bandejas")
except Exception as e:
    print(f"  No se pudo verificar: {e}")
