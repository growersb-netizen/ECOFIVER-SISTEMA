"""
push.py — Web Push Notifications (VAPID)
Maneja suscripciones y envío de notificaciones push al navegador.
"""
import json
import logging
import base64

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import PushSubscription, ConfiguracionSistema, Usuario
from routers.auth import require_auth

router = APIRouter()
log = logging.getLogger(__name__)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_vapid_keys(db: Session):
    """Devuelve (private_key_pem, public_key_b64url) desde la config."""
    priv = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "vapid_private_key"
    ).first()
    pub = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "vapid_public_key"
    ).first()
    return (priv.valor if priv else None), (pub.valor if pub else None)


def generar_y_guardar_vapid(db: Session):
    """Genera claves VAPID y las guarda en ConfiguracionSistema si no existen."""
    priv_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "vapid_private_key"
    ).first()
    if priv_cfg and priv_cfg.valor:
        return  # Ya existen

    try:
        from py_vapid import Vapid
        from cryptography.hazmat.primitives import serialization

        v = Vapid()
        v.generate_keys()

        # Private key como PEM
        private_pem = v.private_pem().decode()

        # Public key como base64url sin padding (formato ApplicationServerKey)
        pub_bytes = v.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip("=")

        for clave, valor, secreto in [
            ("vapid_private_key", private_pem, True),
            ("vapid_public_key",  pub_b64,     False),
        ]:
            existing = db.query(ConfiguracionSistema).filter(
                ConfiguracionSistema.clave == clave
            ).first()
            if existing:
                existing.valor = valor
            else:
                db.add(ConfiguracionSistema(
                    clave=clave,
                    valor=valor,
                    es_secreto=secreto,
                    categoria="push",
                    estado="activa",
                ))

        db.commit()
        log.info("[PUSH] Claves VAPID generadas y guardadas")
    except Exception as e:
        db.rollback()
        log.error(f"[PUSH] Error generando claves VAPID: {e}")


def enviar_push_a_suscripcion(
    endpoint: str,
    p256dh: str,
    auth: str,
    titulo: str,
    mensaje: str,
    url: str,
    vapid_private_key: str,
) -> bool:
    """Envía una notificación push a una suscripción individual. Retorna True si ok."""
    try:
        from pywebpush import webpush, WebPushException

        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=json.dumps({"title": titulo, "body": mensaje, "url": url}),
            vapid_private_key=vapid_private_key,
            vapid_claims={"sub": "mailto:crm@ecomodulos.com.ar"},
        )
        return True
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        log.warning(f"[PUSH] Fallo enviando a {endpoint[:40]}... status={status} err={e}")
        return False


def notificar_push_todos(db: Session, titulo: str, mensaje: str, url: str = "/"):
    """Envía push a todos los usuarios suscritos. Elimina suscripciones expiradas (410)."""
    try:
        from pywebpush import WebPushException

        private_key, _ = get_vapid_keys(db)
        if not private_key:
            return

        subs = db.query(PushSubscription).all()
        to_delete = []

        for sub in subs:
            try:
                from pywebpush import webpush
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=json.dumps({"title": titulo, "body": mensaje, "url": url}),
                    vapid_private_key=private_key,
                    vapid_claims={"sub": "mailto:crm@ecomodulos.com.ar"},
                )
            except WebPushException as e:
                resp = getattr(e, "response", None)
                if resp is not None and resp.status_code in (404, 410):
                    to_delete.append(sub.id)
                else:
                    log.warning(f"[PUSH] Error en {sub.endpoint[:40]}: {e}")
            except Exception as e:
                log.warning(f"[PUSH] Error inesperado en push: {e}")

        if to_delete:
            db.query(PushSubscription).filter(PushSubscription.id.in_(to_delete)).delete(synchronize_session=False)
            db.commit()
    except Exception as e:
        log.error(f"[PUSH] notificar_push_todos error: {e}")


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@router.get("/api/push/vapid-public-key")
async def vapid_public_key(db: Session = Depends(get_db)):
    """Devuelve la VAPID public key para el frontend."""
    _, pub = get_vapid_keys(db)
    if not pub:
        return {"key": None}
    return {"key": pub}


@router.post("/api/push/subscribe")
async def subscribe(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")

    if not endpoint or not p256dh or not auth:
        return {"ok": False, "detail": "Suscripción inválida"}

    # Upsert por endpoint
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == endpoint
    ).first()
    if existing:
        existing.usuario_id = current_user.id
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.add(PushSubscription(
            usuario_id=current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        ))
    db.commit()
    log.info(f"[PUSH] Suscripción registrada para usuario {current_user.id}")
    return {"ok": True}


@router.delete("/api/push/subscribe")
async def unsubscribe(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    deleted = db.query(PushSubscription).filter(
        PushSubscription.usuario_id == current_user.id
    ).delete()
    db.commit()
    return {"ok": True, "deleted": deleted}
