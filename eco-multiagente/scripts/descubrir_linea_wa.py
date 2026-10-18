"""
Descubre el Phone Number ID y WABA ID de un número WhatsApp dado.
Ejecutar: railway run python scripts/descubrir_linea_wa.py +5491164569907
"""
import os, sys, json
from urllib.request import urlopen
from urllib.parse import urlencode

API = "https://graph.facebook.com/v20.0"
OUT_FILE = os.path.join(os.path.dirname(__file__), "inventario_lineas_wa.json")

# WABAs conocidos del negocio EcoFiver (business_id 753481671171165)
WABAS = [
    ("1796656051377246", "Ecofiver Minipiscinas (principal)"),
    ("1398647545019322", "viviendas y piscinas premium (Javier)"),
]

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
if not TOKEN:
    print("ERROR: token no encontrado"); sys.exit(1)

def get(path, **kw):
    qs = urlencode({"access_token": TOKEN, **kw})
    with urlopen(f"{API}/{path}?{qs}", timeout=15) as r:
        return json.loads(r.read())

inventario = []
print("=" * 70)
print("INVENTARIO COMPLETO DE LÍNEAS WHATSAPP")
print("=" * 70)

for waba_id, waba_name in WABAS:
    print(f"\nWABA {waba_id} — {waba_name}")
    print("-" * 60)
    try:
        # Suscripciones de esta WABA
        subs = get(f"{waba_id}/subscribed_apps")
        sub_ids = [a.get("id") for a in subs.get("data", [])]
        print(f"  Apps suscritas: {sub_ids or 'ninguna'}")

        # Números de teléfono
        phones = get(
            f"{waba_id}/phone_numbers",
            fields="id,display_phone_number,verified_name,code_verification_status,quality_rating,platform_type"
        )
        for p in phones.get("data", []):
            print(f"  phone_id: {p['id']}")
            print(f"    número : {p.get('display_phone_number')}")
            print(f"    nombre : {p.get('verified_name')}")
            print(f"    calidad: {p.get('quality_rating')}")
            print()
            inventario.append({
                "waba_id": waba_id,
                "waba_name": waba_name,
                "phone_number_id": p["id"],
                "display_phone_number": p.get("display_phone_number"),
                "verified_name": p.get("verified_name"),
                "quality_rating": p.get("quality_rating"),
                "waba_subscribed_apps": sub_ids,
            })
    except Exception as e:
        print(f"  ERROR: {e}")

# Guardar resultado
with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(inventario, f, ensure_ascii=False, indent=2)

print("=" * 70)
print(f"Total líneas encontradas: {len(inventario)}")
print(f"Guardado en: {OUT_FILE}")
print("=" * 70)
