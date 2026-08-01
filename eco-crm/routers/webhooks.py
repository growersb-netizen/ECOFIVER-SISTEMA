"""
F1 — Webhook WhatsApp Cloud API
  GET  /api/webhooks/whatsapp  → verificación de challenge (Meta)
  POST /api/webhooks/whatsapp  → mensajes entrantes
      • Si el remitente no tiene lead activo → crea lead automático
      • Notifica al siguiente asesor del pool Round Robin
      • Guarda el mensaje como Interaccion en el lead
"""
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Lead, Interaccion, ConfiguracionSistema, Notificacion, Usuario
from utils.whatsapp import send_whatsapp_text, notificar_asesor_nuevo_lead

log = logging.getLogger(__name__)
router = APIRouter()

VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "ecomodulos_webhook_2024")


# ─── Verificación del webhook (GET) ──────────────────────────────────────────

@router.get("/api/webhooks/whatsapp")
async def wa_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """Meta verifica el webhook enviando hub.mode=subscribe y hub.challenge."""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        log.info("[WA Webhook] Verificación exitosa")
        return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge
    raise HTTPException(403, "Token de verificación inválido")


# ─── Recepción de mensajes (POST) ────────────────────────────────────────────

@router.post("/api/webhooks/whatsapp")
async def wa_incoming(request: Request, db: Session = Depends(get_db)):
    """
    Procesa mensajes entrantes de WhatsApp Cloud API.
    Estructura esperada:
    {
      "object": "whatsapp_business_account",
      "entry": [{
        "changes": [{
          "value": {
            "messages": [{ "from": "549...", "text": {"body": "..."}, "type": "text" }],
            "contacts": [{ "profile": { "name": "..." } }]
          }
        }]
      }]
    }
    """
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}  # Meta espera 200 siempre

    if payload.get("object") != "whatsapp_business_account":
        return {"ok": True}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])

            for msg in messages:
                if msg.get("type") != "text":
                    continue  # solo texto por ahora

                telefono_raw = msg.get("from", "")
                texto = msg.get("text", {}).get("body", "").strip()
                nombre_wa = (contacts[0]["profile"]["name"]
                             if contacts and contacts[0].get("profile") else telefono_raw)

                if not telefono_raw:
                    continue

                try:
                    _procesar_mensaje_wa(db, telefono_raw, nombre_wa, texto)
                except Exception as e:
                    log.error(f"[WA Webhook] Error procesando mensaje de {telefono_raw}: {e}")

    return {"ok": True}


def _procesar_mensaje_wa(db: Session, telefono: str, nombre: str, texto: str):
    """
    Lógica principal por mensaje entrante:
    1. Buscar lead activo por teléfono.
    2. Si existe → agregar interacción WHATSAPP + actualizar estado a CONTACTADO.
    3. Si no existe → crear lead nuevo y asignarlo vía Round Robin.
    4. Notificar al asesor asignado.
    """
    # 1. Buscar lead activo
    lead = db.query(Lead).filter(
        Lead.telefono.ilike(f"%{telefono.strip()}%"),
        Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"])
    ).order_by(Lead.created_at.desc()).first()

    es_nuevo = False

    if not lead:
        # 2. Crear lead nuevo
        asesor_id = _siguiente_asesor_rr(db)
        lead = Lead(
            nombre=nombre,
            telefono=telefono,
            producto_interes="SIN_DEFINIR",
            forma_pago="SIN_DEFINIR",
            localidad="",
            origen="WHATSAPP",
            estado="NUEVO",
            asesor_apertura_id=asesor_id,
            notas=f"[AUTO] Lead generado por mensaje WA: {texto[:200]}",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        es_nuevo = True
        log.info(f"[WA Webhook] Lead nuevo creado #{lead.id} para {telefono}")
    else:
        # Lead existente — actualizar estado si sigue NUEVO/INTENTADO
        if lead.estado in ("NUEVO", "INTENTADO"):
            lead.estado = "CONTACTADO"

    # 3. Registrar interacción
    interaccion = Interaccion(
        lead_id=lead.id,
        tipo="WHATSAPP",
        resultado="RESPONDIO",
        notas=f"[WA entrante] {texto[:500]}",
        asesor_id=lead.asesor_apertura_id,
    )
    db.add(interaccion)
    db.commit()

    # 4. Notificar al asesor
    if lead.asesor_apertura_id:
        asesor = db.query(Usuario).filter(Usuario.id == lead.asesor_apertura_id).first()
        if asesor:
            # Notificación interna CRM
            accion = "nuevo lead" if es_nuevo else "respondió"
            db.add(Notificacion(
                usuario_id=asesor.id,
                tipo="LEAD",
                titulo=f"📩 {nombre} te escribió por WhatsApp",
                mensaje=f'"{texto[:100]}"',
                referencia_id=lead.id,
                referencia_tipo="LEAD",
            ))
            db.commit()

            # Notificación WA al asesor (si tiene teléfono configurado)
            tel_cfg = db.query(ConfiguracionSistema).filter(
                ConfiguracionSistema.clave == f"asesor_tel_{asesor.id}"
            ).first()
            if tel_cfg and tel_cfg.valor:
                accion_txt = "📋 *Nuevo lead*" if es_nuevo else "💬 *Respuesta de lead*"
                msg = (
                    f"{accion_txt} — {nombre}\n"
                    f"📱 Tel: {telefono}\n"
                    f'💬 Mensaje: "{texto[:150]}"\n'
                    f"🔗 Ver CRM: https://eco-crm-production.up.railway.app/leads"
                )
                send_whatsapp_text(db, tel_cfg.valor, msg)


def _siguiente_asesor_rr(db: Session) -> Optional[int]:
    """Round Robin: devuelve el ID del próximo asesor del pool."""
    import json
    pool_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "leads_rr_asesores"
    ).first()
    idx_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "leads_rr_index"
    ).first()

    if not pool_cfg or not pool_cfg.valor:
        return None

    try:
        pool = json.loads(pool_cfg.valor)
    except Exception:
        return None

    if not pool:
        return None

    idx = 0
    if idx_cfg and idx_cfg.valor:
        try:
            idx = int(idx_cfg.valor)
        except Exception:
            idx = 0

    asesor_id = pool[idx % len(pool)]
    nuevo_idx = (idx + 1) % len(pool)

    if idx_cfg:
        idx_cfg.valor = str(nuevo_idx)
    else:
        db.add(ConfiguracionSistema(clave="leads_rr_index", valor=str(nuevo_idx)))
    db.commit()

    return int(asesor_id)
