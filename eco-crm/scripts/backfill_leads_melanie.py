"""
Backfill leads históricos de la línea Melanie (1126036495).

Para cada número único que tiene mensajes con wa_linea = WA_PHONE_ID_MELANIE
y no tiene Lead en el CRM, crea el Lead con:
  - modo_atencion = humano
  - agente_asignado = melanie
  - utm_source = meta / utm_medium = ads
  - estado = NUEVO

Ejecutar en Railway:
  python scripts/backfill_leads_melanie.py
  python scripts/backfill_leads_melanie.py --dry-run   (solo cuenta, no crea)
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database.database import SessionLocal
from database.models import Lead, InboxMensaje

WA_PHONE_ID_MELANIE = "1562122100308561"


def run(dry_run: bool = False):
    db = SessionLocal()
    try:
        # Números únicos con mensajes en línea Melanie
        rows = (
            db.query(InboxMensaje.phone, InboxMensaje.nombre_contacto)
            .filter(
                InboxMensaje.wa_linea == WA_PHONE_ID_MELANIE,
                InboxMensaje.direccion == "IN",
            )
            .distinct(InboxMensaje.phone)
            .all()
        )

        # Deduplicar — distinct puede traer múltiples filas por phone si nombre varía
        phones: dict[str, str] = {}
        for phone, nombre in rows:
            if phone not in phones:
                phones[phone] = nombre or phone

        print(f"Números únicos con mensajes en línea Melanie: {len(phones)}")

        creados = 0
        ya_existia = 0

        for phone, nombre in phones.items():
            # Buscar lead existente por teléfono (últimos 9 dígitos)
            lead = db.query(Lead).filter(Lead.telefono.contains(phone[-9:])).first()
            if lead:
                ya_existia += 1
                # Corregir modo si está en bot
                if lead.modo_atencion != "humano" and not dry_run:
                    lead.modo_atencion = "humano"
                    lead.agente_asignado = "melanie"
                    db.commit()
                    print(f"  ✓ Corregido a humano: {phone} ({lead.nombre})")
                continue

            creados += 1
            print(f"  {'[DRY]' if dry_run else '+'} Lead nuevo: {phone} — {nombre}")
            if not dry_run:
                new_lead = Lead(
                    nombre=nombre,
                    telefono=phone,
                    origen="WHATSAPP",
                    utm_source="meta",
                    utm_medium="ads",
                    modo_atencion="humano",
                    agente_asignado="melanie",
                    estado="NUEVO",
                )
                db.add(new_lead)

                # Vincular mensajes existentes al nuevo lead
                db.flush()
                db.query(InboxMensaje).filter(
                    InboxMensaje.phone == phone,
                    InboxMensaje.lead_id.is_(None),
                ).update({"lead_id": new_lead.id})
                db.commit()

        print(f"\nResumen:")
        print(f"  Leads nuevos creados : {creados}")
        print(f"  Ya tenían lead       : {ya_existia}")
        if dry_run:
            print("  (modo dry-run — no se escribió nada)")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo contar, no crear")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
