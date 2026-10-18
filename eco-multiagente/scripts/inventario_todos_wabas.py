"""
Inventario completo: consulta phone_numbers para TODOS los WABAs de EcoFiver.
WABAs obtenidos del WA Manager (10/10/2026).
Ejecutar: railway run python scripts/inventario_todos_wabas.py
"""
import os, sys, json
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

API = "https://graph.facebook.com/v20.0"
TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
if not TOKEN:
    print("ERROR: token no encontrado"); sys.exit(1)

WABAS = [
    ("1796656051377246", "Ecofiver Minipiscinas"),
    ("1723517492280253", "Coim"),
    ("2701119493560346", "eco"),
    ("922734570744974",  "consultoria y asesoría"),
    ("1649923632173086", "EcoFiver"),
    ("9418541518266944", "viviendas y puscinas"),
    ("1000841459644155", "Ecofiver Módulos y Piscinas"),
    ("933806039223386",  "Danisa Diaz"),
    ("2280170016141749", "Tu Vivienda en Cuotas"),
    ("1387556889776132", "Ecofiver Minipiscinas (2)"),
    ("1398647545019322", "viviendas y piscinas premium — Javier"),
]

def get(path, **kw):
    qs = urlencode({"access_token": TOKEN, **kw})
    try:
        with urlopen(f"{API}/{path}?{qs}", timeout=15) as r:
            return json.loads(r.read()), None
    except HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"

inventario = []
print("=" * 75)
print("INVENTARIO COMPLETO LÍNEAS WHATSAPP — TODOS LOS WABAs")
print("=" * 75)

for waba_id, waba_name in WABAS:
    print(f"\n[WABA {waba_id}] {waba_name}")
    phones, err = get(f"{waba_id}/phone_numbers",
                      fields="id,display_phone_number,verified_name,quality_rating")
    if err:
        print(f"  ERROR: {err}")
        continue
    for p in phones.get("data", []):
        pid = p["id"]
        num = p.get("display_phone_number", "")
        name = p.get("verified_name", "")
        quality = p.get("quality_rating", "")
        print(f"  phone_id: {pid}  |  {num}  |  {name}  |  calidad: {quality}")
        inventario.append({
            "waba_id": waba_id,
            "waba_name": waba_name,
            "phone_number_id": pid,
            "display_phone_number": num,
            "verified_name": name,
        })

OUT = os.path.join(os.path.dirname(__file__), "inventario_lineas_wa.json")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(inventario, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 75)
print(f"Total líneas encontradas: {len(inventario)}")
print(f"Guardado en: {OUT}")
print("=" * 75)
