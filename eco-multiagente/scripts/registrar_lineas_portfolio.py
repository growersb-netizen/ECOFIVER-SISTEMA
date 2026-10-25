"""
Registra todas las líneas WA del portfolio en el CRM como MetaPaginas.
Ejecutar: railway run python scripts/registrar_lineas_portfolio.py

ESTADO (2026-10-18): phone_number_ids confirmados via WA Manager (12 líneas).
Aliados y slugs mapeados desde socios del CRM.
"""
import os, json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

CRM = "https://eco-crm-production.up.railway.app"
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("ERROR: API_KEY no encontrada"); exit(1)

# ─── Líneas del portfolio EcoFiver ────────────────────────────────────────────
# Formato: (phone_number_id, numero_wa, nombre_linea, aliado_codigo, vendedor_slug)
LINEAS = [
    # ── YA REGISTRADAS ────────────────────────────────────────────────────────
    # ("1562122100308561", "5491126036495",  "Eco Fiver — Melanie",            "AL-010", "melanie"),    # ya existe
    # ("910994205421879",  "5491176201171",  "Aliados EcoFiver — Javier Ruiz", "AL-044", "javier"),     # ya existe ✅

    # ── CONFIRMADAS: aliado + slug verificados ─────────────────────────────────
    ("645112352027194",  "5493813500329",  "Viviendas Argentinas — Oscar Juárez",    "AL-035", "oscar"),
    ("1383774158147416", "5491122985977",  "EcoFiver Módulos y Piscinas — Rodrigo",  "AL-002", "rodrigo"),
    ("1407320592455703", "5492477674404",  "Ayres Minipiscinas — Danisa Díaz",       "AL-022", "danisa"),
    ("1075383802328082", "5492477512843",  "Consultoría y Asesoría — Danisa Díaz",   "AL-022", "danisa"),
    ("1314857888374443", "5491162692583",  "EcoFiver Piscinas y Módulos — Carlos O", "AL-009", "carlos_o"),

    # ── DUEÑO CONOCIDO, sin aliado_codigo (no están en socios aún) ────────────
    # Registrar con slug → silencia bot + asigna lead; agregar aliado después si corresponde
    ("1443033858886105", "5491140831537",  "EcoFiver Minipiscinas — Tamy",           "",       "tamy"),
    ("1301960096341669", "5491122752412",  "Coim — Sergio Fernández",                "",       "sergio"),
    ("940796132455079",  "5491136420072",  "Piscinas Madero — Lucas Caballero",      "",       "lucas"),
    ("1278822558656650", "5491126202769",  "Tu Vivienda en Cuotas — Pablo C.",       "",       "pablo_v"),
    ("1012820438580701", "5491151788503",  "EcoFiver Minipiscinas 2 — Pablo C.",     "",       "pablo_p"),

    # ── CONFIRMADA (Juan Ciapessoni) ─────────────────────────────────────────
    ("683000601553770",  "5491125068342",  "Viviendas Premium — Juan Ciapessoni",   "",       "juan_c"),
]

# ─── Registro en CRM ──────────────────────────────────────────────────────────
print(f"Registrando {len(LINEAS)} línea(s) en el CRM...\n")
ok = 0
for phone_id, numero, nombre, aliado, vendedor in LINEAS:
    payload = json.dumps({
        "nombre": nombre,
        "numero_whatsapp": numero,   # clave correcta según admin_crear_linea_wa
        "wa_phone_id": phone_id,
        "aliado_codigo": aliado or "",
        "vendedor_slug": vendedor or "",
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
            print(f"  OK {nombre}: {resp.get('accion', resp)}")
            ok += 1
    except HTTPError as e:
        err = e.read().decode()[:300]
        print(f"  ERR {nombre}: HTTP {e.code} - {err}")

print(f"\nTotal registradas: {ok}/{len(LINEAS)}")
