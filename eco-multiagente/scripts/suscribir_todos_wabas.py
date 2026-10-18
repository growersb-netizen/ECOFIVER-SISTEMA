"""
Suscribe TODOS los WABAs del portfolio al Meta App EcoFiver (1628184734950660).
Ejecutar: railway run python scripts/suscribir_todos_wabas.py
"""
import os, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
APP_ID = "1628184734950660"
API = "https://graph.facebook.com/v20.0"

if not TOKEN:
    print("ERROR: token no encontrado"); exit(1)

# Todos los WABAs del portfolio EcoFiver
WABAS = [
    # Ya suscritos (confirmar estado)
    ("1398647545019322", "viviendas premium — Javier"),
    ("933806039223386",  "Danisa Diaz"),
    ("2280170016141749", "Tu Vivienda en Cuotas — Pablo"),
    ("1387556889776132", "Minipiscinas 2 — Pablo"),
    # Pendientes
    ("1796656051377246", "Ecofiver Minipiscinas — Tamy"),
    ("1723517492280253", "Coim — Sergio"),
    ("2701119493560346", "eco — Lucas"),
    ("922734570744974",  "Consultoría y Asesoría — Danisa 2"),
    ("1649923632173086", "EcoFiver — Oscar"),
    ("9418541518266944", "Viviendas y Piscinas — Juan"),
    ("1000841459644155", "EcoFiver Módulos y Piscinas — Rodrigo"),
]

print(f"Suscribiendo WABAs al App {APP_ID}...")
print("=" * 65)

ok = 0
fail = 0
for waba_id, name in WABAS:
    url = f"{API}/{waba_id}/subscribed_apps"
    data = f"access_token={TOKEN}".encode()
    try:
        with urlopen(Request(url, data=data, method="POST"), timeout=15) as r:
            result = json.loads(r.read())
        if result.get("success"):
            print(f"  OK  {name}")
            ok += 1
        else:
            print(f"  ??  {name}: {result}")
    except HTTPError as e:
        err = e.read().decode()[:150]
        print(f"  ERR {name}: HTTP {e.code} — {err}")
        fail += 1

print(f"\nOK: {ok}  |  Errores: {fail}/{len(WABAS)}")
