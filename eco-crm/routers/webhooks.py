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
from database.models import Lead, Interaccion, ConfiguracionSistema, Notificacion, Usuario, MetaPagina
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

            # Número del vendedor que recibió el mensaje (línea destino)
            metadata = value.get("metadata", {})
            wa_phone_id_meta = metadata.get("phone_number_id", "")
            display_phone = metadata.get("display_phone_number", "")

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
                    _procesar_mensaje_wa(
                        db, telefono_raw, nombre_wa, texto,
                        wa_phone_id=wa_phone_id_meta,
                        display_phone=display_phone,
                    )
                except Exception as e:
                    log.error(f"[WA Webhook] Error procesando mensaje de {telefono_raw}: {e}")

    return {"ok": True}


def _procesar_mensaje_wa(
    db: Session,
    telefono: str,
    nombre: str,
    texto: str,
    wa_phone_id: str = "",
    display_phone: str = "",
):
    """
    Lógica principal por mensaje entrante:
    1. Buscar lead activo por teléfono.
    2. Si existe → agregar interacción WHATSAPP + actualizar estado a CONTACTADO.
    3. Si no existe → crear lead nuevo.
       - Si el mensaje llegó a una línea de vendedor (MetaPagina) → asignar a esa página,
         sin Round Robin.
       - Caso general → Round Robin.
    4. Notificar al asesor asignado.
    """
    # Identificar página/vendedor por la línea receptora
    pagina: Optional[MetaPagina] = None
    if wa_phone_id or display_phone:
        q = db.query(MetaPagina)
        if wa_phone_id:
            pagina = q.filter(MetaPagina.wa_phone_id == wa_phone_id).first()
        if not pagina and display_phone:
            # Comparar limpiando espacios y signos
            clean = display_phone.replace("+", "").replace(" ", "").replace("-", "")
            pagina = q.filter(
                MetaPagina.numero_whatsapp.ilike(f"%{clean[-9:]}%")
            ).first()

    # 1. Buscar lead activo
    lead = db.query(Lead).filter(
        Lead.telefono.ilike(f"%{telefono.strip()}%"),
        Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"])
    ).order_by(Lead.created_at.desc()).first()

    es_nuevo = False

    if not lead:
        # 2. Crear lead nuevo
        if pagina:
            # Línea de vendedor: NO usa Round Robin, se asigna a la página
            asesor_id = None
            meta_pagina_id = pagina.page_id
            notas_extra = f"[AUTO] Lead por línea '{pagina.nombre}' ({pagina.vendedor or pagina.numero_whatsapp}): {texto[:200]}"
        else:
            asesor_id = _siguiente_asesor_rr(db)
            meta_pagina_id = None
            notas_extra = f"[AUTO] Lead generado por mensaje WA: {texto[:200]}"

        lead = Lead(
            nombre=nombre,
            telefono=telefono,
            producto_interes="SIN_DEFINIR",
            forma_pago="SIN_DEFINIR",
            localidad="",
            origen="WHATSAPP",
            estado="NUEVO",
            asesor_apertura_id=asesor_id,
            notas=notas_extra,
        )
        # Asignar página si corresponde
        if meta_pagina_id:
            try:
                lead.meta_pagina_id = meta_pagina_id
            except Exception:
                pass
        db.add(lead)
        db.commit()
        db.refresh(lead)
        es_nuevo = True
        log.info(f"[WA Webhook] Lead nuevo creado #{lead.id} para {telefono}" +
                 (f" (línea {pagina.nombre})" if pagina else ""))
    else:
        # Lead existente: actualizar meta_pagina_id si aún no tiene
        if pagina and not getattr(lead, "meta_pagina_id", None):
            try:
                lead.meta_pagina_id = pagina.page_id
                db.commit()
            except Exception:
                pass
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
