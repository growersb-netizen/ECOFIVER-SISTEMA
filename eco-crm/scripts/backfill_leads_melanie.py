"""
Backfill leads históricos de la línea Melanie (1126036495).

Estrategia:
  - Mensajes con wa_linea = WA_PHONE_ID_MELANIE  → definitivamente Melanie
  - Mensajes con wa_linea IS NULL                → históricos pre-fix, casi todos Melanie
    (la línea de agentes tiene muy pocos mensajes y los que tiene son recientes)

Para cada número único sin Lead crea uno con:
  modo_atencion=humano, agente_asignado=melanie, utm_source=meta, utm_medium=ads

Uso:
  python scripts/backfill_leads_melanie.py            # ejecuta
  python scripts/backfill_leads_melanie.py --dry-run  # solo muestra, no escribe
  python scripts/backfill_leads_melanie.py --diag     # diagnóstico de la DB
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.database import SessionLocal
from database.models import Lead, InboxMensaje

WA_PHONE_ID_MELANIE = "1562122100308561"
WA_PHONE_ID_AGENTES = "1037947576071396"


def diagnostico(db):
    total = db.query(InboxMensaje).count()
    con_linea_melanie = db.query(InboxMensaje).filter(InboxMensaje.wa_linea == WA_PHONE_ID_MELANIE).count()
    con_linea_agentes = db.query(InboxMensaje).filter(InboxMensaje.wa_linea == WA_PHONE_ID_AGENTES).count()
    sin_linea        = db.query(InboxMensaje).filter(InboxMensaje.wa_linea.is_(None)).count()
    sin_lead         = db.query(InboxMensaje).filter(InboxMensaje.lead_id.is_(None), InboxMensaje.direccion == "IN").count()
    sin_lead_sin_lin = db.query(InboxMensaje).filter(
        InboxMensaje.lead_id.is_(None),
        InboxMensaje.direccion == "IN",
        InboxMensaje.wa_linea.is_(None),
    ).count()
    sin_lead_melanie = db.query(InboxMensaje).filter(
        InboxMensaje.lead_id.is_(None),
        InboxMensaje.direccion == "IN",
        InboxMensaje.wa_linea == WA_PHONE_ID_MELANIE,
    ).count()

    print("=== DIAGNÓSTICO INBOX ===")
    print(f"  Total mensajes                     : {total}")
    print(f"  Con wa_linea = Melanie             : {con_linea_melanie}")
    print(f"  Con wa_linea = Agentes             : {con_linea_agentes}")
    print(f"  Sin wa_linea (NULL)                : {sin_linea}")
    print(f"  Entrantes sin lead_id (total)      : {sin_lead}")
    print(f"    └ sin wa_linea                   : {sin_lead_sin_lin}")
    print(f"    └ wa_linea = Melanie             : {sin_lead_melanie}")


def run(dry_run: bool = False):
    db = SessionLocal()
    try:
        diagnostico(db)
        print()

        # Obtener números IN sin lead — los de Melanie (explícito) + los NULL (históricos)
        from sqlalchemy import or_
        filas = (
            db.query(InboxMensaje.phone, InboxMensaje.nombre_contacto)
            .filter(
                InboxMensaje.direccion == "IN",
                InboxMensaje.lead_id.is_(None),
                or_(
                    InboxMensaje.wa_linea == WA_PHONE_ID_MELANIE,
                    InboxMensaje.wa_linea.is_(None),
                ),
            )
            .all()
        )

        # Deduplicar por phone (tomar primer nombre encontrado)
        phones: dict[str, str] = {}
        for phone, nombre in filas:
            if phone not in phones:
                phones[phone] = nombre or phone

        print(f"Números únicos a procesar: {len(phones)}")
        if not phones:
            print("Nada para hacer.")
            return

        creados = 0
        ya_existia = 0
        corregidos = 0

        for phone, nombre in phones.items():
            lead = db.query(Lead).filter(Lead.telefono.contains(phone[-9:])).first()
            if lead:
                ya_existia += 1
                if lead.modo_atencion != "humano":
                    corregidos += 1
                    print(f"  ~ Corregido a humano: {phone} ({lead.nombre})")
                    if not dry_run:
                        lead.modo_atencion = "humano"
                        lead.agente_asignado = "melanie"
                        db.commit()
                continue

            creados += 1
            print(f"  {'[DRY]' if dry_run else '+'} Nuevo lead: {phone} — {nombre}")
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
                db.flush()

                # Vincular mensajes sin lead al nuevo
                db.query(InboxMensaje).filter(
                    InboxMensaje.phone == phone,
                    InboxMensaje.lead_id.is_(None),
                ).update({"lead_id": new_lead.id})
                db.commit()

        print(f"\nResumen:")
        print(f"  Leads nuevos creados  : {creados}")
        print(f"  Ya tenían lead        : {ya_existia}")
        print(f"  Corregidos a humano   : {corregidos}")
        if dry_run:
            print("  (modo dry-run — no se escribió nada)")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diag", action="store_true", help="Solo diagnóstico")
    args = parser.parse_args()

    if args.diag:
        db = SessionLocal()
        try:
            diagnostico(db)
        finally:
            db.close()
    else:
        run(dry_run=args.dry_run)
