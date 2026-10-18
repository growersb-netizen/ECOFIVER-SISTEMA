"""
Inventario completo de líneas WhatsApp de EcoFiver.
Intenta varios métodos para encontrar todas las líneas del portfolio.
Ejecutar: railway run python scripts/inventario_completo_wa.py
"""
import os, sys, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode

API = "https://graph.facebook.com/v20.0"
OUT = os.path.join(os.path.dirname(__file__), "inventario_lineas_wa.json")

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN")
if not TOKEN:
    print("ERROR: token no encontrado"); sys.exit(1)

def get(path, **kw):
    qs = urlencode({"access_token": TOKEN, **kw})
    try:
        with urlopen(f"{API}/{path}?{qs}", timeout=15) as r:
            return json.loads(r.read()), None
    except HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:300]}"

# ─── Método 1: /me → businesses → WABAs ──────────────────────────────────────
print("Método 1: /me → businesses → WABAs")
me, err = get("me", fields="id,name,businesses{id,name,whatsapp_business_accounts{id,name,phone_numbers{id,display_phone_number,verified_name}}}")
if err:
    print(f"  Error: {err}")
else:
    for biz in (me or {}).get("businesses", {}).get("data", []):
        for waba in biz.get("whatsapp_business_accounts", {}).get("data", []):
            print(f"\n  WABA {waba['id']} ({waba.get('name')})")
            for p in waba.get("phone_numbers", {}).get("data", []):
                print(f"    {p['id']} | {p.get('display_phone_number')} | {p.get('verified_name')}")

# ─── Método 2: WABAs conocidos directamente ───────────────────────────────────
WABAS = [
    ("1796656051377246", "Ecofiver Minipiscinas (principal)"),
    ("1398647545019322", "viviendas y piscinas premium (Javier)"),
]

inventario = []

print("\n" + "=" * 70)
print("Método 2: WABAs directos")

for waba_id, waba_label in WABAS:
    print(f"\nWABA {waba_id} — {waba_label}")

    # Info del WABA
    waba_info, err = get(waba_id, fields="id,name,currency,timezone_id,message_template_namespace")
    if err:
        print(f"  WABA info error: {err}")
    else:
        print(f"  Nombre: {waba_info.get('name')}")

    # Phone numbers (intento 1: edge directa)
    phones, err1 = get(f"{waba_id}/phone_numbers",
                        fields="id,display_phone_number,verified_name,code_verification_status,quality_rating")
    if err1:
        print(f"  phone_numbers edge error: {err1}")
        # intento 2: via fields en el WABA
        waba_phones, err2 = get(waba_id,
            fields="phone_numbers{id,display_phone_number,verified_name,quality_rating}")
        if err2:
            print(f"  phone_numbers field error: {err2}")
        else:
            phones = waba_phones.get("phone_numbers") if waba_phones else None

    if phones:
        subs_data, _ = get(f"{waba_id}/subscribed_apps")
        sub_ids = [a.get("id") for a in (subs_data or {}).get("data", []) if a.get("id")]

        for p in (phones.get("data") if isinstance(phones, dict) else phones or []):
            print(f"  ✓ {p['id']} | {p.get('display_phone_number')} | {p.get('verified_name')}")
            inventario.append({
                "waba_id": waba_id,
                "waba_name": waba_label,
                "phone_number_id": p["id"],
                "display_phone_number": p.get("display_phone_number"),
                "verified_name": p.get("verified_name"),
                "quality_rating": p.get("quality_rating"),
                "waba_subscribed_apps": sub_ids,
            })

# ─── Guardar ──────────────────────────────────────────────────────────────────
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(inventario, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 70)
print(f"Total líneas encontradas: {len(inventario)}")
print(f"Guardado en: {OUT}")
for entry in inventario:
    print(f"  {entry['phone_number_id']} | {entry['display_phone_number']} | {entry['verified_name']}")
