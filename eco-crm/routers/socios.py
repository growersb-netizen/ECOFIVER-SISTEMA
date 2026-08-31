"""
Plataforma de Socios Comerciales EcoFiver — registro autoservicio, panel,
carga de ventas, scoring BCRA y liquidación de comisiones.

Reemplaza el modelo de "postulación con aprobación" por registro directo:
el postulante se registra, verifica su WhatsApp con un código, y entra al
instante. Sin intervención humana salvo en 3 puntos explícitos (ver spec):
  1) Llamada de bienvenida (auditoría) — venta financiada
  2) Confirmación de 48hs — venta de contado
  3) Transferencia bancaria de la comisión liquidada

Extiende eco-crm; no reemplaza routers/aliados.py (que sigue gestionando
el panel interno de gestión, comisiones, y el portal de solo lectura legado).
"""
import os
import re
import json
import random
import secrets
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pathlib import Path

from database.database import get_db
from database.models import (
    Aliado, Comision, VentaContado, VentaFinanciada, MaterialSocio,
    ScoringBCRA, Usuario, ComisionConfig, Presupuesto,
)
from routers.auth import require_auth, get_user_roles, get_current_user
from routers.catalogo import load_catalogo
from utils.whatsapp import send_whatsapp_text, send_whatsapp_otp, notificar_rodrigo

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "eco-crm-secret-key-dev-2024")
ALGORITHM = "HS256"
SOCIO_TOKEN_COOKIE = "socio_token"
SOCIO_TOKEN_EXPIRE_HOURS = 24 * 14  # 14 días — es un panel de trabajo diario, no una sesión admin

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")

MAX_INTENTOS_LOGIN = 5
BLOQUEO_MINUTOS = 15
CODIGO_OTP_EXPIRA_MINUTOS = 10

DATA_DIR = Path("data")
DOCS_SOCIOS_DIR = DATA_DIR / "documentos_socios"  # /app/data — persistente
DOCS_SOCIOS_DIR.mkdir(parents=True, exist_ok=True)
BIBLIOTECA_DIR = DATA_DIR / "biblioteca_socios"
BIBLIOTECA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN DEL SOCIO (independiente de Usuario/auth.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _crear_token_socio(aliado_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=SOCIO_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": str(aliado_id), "typ": "socio", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_socio(request: Request, db: Session = Depends(get_db)) -> Optional[Aliado]:
    token = request.cookies.get(SOCIO_TOKEN_COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != "socio":
            return None
        aliado_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
    return db.query(Aliado).filter(Aliado.id == aliado_id, Aliado.estado == "activo").first()


def require_socio(request: Request, db: Session = Depends(get_db)) -> Aliado:
    """
    Requiere sesión iniciada. La verificación de WhatsApp/email y la carga de
    perfil (DNI, zona) NO son requisito para entrar al panel — se piden después
    del login, con un pop-up obligatorio, y solo bloquean poder cargar ventas
    (ver `_require_verificado`).
    """
    socio = get_current_socio(request, db)
    if not socio:
        raise HTTPException(401, "No autenticado")
    return socio


def _esta_verificado(socio: Aliado) -> bool:
    # La verificación de email quedó afuera a pedido: WhatsApp ya es suficiente
    # como único canal verificado, para no duplicar un paso — la función/los
    # endpoints de email siguen existiendo (sin uso) por si se retoma después.
    return bool(socio.perfil_completo and socio.whatsapp_verificado)


def _require_verificado(socio: Aliado):
    """Gate para las acciones que generan comisiones y para la Biblioteca: perfil completo + WhatsApp verificado."""
    if not _esta_verificado(socio):
        raise HTTPException(
            403,
            "Completá tu perfil y verificá tu WhatsApp antes de cargar ventas o acceder a la Biblioteca — te va a aparecer el paso pendiente al entrar al panel.",
        )


def _require_gestion_interna(x_api_key: Optional[str], current_user: Optional[Usuario]):
    """Para las acciones que sigue haciendo el equipo interno (los 3 puntos humanos)."""
    if x_api_key and x_api_key == API_KEY:
        return
    if current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "SUPERVISOR_CIERRE", "ADMINISTRACION", "COORDINADOR_OPERATIVO")):
        return
    raise HTTPException(403, "Sin permisos para esta operación")


def _generar_codigo_aliado(db: Session) -> str:
    ultimo = db.query(Aliado).order_by(Aliado.id.desc()).first()
    n = 1
    if ultimo and ultimo.codigo and ultimo.codigo.upper().startswith("AL-"):
        try:
            n = int(ultimo.codigo.split("-")[-1]) + 1
        except Exception:
            n = (ultimo.id or 0) + 1
    elif ultimo:
        n = (ultimo.id or 0) + 1
    return f"AL-{n:03d}"


def _normalizar_telefono(tel: str) -> str:
    """
    Normaliza a formato internacional completo para WhatsApp Cloud API:
    54 + 9 + 10 dígitos (ej: "11 3516-4644" -> "5491135164644"). Nadie tipea
    el "54 9" a mano, pero sin eso el envío por WhatsApp devuelve 200 OK
    (la API acepta el pedido) y el mensaje nunca llega a ningún dispositivo
    real. Asume números argentinos (el programa opera "todo el país" = AR).
    """
    digitos = re.sub(r"\D", "", tel or "")
    if not digitos:
        return ""
    if digitos.startswith("549"):
        return digitos
    if digitos.startswith("54"):
        return "549" + digitos[2:]
    if digitos.startswith("9") and len(digitos) == 11:
        return "54" + digitos
    return "549" + digitos  # número local sin código de país (10 dígitos)


def _notificar_socio(db: Session, aliado_codigo: Optional[str], mensaje: str):
    """Notificación automática al socio por WhatsApp ante cambios de estado."""
    if not aliado_codigo:
        return
    socio = db.query(Aliado).filter(Aliado.codigo == aliado_codigo).first()
    if socio and socio.telefono:
        send_whatsapp_text(db, socio.telefono, mensaje)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRO — reemplaza a la postulación con aprobación
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/public/socio-registro")
async def socio_registro(request: Request, db: Session = Depends(get_db)):
    """
    Registro directo y automático — sin aprobación humana. El único requisito
    para arrancar es Nombre, WhatsApp y Email; el resto (DNI, zona, etc.) se
    completa después de verificar. No pide contraseña acá: se verifica el
    WhatsApp con un código y, ya adentro, se le pide crear su contraseña
    para los próximos ingresos (ver /socio-verificar y /api/socio/crear-password).
    """
    data = await request.json()

    nombre = (data.get("nombre") or "").strip()
    telefono = _normalizar_telefono(data.get("whatsapp") or data.get("telefono") or "")
    email = (data.get("email") or "").strip().lower()

    if not nombre or not telefono or not email:
        raise HTTPException(400, "Nombre y apellido, WhatsApp y email son obligatorios")
    if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Email inválido")
    if len(telefono) < 8:
        raise HTTPException(400, "WhatsApp inválido")

    if db.query(Aliado).filter(Aliado.telefono == telefono, Aliado.telefono != "").first():
        raise HTTPException(409, "Ya existe un socio registrado con ese WhatsApp")
    if db.query(Aliado).filter(Aliado.email == email).first():
        raise HTTPException(409, "Ya existe un socio registrado con ese email")

    origen_partes = [
        f"{k}={v}" for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
        if (v := (data.get(k) or "").strip())
    ]
    origen_registro = "&".join(origen_partes)

    otp = f"{random.randint(0, 999999):06d}"
    socio = Aliado(
        codigo=_generar_codigo_aliado(db),
        nombre=nombre,
        telefono=telefono,
        email=email,
        estado="activo",  # registro directo, sin aprobación
        whatsapp_verificado=False,
        email_verificado=False,
        perfil_completo=False,
        codigo_verificacion=otp,
        codigo_verificacion_expira=datetime.now() + timedelta(minutes=CODIGO_OTP_EXPIRA_MINUTOS),
        origen_registro=origen_registro,
        notas="Registro directo vía plataforma de socios",
    )
    db.add(socio)
    db.commit()
    db.refresh(socio)

    send_whatsapp_otp(db, telefono, otp)
    return {"ok": True, "codigo": socio.codigo, "nombre": socio.nombre}


@router.post("/api/public/socio-solicitar-codigo")
async def socio_solicitar_codigo(request: Request, db: Session = Depends(get_db)):
    """
    Reenvía el código de activación por WhatsApp — para cuando el código de
    bienvenida del registro ya venció y todavía no creó su contraseña.
    Se confirma con /api/public/socio-verificar.
    """
    data = await request.json()
    identificador = (data.get("whatsapp") or data.get("email") or data.get("codigo") or "").strip()
    if not identificador:
        raise HTTPException(400, "Ingresá tu WhatsApp, email o código de socio")

    q = db.query(Aliado)
    if "@" in identificador:
        socio = q.filter(Aliado.email == identificador.lower()).first()
    elif re.match(r"^[A-Za-z]{2}-\d+$", identificador):
        socio = q.filter(Aliado.codigo == identificador.upper()).first()
    else:
        socio = q.filter(Aliado.telefono == _normalizar_telefono(identificador)).first()

    if not socio:
        raise HTTPException(404, "No encontramos una cuenta con ese dato — registrate primero")

    otp = f"{random.randint(0, 999999):06d}"
    socio.codigo_verificacion = otp
    socio.codigo_verificacion_expira = datetime.now() + timedelta(minutes=CODIGO_OTP_EXPIRA_MINUTOS)
    db.commit()
    send_whatsapp_otp(db, socio.telefono, otp)
    return {"ok": True, "codigo": socio.codigo}


@router.post("/api/public/socio-verificar")
async def socio_verificar(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Confirma el código de WhatsApp y deja la sesión iniciada. Si todavía no
    tiene contraseña (primera activación), el front debe pedirle que cree
    una antes de usar el panel — ver `necesita_password` en la respuesta y
    POST /api/socio/crear-password.
    """
    data = await request.json()
    codigo = (data.get("codigo") or "").strip().upper()
    otp = (data.get("otp") or data.get("codigo_verificacion") or "").strip()

    if not codigo or not otp:
        raise HTTPException(400, "Faltan datos")

    socio = db.query(Aliado).filter(Aliado.codigo == codigo).first()
    if not socio:
        raise HTTPException(404, "Socio no encontrado")
    if not socio.codigo_verificacion or socio.codigo_verificacion != otp:
        raise HTTPException(400, "Código incorrecto")
    if socio.codigo_verificacion_expira and socio.codigo_verificacion_expira < datetime.now():
        raise HTTPException(400, "El código venció — pedí uno nuevo")

    socio.whatsapp_verificado = True
    socio.codigo_verificacion = None
    socio.codigo_verificacion_expira = None
    db.commit()

    token = _crear_token_socio(socio.id)
    response.set_cookie(SOCIO_TOKEN_COOKIE, token, httponly=True, max_age=SOCIO_TOKEN_EXPIRE_HOURS * 3600, samesite="lax")
    return {"ok": True, "codigo": socio.codigo, "nombre": socio.nombre, "necesita_password": not bool(socio.password_hash)}


@router.post("/api/socio/crear-password")
async def socio_crear_password(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """Define la contraseña del socio ya logueado — paso único tras la primera
    activación por WhatsApp. También sirve para cambiarla estando adentro."""
    data = await request.json()
    password = data.get("password") or ""
    if len(password) < 6:
        raise HTTPException(400, "La contraseña debe tener al menos 6 caracteres")
    socio.password_hash = pwd_context.hash(password)
    db.commit()
    return {"ok": True}


@router.post("/api/public/socio-login")
async def socio_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """Login con email, WhatsApp o código de socio + contraseña. Con límite de intentos."""
    data = await request.json()
    identificador = (data.get("identificador") or data.get("email") or data.get("whatsapp") or data.get("codigo") or "").strip()
    password = data.get("password") or ""

    if not identificador or not password:
        raise HTTPException(400, "Faltan credenciales")

    socio = _buscar_socio_por_identificador(db, identificador)

    if not socio:
        raise HTTPException(401, "Credenciales incorrectas")

    if socio.bloqueado_hasta and socio.bloqueado_hasta > datetime.now():
        minutos = max(1, int((socio.bloqueado_hasta - datetime.now()).total_seconds() // 60) + 1)
        raise HTTPException(429, f"Demasiados intentos fallidos. Probá de nuevo en {minutos} minutos.")

    if not socio.password_hash or not pwd_context.verify(password, socio.password_hash):
        socio.intentos_fallidos = (socio.intentos_fallidos or 0) + 1
        if socio.intentos_fallidos >= MAX_INTENTOS_LOGIN:
            socio.bloqueado_hasta = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
            socio.intentos_fallidos = 0
        db.commit()
        raise HTTPException(401, "Credenciales incorrectas")

    socio.intentos_fallidos = 0
    socio.bloqueado_hasta = None
    db.commit()

    token = _crear_token_socio(socio.id)
    response.set_cookie(SOCIO_TOKEN_COOKIE, token, httponly=True, max_age=SOCIO_TOKEN_EXPIRE_HOURS * 3600, samesite="lax")
    return {"ok": True, "codigo": socio.codigo, "nombre": socio.nombre}


@router.post("/api/public/socio-reenviar-codigo")
async def socio_reenviar_codigo(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    codigo = (data.get("codigo") or "").strip().upper()
    socio = db.query(Aliado).filter(Aliado.codigo == codigo).first()
    if not socio:
        raise HTTPException(404, "Socio no encontrado")

    otp = f"{random.randint(0, 999999):06d}"
    socio.codigo_verificacion = otp
    socio.codigo_verificacion_expira = datetime.now() + timedelta(minutes=CODIGO_OTP_EXPIRA_MINUTOS)
    db.commit()
    send_whatsapp_otp(db, socio.telefono, otp)
    return {"ok": True}


# ─── Recuperación de contraseña — mismo canal de OTP por WhatsApp ─────────────

def _buscar_socio_por_identificador(db: Session, identificador: str) -> Optional[Aliado]:
    """Busca un socio por email, código (AL-000) o WhatsApp — mismo criterio
    usado para login, en /api/public/socio-login."""
    identificador = (identificador or "").strip()
    q = db.query(Aliado)
    if "@" in identificador:
        return q.filter(Aliado.email == identificador.lower()).first()
    if re.match(r"^[A-Za-z]{2}-\d+$", identificador):
        return q.filter(Aliado.codigo == identificador.upper()).first()
    return q.filter(Aliado.telefono == _normalizar_telefono(identificador)).first()


@router.post("/api/public/socio-olvide-password")
async def socio_olvide_password(request: Request, db: Session = Depends(get_db)):
    """
    Pide un código por WhatsApp para resetear la contraseña. Responde igual
    exista o no el socio (no revela si un dato está registrado).
    """
    data = await request.json()
    identificador = (data.get("email") or data.get("whatsapp") or data.get("codigo") or "").strip()
    if not identificador:
        raise HTTPException(400, "Ingresá tu WhatsApp, email o código de socio")

    socio = _buscar_socio_por_identificador(db, identificador)

    if socio and socio.telefono:
        otp = f"{random.randint(0, 999999):06d}"
        socio.codigo_verificacion = otp
        socio.codigo_verificacion_expira = datetime.now() + timedelta(minutes=CODIGO_OTP_EXPIRA_MINUTOS)
        db.commit()
        send_whatsapp_otp(db, socio.telefono, otp)

    return {"ok": True, "mensaje": "Si el dato coincide con una cuenta, te mandamos un código por WhatsApp."}


@router.post("/api/public/socio-resetear-password")
async def socio_resetear_password(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    identificador = (data.get("email") or data.get("whatsapp") or data.get("codigo") or "").strip()
    otp = (data.get("otp") or "").strip()
    password_nueva = data.get("password_nueva") or ""

    if not identificador or not otp:
        raise HTTPException(400, "Faltan datos")
    if len(password_nueva) < 6:
        raise HTTPException(400, "La contraseña debe tener al menos 6 caracteres")

    socio = _buscar_socio_por_identificador(db, identificador)

    if not socio or not socio.codigo_verificacion or socio.codigo_verificacion != otp:
        raise HTTPException(400, "Código incorrecto")
    if socio.codigo_verificacion_expira and socio.codigo_verificacion_expira < datetime.now():
        raise HTTPException(400, "El código venció — pedí uno nuevo")

    socio.password_hash = pwd_context.hash(password_nueva)
    socio.codigo_verificacion = None
    socio.codigo_verificacion_expira = None
    socio.intentos_fallidos = 0
    socio.bloqueado_hasta = None
    db.commit()
    return {"ok": True, "mensaje": "Contraseña actualizada. Ya podés ingresar."}


@router.post("/api/public/socio-logout")
async def socio_logout(response: Response):
    response.delete_cookie(SOCIO_TOKEN_COOKIE)
    return {"ok": True}


@router.get("/api/socio/me")
async def socio_me(socio: Aliado = Depends(require_socio)):
    return {
        "codigo": socio.codigo,
        "nombre": socio.nombre,
        "email": socio.email,
        "telefono": socio.telefono or "",
        "dni": socio.dni or "",
        "zona": socio.zona,
        "cuit_monotributo": socio.cuit_monotributo or "",
        "cbu_alias": socio.cbu_alias or "",
        "doc_monotributo_cargado": bool(socio.doc_monotributo_path),
        "doc_dni_cargado": bool(socio.doc_dni_path),
        "perfil_completo": bool(socio.perfil_completo),
        "whatsapp_verificado": bool(socio.whatsapp_verificado),
        "email_verificado": bool(socio.email_verificado),
        "verificado": _esta_verificado(socio),
        "tiene_password": bool(socio.password_hash),
        "comisiones_aceptadas": bool(socio.comisiones_aceptadas_en),
        "interes_venta": socio.interes_venta,
    }


@router.put("/api/socio/me")
async def socio_actualizar_perfil(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    data = await request.json()
    for campo in ("zona", "cbu_alias", "cuit_monotributo"):
        if campo in data:
            setattr(socio, campo, (data[campo] or "").strip())

    if "interes_venta" in data:
        valor = (data["interes_venta"] or "").strip().upper()
        if valor and valor not in ("PISCINAS", "MODULOS", "AMBOS"):
            raise HTTPException(400, "interes_venta debe ser PISCINAS, MODULOS o AMBOS")
        socio.interes_venta = valor or None

    if "dni" in data:
        dni = (data["dni"] or "").strip()
        if dni:
            existente = db.query(Aliado).filter(Aliado.dni == dni, Aliado.dni != "", Aliado.id != socio.id).first()
            if existente:
                raise HTTPException(409, "Ese DNI ya está registrado en otra cuenta")
        socio.dni = dni

    # Perfil completo = DNI + zona cargados (el CUIT/Monotributo es opcional).
    if socio.dni and socio.zona:
        socio.perfil_completo = True

    db.commit()
    return {"ok": True, "perfil_completo": bool(socio.perfil_completo), "verificado": _esta_verificado(socio)}


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICACIÓN DE CANALES (post-login) — WhatsApp y email por separado
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/socio/verificar-whatsapp/enviar")
async def enviar_codigo_whatsapp(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Manda el código al WhatsApp del socio. Acepta opcionalmente `whatsapp` en el
    body para elegir/corregir el número a verificar (por si se equivocó al
    registrarse, o prefiere verificar otro) — se guarda como su número de
    contacto si difiere del que ya tenía.
    """
    if socio.whatsapp_verificado:
        return {"ok": True, "ya_verificado": True}

    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    nuevo_tel = _normalizar_telefono(data.get("whatsapp") or "") if data else ""
    if nuevo_tel:
        if len(nuevo_tel) < 8:
            raise HTTPException(400, "WhatsApp inválido")
        existente = db.query(Aliado).filter(Aliado.telefono == nuevo_tel, Aliado.telefono != "", Aliado.id != socio.id).first()
        if existente:
            raise HTTPException(409, "Ese WhatsApp ya está registrado en otra cuenta")
        socio.telefono = nuevo_tel

    if not socio.telefono:
        raise HTTPException(400, "No tenés un WhatsApp cargado")
    otp = f"{random.randint(0, 999999):06d}"
    socio.codigo_verificacion = otp
    socio.codigo_verificacion_expira = datetime.now() + timedelta(minutes=CODIGO_OTP_EXPIRA_MINUTOS)
    db.commit()
    send_whatsapp_otp(db, socio.telefono, otp)
    return {"ok": True}


@router.post("/api/socio/verificar-whatsapp/confirmar")
async def confirmar_codigo_whatsapp(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    data = await request.json()
    otp = (data.get("otp") or data.get("codigo") or "").strip()
    if socio.whatsapp_verificado:
        return {"ok": True, "ya_verificado": True}
    if not socio.codigo_verificacion or socio.codigo_verificacion != otp:
        raise HTTPException(400, "Código incorrecto")
    if socio.codigo_verificacion_expira and socio.codigo_verificacion_expira < datetime.now():
        raise HTTPException(400, "El código venció — pedí uno nuevo")
    socio.whatsapp_verificado = True
    socio.codigo_verificacion = None
    socio.codigo_verificacion_expira = None
    db.commit()
    return {"ok": True, "verificado": _esta_verificado(socio)}


@router.post("/api/socio/verificar-email/enviar")
async def enviar_codigo_email(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    from utils.email import send_email_text

    if socio.email_verificado:
        return {"ok": True, "ya_verificado": True}
    if not socio.email:
        raise HTTPException(400, "No tenés un email cargado")
    otp = f"{random.randint(0, 999999):06d}"
    socio.codigo_verificacion_email = otp
    socio.codigo_verificacion_email_expira = datetime.now() + timedelta(minutes=CODIGO_OTP_EXPIRA_MINUTOS)
    db.commit()
    enviado = send_email_text(
        db, socio.email, "Tu código de verificación EcoFiver",
        f"Tu código de verificación es {otp}. Vence en {CODIGO_OTP_EXPIRA_MINUTOS} minutos.\n\nSi no lo pediste vos, ignorá este mensaje.",
    )
    return {"ok": True, "enviado": enviado}


@router.post("/api/socio/verificar-email/confirmar")
async def confirmar_codigo_email(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    data = await request.json()
    otp = (data.get("otp") or data.get("codigo") or "").strip()
    if socio.email_verificado:
        return {"ok": True, "ya_verificado": True}
    if not socio.codigo_verificacion_email or socio.codigo_verificacion_email != otp:
        raise HTTPException(400, "Código incorrecto")
    if socio.codigo_verificacion_email_expira and socio.codigo_verificacion_email_expira < datetime.now():
        raise HTTPException(400, "El código venció — pedí uno nuevo")
    socio.email_verificado = True
    socio.codigo_verificacion_email = None
    socio.codigo_verificacion_email_expira = None
    db.commit()
    return {"ok": True, "verificado": _esta_verificado(socio)}


# ═══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO Y SIMULADOR (el socio consume lo que el CRM ya calcula)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/socio/catalogo")
async def socio_catalogo(socio: Aliado = Depends(require_socio)):
    """Catálogo completo con precios de lista — para cotizar con seguridad."""
    cat = load_catalogo()
    resultado = {
        "piscinas": {
            "modelos": cat["piscinas"].get("modelos", []),
            "precios_lista": cat["piscinas"].get("precios_lista", {}),
            "precios": cat["piscinas"].get("precios", {}),
            "precios_sin_instalacion": cat["piscinas"].get("precios_sin_instalacion", {}),
            "precios_sin_instalacion_sin_equipo": cat["piscinas"].get("precios_sin_instalacion_sin_equipo", {}),
            "fotos": cat["piscinas"].get("fotos", {}),
            "medidas": cat["piscinas"].get("medidas", {}),
            "colores": cat["piscinas"].get("colores", []),
        },
        "modulos": {
            "superficies_m2": cat["modulos"].get("superficies_m2", []),
            "precios_lista": cat["modulos"].get("precios_lista", {}),
            "precios": cat["modulos"].get("precios", {}),
            "fotos": cat["modulos"].get("fotos", {}),
            "tecnologia": cat["modulos"].get("tecnologia", ""),
        },
        "combos": cat.get("combos") or {},
    }
    # Resto de categorías (hidromasajes, bañeras, receptáculos, accesorios,
    # baños químicos, garitas, cuchas, reposeras, depósitos de jardín): cada
    # una expone su info general (material/instalación/estructura) más los
    # items con su propio precio, descripción y fotos.
    for cat_key in _CATEGORIAS_CATALOGO_SIMPLES:
        bloque = cat.get(cat_key) or {}
        items = bloque.get("modelos") if isinstance(bloque.get("modelos"), dict) else bloque
        if not isinstance(items, dict):
            continue
        info_general = {k: v for k, v in bloque.items() if k != "modelos" and not isinstance(v, dict)}
        resultado[cat_key] = {"info": info_general, "items": items}
    return resultado


CATEGORIAS_FINANCIABLES = ("piscinas", "modulos", "combos")


def _resolver_item_catalogo(cat: dict, categoria: str, producto: str) -> Optional[dict]:
    """
    Busca un producto por categoría+nombre en el catálogo completo (fuente
    única de verdad — igual criterio que /api/socio/catalogo). Devuelve
    {precio_contado, precio_lista} — precio_lista solo existe en las
    categorías financiables (piscinas/módulos/combos).
    """
    categoria = (categoria or "").strip().lower()
    producto = (producto or "").strip()
    if not categoria or not producto:
        return None

    if categoria == "piscinas":
        precios = cat["piscinas"].get("precios", {})
        if producto not in precios:
            return None
        return {"precio_contado": precios[producto], "precio_lista": cat["piscinas"].get("precios_lista", {}).get(producto)}

    if categoria == "modulos":
        precios = cat["modulos"].get("precios", {})
        if producto not in precios:
            return None
        return {"precio_contado": precios[producto], "precio_lista": cat["modulos"].get("precios_lista", {}).get(producto)}

    if categoria == "combos":
        combo = (cat.get("combos") or {}).get(producto)
        if not combo:
            return None
        return {"precio_contado": combo.get("precio_contado"), "precio_lista": combo.get("precio_lista")}

    # Categorías simples (hidromasajes, bañeras, garitas, etc.) — solo contado.
    if categoria in _CATEGORIAS_CATALOGO_SIMPLES:
        bloque = cat.get(categoria) or {}
        items = bloque.get("modelos") if isinstance(bloque.get("modelos"), dict) else bloque
        if not isinstance(items, dict) or producto not in items:
            return None
        item = items[producto]
        precio = item.get("precio_contado") if isinstance(item, dict) else None
        return {"precio_contado": precio, "precio_lista": None}

    return None


@router.post("/api/socio/presupuestos")
async def crear_presupuesto(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Genera un presupuesto profesional en PDF a partir del catálogo completo —
    funciona también como captura de lead: pide los datos completos del
    cliente y queda registrado, disponible para el socio y para el admin.
    """
    data = await request.json()
    categoria = (data.get("categoria") or "").strip().lower()
    producto = (data.get("producto") or "").strip()
    forma_pago = (data.get("forma_pago") or "contado").strip().lower()
    cuotas = data.get("cuotas")

    cliente_nombre = (data.get("cliente_nombre") or "").strip()
    cliente_apellido = (data.get("cliente_apellido") or "").strip()
    cliente_whatsapp = _normalizar_telefono(data.get("cliente_whatsapp") or "")
    cliente_email = (data.get("cliente_email") or "").strip()
    cliente_localidad = (data.get("cliente_localidad") or "").strip()

    if not cliente_nombre or not cliente_apellido or not cliente_whatsapp or not cliente_localidad:
        raise HTTPException(400, "Faltan datos del cliente (nombre, apellido, WhatsApp y localidad son obligatorios)")

    cat = load_catalogo()
    item = _resolver_item_catalogo(cat, categoria, producto)
    if not item:
        raise HTTPException(404, f"No se encontró '{producto}' en la categoría '{categoria}'")

    presu = Presupuesto(
        aliado_codigo=socio.codigo, categoria=categoria, producto=producto, forma_pago=forma_pago,
        cliente_nombre=cliente_nombre, cliente_apellido=cliente_apellido, cliente_whatsapp=cliente_whatsapp,
        cliente_email=cliente_email, cliente_localidad=cliente_localidad,
    )

    if forma_pago == "financiado":
        if categoria not in CATEGORIAS_FINANCIABLES:
            raise HTTPException(400, f"'{categoria}' no tiene plan financiado — solo contado")
        precio_lista = item.get("precio_lista")
        if not precio_lista:
            raise HTTPException(409, "Ese producto no tiene precio de lista cargado")
        try:
            cuotas = int(cuotas)
        except (TypeError, ValueError):
            raise HTTPException(400, "Indicá la cantidad de cuotas")
        if cuotas < 1:
            raise HTTPException(400, "La cantidad de cuotas debe ser mayor a 0")
        factor = 2.0
        cuota_mensual = round(precio_lista / (cuotas + factor))
        ingreso_inicial = round(cuota_mensual * factor)
        presu.cuotas = cuotas
        presu.precio_lista = precio_lista
        presu.cuota_mensual = cuota_mensual
        presu.ingreso_inicial = ingreso_inicial
        presu.total_financiado = ingreso_inicial + cuota_mensual * cuotas
    else:
        forma_pago = "contado"
        presu.forma_pago = "contado"
        precio_contado = item.get("precio_contado")
        if not precio_contado:
            raise HTTPException(409, "Ese producto no tiene precio de contado cargado — consultar")
        presu.precio_contado = precio_contado

    db.add(presu)
    db.commit()
    db.refresh(presu)

    from utils.documentos import render_html, html_to_pdf
    label_categoria = _CATEGORIAS_CATALOGO_SIMPLES.get(categoria, categoria.capitalize())
    html = render_html("presupuesto.html", {
        "numero": presu.id, "fecha": datetime.now().strftime("%d/%m/%Y"),
        "categoria_label": label_categoria, "producto": producto,
        "forma_pago": presu.forma_pago, "forma_pago_label": "Financiado" if presu.forma_pago == "financiado" else "Contado",
        "cliente_nombre": cliente_nombre, "cliente_apellido": cliente_apellido,
        "cliente_whatsapp": cliente_whatsapp, "cliente_email": cliente_email, "cliente_localidad": cliente_localidad,
        "precio_contado": _money(presu.precio_contado), "precio_lista": _money(presu.precio_lista),
        "cuota_mensual": _money(presu.cuota_mensual), "ingreso_inicial": _money(presu.ingreso_inicial),
        "total_financiado": _money(presu.total_financiado), "cuotas": presu.cuotas,
        "socio_nombre": socio.nombre, "socio_codigo": socio.codigo, "socio_whatsapp": socio.telefono,
    })
    pdf_path = Path("data/presupuestos") / f"presupuesto_{presu.id}.pdf"
    await html_to_pdf(html, pdf_path)
    presu.pdf_path = str(pdf_path)
    db.commit()

    notificar_rodrigo(
        db,
        f"📋 *Nuevo presupuesto generado*\n"
        f"Socio: {socio.codigo} ({socio.nombre})\n"
        f"Cliente: {cliente_nombre} {cliente_apellido} · WhatsApp {cliente_whatsapp}\n"
        f"Localidad: {cliente_localidad}\n"
        f"Producto: {label_categoria} — {producto}\n"
        f"Forma de pago: {'Financiado' if presu.forma_pago == 'financiado' else 'Contado'}\n"
        f"Presupuesto ID: {presu.id}",
    )

    return {"ok": True, "presupuesto_id": presu.id, "pdf_url": f"/api/socio/presupuestos/{presu.id}/pdf"}


@router.get("/api/socio/presupuestos")
async def listar_mis_presupuestos(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    items = db.query(Presupuesto).filter(Presupuesto.aliado_codigo == socio.codigo).order_by(Presupuesto.id.desc()).all()
    return {"total": len(items), "presupuestos": [_presupuesto_dict(p) for p in items]}


@router.get("/api/socio/presupuestos/{presupuesto_id}/pdf")
async def descargar_mi_presupuesto(presupuesto_id: int, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id, Presupuesto.aliado_codigo == socio.codigo).first()
    if not p or not p.pdf_path or not Path(p.pdf_path).exists():
        raise HTTPException(404, "Presupuesto no encontrado")
    return FileResponse(p.pdf_path, media_type="application/pdf", filename=f"Presupuesto_{p.id}.pdf")


def _presupuesto_dict(p: "Presupuesto") -> dict:
    return {
        "id": p.id, "aliado_codigo": p.aliado_codigo, "categoria": p.categoria, "producto": p.producto,
        "forma_pago": p.forma_pago, "cuotas": p.cuotas,
        "precio_lista": p.precio_lista, "precio_contado": p.precio_contado,
        "cuota_mensual": p.cuota_mensual, "ingreso_inicial": p.ingreso_inicial, "total_financiado": p.total_financiado,
        "cliente_nombre": p.cliente_nombre, "cliente_apellido": p.cliente_apellido,
        "cliente_whatsapp": p.cliente_whatsapp, "cliente_email": p.cliente_email, "cliente_localidad": p.cliente_localidad,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/api/admin/presupuestos")
async def admin_listar_presupuestos(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Todos los presupuestos generados por todos los socios — trazabilidad de leads."""
    _require_gestion_interna(x_api_key, current_user)
    items = db.query(Presupuesto).order_by(Presupuesto.id.desc()).all()
    return {"total": len(items), "presupuestos": [_presupuesto_dict(p) for p in items]}


@router.get("/api/admin/presupuestos/{presupuesto_id}/pdf")
async def admin_descargar_presupuesto(
    presupuesto_id: int, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    from fastapi.responses import FileResponse
    _require_gestion_interna(x_api_key, current_user)
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
    if not p or not p.pdf_path or not Path(p.pdf_path).exists():
        raise HTTPException(404, "Presupuesto no encontrado")
    return FileResponse(p.pdf_path, media_type="application/pdf", filename=f"Presupuesto_{p.id}.pdf")


# ─── Flete — tabla propia del canal de socios ─────────────────────────────────
# Contado: SIEMPRE se cobra, nunca se bonifica. Financiado: se calcula igual,
# pero puede ofrecerse bonificado como argumento de cierre (decisión humana al
# cerrar la operación — el sistema no lo pone en $0 automáticamente).
FLETE_KM_ALTO = 5500
FLETE_KM_BAJO = 3500
_MODELOS_FLETE_ALTO_PISCINA = {"Playa y Abanico", "Arco Romano Grande", "Playa y Abanico Chica", "Playa y Abanico Mediana", "Playa y Abanico Grande", "Arco Romano Grande Recto", "Arco Romano Grande Curvo"}


def _flete_por_km(tipo: str, modelo_o_m2) -> int:
    if tipo.upper() == "MODULO":
        try:
            m2 = float(modelo_o_m2)
        except (TypeError, ValueError):
            return FLETE_KM_BAJO
        return FLETE_KM_ALTO if m2 >= 18 else FLETE_KM_BAJO
    return FLETE_KM_ALTO if str(modelo_o_m2) in _MODELOS_FLETE_ALTO_PISCINA else FLETE_KM_BAJO


@router.get("/api/socio/ficha-producto")
async def ficha_producto_pdf(tipo: str, modelo: str, socio: Aliado = Depends(require_socio)):
    """Genera una ficha de producto en PDF, lista para compartir con un cliente."""
    from utils.documentos import render_html, html_to_pdf

    def _money(v):
        return f"{(v or 0):,.0f}".replace(",", ".")

    tipo_norm = "PISCINA" if tipo.upper() == "PISCINA" else "MODULO"
    cat = load_catalogo()
    seccion = cat["piscinas"] if tipo_norm == "PISCINA" else cat["modulos"]
    precio_lista = seccion.get("precios_lista", {}).get(modelo)
    precio_contado = seccion.get("precios", {}).get(modelo)
    if not precio_lista:
        raise HTTPException(404, f"Modelo '{modelo}' no encontrado en el catálogo")

    factor = 2.0
    filas = ""
    for n in (12, 24, 36, 48, 60):
        cuota = precio_lista / (n + factor)
        ingreso = cuota * factor
        filas += f"<tr><td>{n}</td><td>$ {_money(cuota)}</td><td>$ {_money(ingreso)}</td><td>$ {_money(ingreso + cuota * n)}</td></tr>"

    titulo = f"{'Piscina de fibra' if tipo_norm=='PISCINA' else 'Módulo Wood Frame'} — {modelo}{'' if tipo_norm=='PISCINA' else ' m²'}"
    html = render_html("ficha_producto.html", {
        "titulo": titulo,
        "precio_lista": _money(precio_lista),
        "precio_contado": _money(precio_contado) if precio_contado else "Consultar",
        "tabla_filas": filas,
    })
    pdf_path = Path("data/fichas") / f"ficha_{tipo_norm}_{modelo}.pdf".replace(" ", "_")
    await html_to_pdf(html, pdf_path)

    from fastapi.responses import FileResponse
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"Ficha_{titulo}.pdf")


@router.get("/api/socio/flete")
async def socio_calcular_flete(
    tipo: str, modelo: Optional[str] = None, m2: Optional[float] = None,
    distancia_km: float = 0, financiado: bool = False,
    socio: Aliado = Depends(require_socio),
):
    """
    Calcula el flete desde la fábrica en Zárate. Siempre devuelve el costo real
    calculado — en contado se cobra sin excepción; en financiado se marca
    "bonificable" para que el socio pueda ofrecerlo como argumento de cierre,
    pero la aplicación de ese descuento es una decisión al cerrar la venta,
    no algo que el sistema resuelva solo.
    """
    valor_km = _flete_por_km(tipo, modelo if tipo.upper() != "MODULO" else m2)
    flete_total = round(valor_km * distancia_km)
    return {
        "tipo": tipo, "distancia_km": distancia_km, "flete_por_km": valor_km,
        "flete_total": flete_total,
        "bonificable": bool(financiado),
        "origen": "Zárate, Buenos Aires",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BIBLIOTECA DE CONTENIDOS
# ═══════════════════════════════════════════════════════════════════════════════

_GUIAS_SEED = [
    {
        "tipo": "guia", "categoria": "ventas", "orden": 1,
        "titulo": "Cómo empezar a vender tu primera semana",
        "descripcion": (
            "1) Armá una lista de 10 a 15 contactos: familia, vecinos y comercios de tu zona que puedan necesitar "
            "un módulo o una piscina. 2) Presentate como Socio Comercial de EcoFiver, con respaldo de fábrica y "
            "financiación propia directa. 3) Usá el catálogo y el simulador de tu panel para cotizar en el momento, "
            "con precisión. 4) Si te consultan por la instalación en una venta de contado, explicá que está incluida "
            "en la mayoría de los casos, y que fuera del área de cobertura directa se coordina con tu equipo o un "
            "instalador de la zona. 5) Al cerrar la venta, cargala desde tu panel el mismo día."
        ),
    },
    {
        "tipo": "guia", "categoria": "ventas", "orden": 2,
        "titulo": "Cómo explicarle el plan de pagos a un cliente financiado",
        "descripcion": (
            "1) Cotizá con el Simulador de tu panel: precio de lista, cantidad de cuotas y valor de cada una. "
            "2) Explicale que la inscripción equivale a 2 cuotas del plan — la puede pagar completa de una vez, "
            "o en partes: la primera parte (la seña, el monto que él elija) ya genera el contrato, y tiene 30 "
            "días para completar el resto. 3) En cuanto hace ese primer pago, descargás el contrato desde tu "
            "panel y se lo mandás — lo confirma con un link, sin papeles. 4) Al completar el 100% de la "
            "inscripción, se emite un recibo y el plan queda activo. 5) Nuestro equipo hace una llamada de "
            "bienvenida para confirmar todo, y ahí se libera tu comisión."
        ),
    },
    {
        "tipo": "guia", "categoria": "redes", "orden": 3,
        "titulo": "Ideas para publicar en redes esta semana",
        "descripcion": (
            "• Lunes: una foto de un módulo o piscina del catálogo con el precio y la cuota más baja. "
            "• Miércoles: un video corto de 15-20 segundos mostrando el simulador de cuotas de tu panel. "
            "• Viernes: una historia con la pregunta \"¿Sabías que podés financiar directo de fábrica, sin banco?\" "
            "seguida de tu contacto. Etiquetá siempre a @ecomodulosypiscinas si usás material oficial de la Biblioteca."
        ),
    },
    {
        "tipo": "guia", "categoria": "redes", "orden": 4,
        "titulo": "Cómo generar contenido con tu celular",
        "descripcion": (
            "No necesitás equipo profesional. Grabá en horizontal, con buena luz natural (de día, cerca de una "
            "ventana o al aire libre). Mostrá el producto real si tenés fotos de entregas de la Biblioteca, o "
            "mostrate a vos mismo explicando el Plan 18 Pasos con tus palabras — la naturalidad vende más que la "
            "perfección. Un video corto y genuino funciona mejor que uno largo y armado."
        ),
    },
    {
        "tipo": "guia", "categoria": "ventas", "orden": 5,
        "titulo": "Objeciones frecuentes de clientes y cómo responderlas",
        "descripcion": (
            "\"¿Y si no me aprueban?\" → La aprobación es simple y directa de fábrica, sin recibo de sueldo ni "
            "garante. \"¿Por qué no un banco?\" → Sin intermediarios, las cuotas son más accesibles y el trámite "
            "más ágil. \"¿Y la instalación?\" → Está incluida en financiado y en la mayoría de las ventas de "
            "contado; fuera del área de cobertura directa, se coordina con tu equipo o un instalador de la zona. "
            "\"Quiero verlo antes\" → Mostrale el catálogo con fotos reales y ofrecele una videollamada con el equipo."
        ),
    },
    {
        "tipo": "guia", "categoria": "operacion", "orden": 6,
        "titulo": "Recorrido completo del panel — qué hace cada sección",
        "descripcion": (
            "Inicio: tu resumen general (comisiones, ventas cargadas, tu progreso). Catálogo y precios: todos "
            "los productos con sus precios reales — siempre cotizá desde acá, nunca de memoria. Simulador de "
            "cuotas: calculá la cuota exacta de un plan financiado antes de ofrecerlo. Cargar venta: acá "
            "registrás cada operación — elegís categoría y producto, el precio se autocompleta, y en "
            "financiado podés chequear la situación crediticia del cliente antes de avanzar. Mis ventas: el "
            "estado de cada operación, paso a paso, con los documentos para descargar. Mis comisiones: cuánto "
            "tenés pendiente y cuánto ya te transferimos. Ranking: tu posición a nivel nacional. Mi Empresa: "
            "los datos institucionales que te puede pedir un cliente. Biblioteca de contenidos: fotos, videos "
            "y copys listos para usar. Capacitación: donde estás ahora. Mi perfil: tus datos y documentación."
        ),
    },
    {
        "tipo": "guia", "categoria": "operacion", "orden": 7,
        "titulo": "Checklist antes de cargar una venta",
        "descripcion": (
            "1) ¿Cotizaste el precio exacto desde el Catálogo (no de memoria)? 2) Si es financiado, ¿corriste "
            "el Scoring del cliente? 3) ¿Tenés el nombre completo, WhatsApp y localidad del cliente "
            "cargados correctamente? 4) Si es una piscina fuera del área de cobertura directa, ¿elegiste bien "
            "el nivel de instalación (con instalación / casco + equipo / casco solo)? 5) En financiado, ¿le "
            "explicaste al cliente que la inscripción equivale a 2 cuotas y que puede pagarla en partes? "
            "Con estos 5 puntos resueltos, cargá la venta con confianza — el resto lo maneja el sistema."
        ),
    },
]


_COPYS_SEED = [
    # ── General / marca ──
    {"tipo": "copy", "categoria": "general", "orden": 1,
     "titulo": "Presentación — quién sos como Socio Comercial",
     "descripcion": (
         "🌿 Ahora represento a EcoFiver en [TU ZONA] — fábrica propia en Zárate con más de 15 años haciendo "
         "módulos habitacionales y piscinas de fibra. Puedo cotizarte al instante, con financiación propia "
         "directa de fábrica (sin banco, sin recibo de sueldo). Contactame por acá 👇"
     )},
    {"tipo": "copy", "categoria": "general", "orden": 2,
     "titulo": "Financiación propia — argumento de cierre",
     "descripcion": (
         "💳 Financiamos directo de fábrica, en cuotas propias fijas, sin pasar por bancos ni tarjetas. "
         "Solo pedimos una entrada + cuotas mensuales, con aprobación simple y rápida. Y si en algún momento "
         "querés adelantar la entrega, después de cierta cuota podés hacerlo sin dejar de pagar el resto del plan."
     )},
    {"tipo": "copy", "categoria": "general", "orden": 3,
     "titulo": "Garantía y respaldo de fábrica",
     "descripcion": (
         "🏭 Esto no es un catálogo genérico: fabricamos en nuestra propia planta en Zárate, Buenos Aires. "
         "Todos los productos tienen 10 años de garantía de fábrica. Podés venir a ver la planta o coordinar "
         "el retiro sin cargo en nuestros puntos de CABA (San Telmo) o Zona Oeste (Paso del Rey)."
     )},
    # ── Piscinas de fibra (Arco Romano / Playa y Abanico) ──
    {"tipo": "copy", "categoria": "piscinas", "orden": 10,
     "titulo": "Piscinas de fibra — línea Arco Romano",
     "descripcion": (
         "🏊 Línea Arco Romano: piscinas de fibra de vidrio en 3 tamaños (Chico, Mediano, Grande) y con o sin "
         "desnivel de profundidad. Instalación en el día una vez en obra. Consultame el tamaño que se ajusta "
         "a tu espacio y te paso precio contado o en cuotas."
     )},
    {"tipo": "copy", "categoria": "piscinas", "orden": 11,
     "titulo": "Piscinas grandes — línea Playa y Abanico",
     "descripcion": (
         "🌊 Para patios grandes: la línea Playa y Abanico (9,20 x 3,80m, hasta 53.000 litros) es nuestro modelo "
         "más grande, ideal para uso familiar o quinchos de fin de semana. Financiación propia disponible — "
         "pedime el simulador de cuotas para tu presupuesto."
     )},
    {"tipo": "copy", "categoria": "piscinas", "orden": 12,
     "titulo": "Piscinas hidromasaje / bañeras — spa en casa",
     "descripcion": (
         "🛁 ¿Buscás algo más compacto? Tenemos bañeras y mini piscinas hidromasaje (rectangulares, circulares, "
         "esquineras) ideales para baños, terrazas o SPA en casa. Se pueden sumar accesorios: blower de burbujas, "
         "iluminación LED, grifería integrada y ozonizador. Te armo la cotización completa con lo que necesites."
     )},
    # ── Módulos habitacionales ──
    {"tipo": "copy", "categoria": "modulos", "orden": 20,
     "titulo": "Módulos habitacionales — 6, 12, 18 y 24 m²",
     "descripcion": (
         "🏠 Módulos de fábrica en 4 tamaños (6, 12, 18 y 24 m²), en versión BASE o PREMIUM. Incluyen aberturas, "
         "pintura completa e instalación eléctrica interna. Sirven como vivienda, ampliación, depósito u oficina. "
         "Entrega y montaje en el mismo día para 6/12/18 m² — te cotizo el tamaño y la versión que necesites."
     )},
    {"tipo": "copy", "categoria": "modulos", "orden": 21,
     "titulo": "Módulo depósito — solución rápida y económica",
     "descripcion": (
         "📦 ¿Necesitás un espacio extra ya? El módulo de 6 m² es nuestra opción más accesible: depósito, "
         "herramientas, oficina de obra o cuarto extra. Entrega y montaje en el mismo día. Preguntame el precio "
         "contado o en cuotas propias."
     )},
    {"tipo": "copy", "categoria": "modulos", "orden": 22,
     "titulo": "Vivienda modular — ampliá o mudate a estrenar",
     "descripcion": (
         "🏡 Nuestros módulos de 18 y 24 m² funcionan como vivienda modular completa: dormitorio, ampliación "
         "familiar o casa chica llave en mano. Fabricación propia, financiación directa y garantía de 10 años. "
         "Pedime el simulador para ver el plan de cuotas que más te convenga."
     )},
    # ── Objeciones / cierre ──
    {"tipo": "copy", "categoria": "ventas", "orden": 30,
     "titulo": "Respuesta lista — \"¿Y si no me aprueban el crédito?\"",
     "descripcion": (
         "No pedimos recibo de sueldo ni garante — es una aprobación simple y directa de fábrica, no un crédito "
         "bancario. En la mayoría de los casos te puedo confirmar en el momento si tu plan queda aprobado."
     )},
    {"tipo": "copy", "categoria": "ventas", "orden": 31,
     "titulo": "Respuesta lista — \"¿La instalación está incluida?\"",
     "descripcion": (
         "Sí, está incluida en financiado y en la mayoría de las ventas de contado. Si tu zona queda fuera del "
         "área de instalación directa, te entrego el producto en formato casco (o casco con equipo de filtrado "
         "completo) y coordinamos juntos la instalación con tu equipo o un instalador de confianza."
     )},
]


def seed_biblioteca_socios(db: Session):
    """Carga las guías y los copys reales una sola vez (idempotente por título)."""
    for g in _GUIAS_SEED + _COPYS_SEED:
        existe = db.query(MaterialSocio).filter(MaterialSocio.titulo == g["titulo"]).first()
        if not existe:
            db.add(MaterialSocio(**g))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# COMISIONES — porcentaje configurable desde el panel de admin, por tipo de
# venta y opcionalmente por producto/modelo. Default de hoy: 5% en contado
# (cualquier producto) y 100% de la primera cuota en financiado.
# ═══════════════════════════════════════════════════════════════════════════════

def seed_comision_config(db: Session):
    """Crea los valores por defecto una sola vez (si la tabla está vacía)."""
    if db.query(ComisionConfig).first():
        return
    db.add(ComisionConfig(tipo_venta="contado", producto=None, modelo=None, porcentaje=0.05))
    db.add(ComisionConfig(tipo_venta="financiado", producto=None, modelo=None, porcentaje=1.0))
    db.commit()


def obtener_porcentaje_comision(db: Session, tipo_venta: str, producto: str = None, modelo: str = None) -> float:
    """
    Resuelve el % de comisión vigente por especificidad: modelo exacto >
    producto (todo modelo) > default global de ese tipo_venta. Si no hay
    ninguna config cargada (no debería pasar tras el seed), cae a un
    fallback fijo para no romper el cálculo.
    """
    producto = (producto or "").upper() or None
    q = db.query(ComisionConfig).filter(ComisionConfig.tipo_venta == tipo_venta)

    if producto and modelo:
        row = q.filter(ComisionConfig.producto == producto, ComisionConfig.modelo == modelo).first()
        if row:
            return row.porcentaje
    if producto:
        row = q.filter(ComisionConfig.producto == producto, ComisionConfig.modelo.is_(None)).first()
        if row:
            return row.porcentaje
    row = q.filter(ComisionConfig.producto.is_(None), ComisionConfig.modelo.is_(None)).first()
    if row:
        return row.porcentaje
    return 0.05 if tipo_venta == "contado" else 1.0


_CATEGORIAS_CATALOGO_SIMPLES = {
    "hidromasajes": "Hidromasaje", "baneras": "Bañera", "receptaculos": "Receptáculo",
    "accesorios_piscinas": "Accesorio de piscina", "banios_quimicos": "Baño químico",
    "garitas_seguridad": "Garita de seguridad", "cuchas_perros": "Cucha", "reposeras": "Reposera",
    "depositos_jardin": "Depósito de jardín",
}


def _extraer_fotos_catalogo(cat: dict) -> list:
    """
    Recorre el catálogo completo (todas las categorías, cualquiera sea su forma
    exacta) y devuelve [{categoria, producto, url}, ...] para cada foto real
    cargada. Genérico a propósito: cada rubro tiene una forma algo distinta
    (piscinas/módulos guardan fotos como {modelo: [urls]} al nivel de la
    categoría; combos y el resto las guardan por ítem, directo o bajo
    'modelos') — así no hay que tocar esta función cada vez que se agrega un
    producto nuevo, solo cuando se agrega una categoría con una forma distinta.
    """
    fotos = []

    for modelo, urls in (cat.get("piscinas", {}).get("fotos") or {}).items():
        for url in (urls or []):
            if url:
                fotos.append({"categoria": "piscinas", "producto": modelo, "url": url})

    for modelo, urls in (cat.get("modulos", {}).get("fotos") or {}).items():
        for url in (urls or []):
            if url:
                fotos.append({"categoria": "modulos", "producto": f"Módulo {modelo}m²", "url": url})

    for nombre, datos in (cat.get("combos") or {}).items():
        if isinstance(datos, dict):
            for url in (datos.get("fotos") or []):
                if url:
                    fotos.append({"categoria": "combos", "producto": nombre, "url": url})

    for cat_key in _CATEGORIAS_CATALOGO_SIMPLES:
        bloque = cat.get(cat_key) or {}
        items = bloque.get("modelos") if isinstance(bloque.get("modelos"), dict) else bloque
        if not isinstance(items, dict):
            continue
        for nombre, datos in items.items():
            if isinstance(datos, dict):
                for url in (datos.get("fotos") or []):
                    if url:
                        fotos.append({"categoria": cat_key, "producto": nombre, "url": url})

    return fotos


def sincronizar_biblioteca_catalogo(db: Session) -> int:
    """
    Reemplaza todo el material tipo=imagen con origen='catalogo' por el estado
    ACTUAL de fotos del catálogo — idempotente, se puede correr las veces que
    haga falta (por ejemplo después de cargar fotos nuevas a un producto).
    Nunca toca el material cargado a mano (origen='manual').
    """
    cat = load_catalogo()
    fotos = _extraer_fotos_catalogo(cat)

    db.query(MaterialSocio).filter(MaterialSocio.origen == "catalogo").delete()

    orden = 100  # después de las guías/copys cargados a mano
    for f in fotos:
        db.add(MaterialSocio(
            tipo="imagen", categoria=f["categoria"], titulo=f["producto"],
            descripcion=f"Foto oficial de {f['producto']} - lista para usar en tus publicaciones.",
            url_externa=f["url"], orden=orden, origen="catalogo",
        ))
        orden += 1
    db.commit()
    return len(fotos)


def sincronizar_biblioteca_marketing(db: Session) -> int:
    """
    Trae a la Biblioteca de socios el contenido de marketing ya aprobado o
    publicado en Ecopost (flyers, fotos y videos, cada uno con su copy y
    hashtags listos) — el mismo material que ya se usa para las redes
    propias de EcoFiver, disponible también para que lo usen los socios.
    Idempotente: reemplaza todo lo de origen='ecopost' en cada corrida.
    """
    from database.models import ContenidoEcopost
    import secrets as _secrets

    crm_base = os.getenv("CRM_BASE_URL", "https://eco-crm-production.up.railway.app").rstrip("/")

    db.query(MaterialSocio).filter(MaterialSocio.origen == "ecopost").delete()

    items = db.query(ContenidoEcopost).filter(ContenidoEcopost.estado.in_(["aprobado", "publicado"])).all()
    orden, n = 200, 0
    for c in items:
        url, tipo = None, ("video" if c.video_token else "imagen")
        if c.video_token:
            url = f"{crm_base}/pub/video/{c.video_token}"
        elif c.imagen_url:
            url = c.imagen_url
        elif c.imagen_base64:
            if not c.public_token:
                c.public_token = _secrets.token_urlsafe(32)
            url = f"{crm_base}/pub/img/{c.public_token}"
        if not url:
            continue

        descripcion = (c.copy_texto or "").strip()
        if c.copy_hashtags:
            descripcion = (descripcion + "\n\n" + c.copy_hashtags).strip()

        db.add(MaterialSocio(
            tipo=tipo, categoria=(c.producto or "general").lower(),
            titulo=c.titulo or c.modelo_especifico or "Contenido de marketing",
            descripcion=descripcion, url_externa=url, orden=orden, origen="ecopost",
        ))
        orden += 1
        n += 1
    db.commit()
    return n


def _material_dict(m: MaterialSocio) -> dict:
    return {
        "id": m.id, "tipo": m.tipo, "categoria": m.categoria, "titulo": m.titulo,
        "descripcion": m.descripcion,
        "url": m.url_externa or (f"/api/socio/biblioteca/{m.id}/archivo" if m.archivo_path else None),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOEVALUACIÓN — el quiz de onboarding, ahora como contenido educativo
# ═══════════════════════════════════════════════════════════════════════════════
# No bloquea ni aprueba nada — el registro es directo. Sirve para que el socio
# se autoevalúe si entendió bien las reglas. Fuente de verdad de las preguntas:
# eco-multiagente/tools/franco_quiz.py (mantener ambas listas sincronizadas).
QUIZ_AUTOEVALUACION = [
    {"pregunta": "¿En qué zona geográfica opera el programa de Socios Comerciales?", "respuesta": "En todo el país."},
    {"pregunta": "¿Quién cierra una venta, contado o financiada: el Socio o el equipo de EcoFiver?", "respuesta": "El Socio Comercial — hace la operación completa, de punta a punta."},
    {"pregunta": "¿Con qué herramienta cotizás precios y cuotas?", "respuesta": "Con el catálogo y el simulador de tu panel — nunca de memoria."},
    {"pregunta": "¿Tenés horario fijo de trabajo?", "respuesta": "No. Es un vínculo comercial, sin obligación de horario ni de asistencia."},
    {"pregunta": "¿Cómo se calcula tu comisión en una venta financiada?", "respuesta": "El 100% del valor de la primera cuota del plan. El detalle actualizado siempre está disponible en \"Mis comisiones\"."},
    {"pregunta": "¿Cuándo se libera tu comisión en una venta financiada?", "respuesta": "Cuando el equipo hace la llamada de bienvenida (auditoría) y confirma que el cliente entendió el plan."},
    {"pregunta": "¿Cómo se calcula tu comisión en una venta de contado?", "respuesta": "El 5% del precio de venta — se libera contra entrega y cobro. El detalle actualizado siempre está disponible en \"Mis comisiones\"."},
    {"pregunta": "¿Necesitás Monotributo para operar?", "respuesta": "Eventualmente sí, para poder facturar tus comisiones."},
    {"pregunta": "¿La instalación está incluida en una venta de contado?", "respuesta": "En general sí. Fuera del área de cobertura de instalación directa, el producto se entrega en formato casco y la instalación queda a cargo del Socio o de un instalador de su zona."},
    {"pregunta": "¿Desde qué cuota se puede pedir la entrega anticipada (licitación)?", "respuesta": "Desde la cuota 6 en viviendas, y desde la cuota 3 en piscinas."},
    {"pregunta": "¿A quién le escribís si tenés dudas sobre una venta en curso?", "respuesta": "Al WhatsApp del programa de Socios Comerciales, donde te atiende el equipo de EcoFiver."},
]


@router.get("/api/socio/quiz")
async def socio_quiz(socio: Aliado = Depends(require_socio)):
    """Autoevaluación educativa — no bloquea ni aprueba nada."""
    return {"preguntas": QUIZ_AUTOEVALUACION}


@router.get("/api/socio/biblioteca")
async def socio_biblioteca(tipo: Optional[str] = None, categoria: Optional[str] = None, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    _require_verificado(socio)
    q = db.query(MaterialSocio).filter(MaterialSocio.activo == True)
    if tipo:
        q = q.filter(MaterialSocio.tipo == tipo)
    if categoria:
        q = q.filter(MaterialSocio.categoria == categoria)
    items = q.order_by(MaterialSocio.orden, MaterialSocio.id.desc()).all()
    return {"total": len(items), "materiales": [_material_dict(m) for m in items]}


@router.get("/api/socio/biblioteca/{material_id}/archivo")
async def socio_biblioteca_archivo(material_id: int, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    _require_verificado(socio)
    from fastapi.responses import FileResponse
    m = db.query(MaterialSocio).filter(MaterialSocio.id == material_id).first()
    if not m or not m.archivo_path or not os.path.exists(m.archivo_path):
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(m.archivo_path)


@router.post("/api/materiales-socio")
async def crear_material_socio(
    tipo: str = Form(...), categoria: str = Form("general"), titulo: str = Form(""),
    descripcion: str = Form(""), url_externa: Optional[str] = Form(None),
    archivo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Admin/equipo interno carga material a la biblioteca del panel de socios."""
    _require_gestion_interna(x_api_key, current_user)

    archivo_path = None
    if archivo:
        ext = os.path.splitext(archivo.filename or "")[1] or ".bin"
        fname = f"{secrets.token_hex(8)}{ext}"
        archivo_path = str(BIBLIOTECA_DIR / fname)
        with open(archivo_path, "wb") as f:
            f.write(await archivo.read())

    m = MaterialSocio(
        tipo=tipo, categoria=categoria, titulo=titulo, descripcion=descripcion,
        url_externa=url_externa, archivo_path=archivo_path,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"ok": True, **_material_dict(m)}


@router.get("/api/admin/materiales-socio")
async def admin_listar_materiales(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Lista todo el material (activo o no) para el panel de admin — a
    diferencia de /api/socio/biblioteca, no requiere sesión de socio."""
    _require_gestion_interna(x_api_key, current_user)
    items = db.query(MaterialSocio).order_by(MaterialSocio.id).all()
    return {"total": len(items), "materiales": [_material_dict(m) for m in items]}


@router.put("/api/materiales-socio/{material_id}")
async def editar_material_socio(
    material_id: int, request: Request, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Corrige título/descripción/categoría de un material ya cargado, sin
    tener que volver a subir el archivo."""
    _require_gestion_interna(x_api_key, current_user)
    m = db.query(MaterialSocio).filter(MaterialSocio.id == material_id).first()
    if not m:
        raise HTTPException(404, "No encontrado")
    data = await request.json()
    for campo in ("titulo", "descripcion", "categoria"):
        if campo in data:
            setattr(m, campo, data[campo])
    db.commit()
    return {"ok": True, **_material_dict(m)}


@router.delete("/api/materiales-socio/{material_id}")
async def borrar_material_socio(
    material_id: int, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    _require_gestion_interna(x_api_key, current_user)
    m = db.query(MaterialSocio).filter(MaterialSocio.id == material_id).first()
    if not m:
        raise HTTPException(404, "No encontrado")
    m.activo = False
    db.commit()
    return {"ok": True}


@router.post("/api/materiales-socio/sincronizar-catalogo")
async def sincronizar_catalogo_endpoint(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Vuelve a leer el catálogo y Ecopost, y actualiza en la Biblioteca todas
    las fotos/videos disponibles (piscinas, módulos, hidromasajes, bañeras,
    accesorios, flyers y reels de marketing, etc). Usar después de cargar
    fotos nuevas a un producto, o de aprobar contenido nuevo en Ecopost."""
    _require_gestion_interna(x_api_key, current_user)
    n1 = sincronizar_biblioteca_catalogo(db)
    n2 = sincronizar_biblioteca_marketing(db)
    return {"ok": True, "fotos_catalogo": n1, "contenido_marketing": n2, "total": n1 + n2}


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL ADMINISTRATIVO — resumen, listado y baja de socios (equipo interno)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/admin/socios/resumen")
async def admin_socios_resumen(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    _require_gestion_interna(x_api_key, current_user)
    todos = db.query(Aliado).filter(Aliado.estado == "activo").all()
    total = len(todos)
    verificados = sum(1 for a in todos if _esta_verificado(a))
    con_perfil = sum(1 for a in todos if a.perfil_completo)
    con_whatsapp = sum(1 for a in todos if a.whatsapp_verificado)
    ventas_contado = db.query(VentaContado).filter(VentaContado.aliado_codigo.isnot(None)).count()
    ventas_financiado = db.query(VentaFinanciada).filter(VentaFinanciada.aliado_codigo.isnot(None)).count()
    comision_pendiente = sum(c.monto or 0 for c in db.query(Comision).filter(Comision.estado == "pendiente").all())
    comision_liquidada = sum(c.monto or 0 for c in db.query(Comision).filter(Comision.estado == "liquidada").all())
    return {
        "total_socios": total, "verificados": verificados, "con_perfil_completo": con_perfil,
        "con_whatsapp_verificado": con_whatsapp,
        "ventas_contado_cargadas": ventas_contado, "ventas_financiado_cargadas": ventas_financiado,
        "comision_pendiente": round(comision_pendiente, 2), "comision_liquidada": round(comision_liquidada, 2),
    }


@router.get("/api/admin/socios")
async def admin_socios_lista(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Listado completo de socios con su estado y actividad — para
    trazabilidad desde el panel interno (cuántos hay, quién está verificado,
    cuánto vendió cada uno, cuánto tiene pendiente de cobrar)."""
    _require_gestion_interna(x_api_key, current_user)
    filas = []
    for a in db.query(Aliado).order_by(Aliado.id.desc()).all():
        n_contado = db.query(VentaContado).filter(VentaContado.aliado_codigo == a.codigo).count()
        n_financiado = db.query(VentaFinanciada).filter(VentaFinanciada.aliado_codigo == a.codigo).count()
        pendiente = sum(c.monto or 0 for c in db.query(Comision).filter(Comision.aliado_codigo == a.codigo, Comision.estado == "pendiente").all())
        liquidada = sum(c.monto or 0 for c in db.query(Comision).filter(Comision.aliado_codigo == a.codigo, Comision.estado == "liquidada").all())
        filas.append({
            "codigo": a.codigo, "nombre": a.nombre, "email": a.email, "telefono": a.telefono or "",
            "zona": a.zona or "", "estado": a.estado, "interes_venta": a.interes_venta or "",
            "origen_registro": a.origen_registro or "",
            "fecha_alta": a.fecha_alta.isoformat() if a.fecha_alta else None,
            "verificado": _esta_verificado(a), "perfil_completo": bool(a.perfil_completo),
            "whatsapp_verificado": bool(a.whatsapp_verificado),
            "ventas_contado": n_contado, "ventas_financiado": n_financiado,
            "comision_pendiente": round(pendiente, 2), "comision_liquidada": round(liquidada, 2),
        })
    return {"total": len(filas), "socios": filas}


@router.delete("/api/admin/socios/{codigo}")
async def admin_eliminar_socio(
    codigo: str, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Elimina un socio y sus ventas/comisiones asociadas. Pensado para dar de
    baja cuentas de prueba — es definitivo, no tiene papelera de reciclaje."""
    _require_gestion_interna(x_api_key, current_user)
    socio = db.query(Aliado).filter(Aliado.codigo == codigo.upper()).first()
    if not socio:
        raise HTTPException(404, "Socio no encontrado")
    db.query(Comision).filter(Comision.aliado_codigo == socio.codigo).delete()
    db.query(VentaContado).filter(VentaContado.aliado_codigo == socio.codigo).delete()
    db.query(VentaFinanciada).filter(VentaFinanciada.aliado_codigo == socio.codigo).delete()
    db.query(Presupuesto).filter(Presupuesto.aliado_codigo == socio.codigo).delete()
    db.delete(socio)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENTACIÓN PROPIA DEL SOCIO (para poder cobrar)
# ═══════════════════════════════════════════════════════════════════════════════

async def _guardar_doc_socio(socio_codigo: str, tag: str, archivo: UploadFile) -> str:
    ext = os.path.splitext(archivo.filename or "")[1] or ".pdf"
    fname = f"{socio_codigo}_{tag}_{secrets.token_hex(6)}{ext}"
    path = str(DOCS_SOCIOS_DIR / fname)
    with open(path, "wb") as f:
        f.write(await archivo.read())
    return path


@router.post("/api/socio/documentos/monotributo")
async def subir_doc_monotributo(archivo: UploadFile = File(...), socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    socio.doc_monotributo_path = await _guardar_doc_socio(socio.codigo, "monotributo", archivo)
    db.commit()
    return {"ok": True}


@router.post("/api/socio/documentos/dni")
async def subir_doc_dni(archivo: UploadFile = File(...), socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    socio.doc_dni_path = await _guardar_doc_socio(socio.codigo, "dni", archivo)
    db.commit()
    return {"ok": True}


@router.post("/api/socio/comisiones/{comision_id}/factura")
async def subir_factura_comision(comision_id: int, archivo: UploadFile = File(...), socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """No es excluyente ni bloqueante del pago — solo respaldo si el socio tiene monotributo."""
    c = db.query(Comision).filter(Comision.id == comision_id, Comision.aliado_codigo == socio.codigo).first()
    if not c:
        raise HTTPException(404, "Comisión no encontrada")
    c.factura_path = await _guardar_doc_socio(socio.codigo, f"factura{comision_id}", archivo)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING BCRA — Central de Deudores (pública)
# ═══════════════════════════════════════════════════════════════════════════════

BCRA_API = "https://api.bcra.gob.ar/CentralDeDeudores/v1.0/Deudas"


def _calcular_cuit(prefijo: str, dni: str) -> str:
    """Calcula un CUIT/CUIL válido a partir de un DNI y un prefijo (20=varón, 27=mujer)."""
    dni = dni.zfill(8)
    base = prefijo + dni
    multiplicadores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(d) * m for d, m in zip(base, multiplicadores))
    verificador = 11 - (suma % 11)
    if verificador == 11:
        verificador = 0
    elif verificador == 10:
        verificador = 9  # ajuste práctico estándar para el dígito verificador 10
    return base + str(verificador)


async def _consultar_bcra_por_identificacion(identificacion: str) -> tuple:
    """Devuelve (situacion, detalle: dict, respuesta_raw, encontrado: bool). Lanza HTTPException solo ante un error real de red/servicio."""
    async with httpx.AsyncClient(timeout=15, verify=False) as client:
        r = await client.get(f"{BCRA_API}/{identificacion}")
        if r.status_code == 200:
            body = r.json()
            results = body.get("results") or {}
            periodos = results.get("periodos") or []
            if periodos:
                ultimo = periodos[0]  # la API devuelve el período más reciente primero
                entidades = ultimo.get("entidades") or []
                situaciones = [e.get("situacion") for e in entidades if e.get("situacion") is not None]
                detalle = {
                    "denominacion": results.get("denominacion"),
                    "periodo": ultimo.get("periodo"),
                    "cantidad_entidades": len(entidades),
                    "monto_total_miles": round(sum(e.get("monto") or 0 for e in entidades), 2),
                    "entidades": [
                        {
                            "entidad": e.get("entidad"),
                            "situacion": e.get("situacion"),
                            "monto_miles": e.get("monto"),
                            "dias_atraso_pago": e.get("diasAtrasoPago"),
                            "refinanciaciones": bool(e.get("refinanciaciones")),
                            "en_revision": bool(e.get("enRevision")),
                            "proceso_judicial": bool(e.get("procesoJud")),
                        }
                        for e in entidades
                    ],
                }
                if situaciones:
                    return max(situaciones), detalle, r.text, True  # la peor situación entre todas las entidades
            return None, None, r.text, True
        if r.status_code in (400, 404):
            # 404: sin antecedentes para esa identificación. 400 (típicamente por
            # longitud): se resuelve reintentando con otra identificación válida.
            return None, None, r.text, False
        raise HTTPException(502, "El servicio de Scoring no respondió correctamente, reintentá en un momento")


@router.post("/api/socio/scoring")
async def consultar_scoring(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Consulta la Central de Deudores del BCRA por DNI o CUIT — disponible en
    cualquier momento, no solo al cargar una venta. La Central de Deudores
    solo admite CUIT/CUIL (11 dígitos); si se ingresa un DNI (8 dígitos) se
    calculan y prueban los CUIT/CUIL más probables (varón y mujer) hasta
    encontrar antecedentes. Situación 5 o 6 no bloquean la venta — disparan
    pedirle al cliente una declaración jurada (requiere_declaracion_jurada=True).
    """
    data = await request.json()
    identificacion = re.sub(r"\D", "", data.get("dni") or data.get("cuit") or "")
    if not identificacion:
        raise HTTPException(400, "Falta DNI o CUIT")

    candidatos = [identificacion] if len(identificacion) == 11 else [
        _calcular_cuit("20", identificacion), _calcular_cuit("27", identificacion),
    ]

    situacion, detalle, respuesta_raw = None, None, ""
    try:
        for candidato in candidatos:
            situacion, detalle, respuesta_raw, encontrado = await _consultar_bcra_por_identificacion(candidato)
            if encontrado:
                break
    except httpx.HTTPError:
        raise HTTPException(502, "No se pudo conectar con el servicio de Scoring — reintentá en un momento")

    requiere_dj = situacion in (5, 6)

    log = ScoringBCRA(
        aliado_codigo=socio.codigo, cliente_dni=identificacion, situacion=situacion,
        requiere_declaracion_jurada=requiere_dj, respuesta_raw=respuesta_raw[:4000],
    )
    db.add(log)
    db.commit()

    mensaje = "Sin antecedentes registrados en la Central de Deudores." if situacion is None else f"Situación {situacion} en el sistema financiero."
    if requiere_dj:
        mensaje += " Se le va a solicitar al cliente una declaración jurada antes de avanzar — la operación continúa sin inconvenientes."

    return {
        "ok": True, "situacion": situacion, "requiere_declaracion_jurada": requiere_dj,
        "mensaje": mensaje, "detalle": detalle,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CARGA DE VENTAS — el socio hace la operación completa
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/socio/ventas/contado")
async def cargar_venta_contado(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Venta de contado cargada por el socio. La instalación está incluida por
    defecto; en piscinas vendidas fuera del área de cobertura directa (formato
    casco, con o sin equipo de filtrado), la coordina el propio socio, su
    equipo, o un instalador de su zona. El equipo interno se contacta con el
    cliente dentro de las 48hs.
    """
    _require_verificado(socio)
    data = await request.json()
    cliente_nombre = (data.get("cliente_nombre") or "").strip()
    if not cliente_nombre:
        raise HTTPException(400, "Falta el nombre del cliente")

    nivel_instalacion = (data.get("nivel_instalacion") or "con").strip()
    nota_instalacion = {
        "con": "Instalación incluida.",
        "sin_instalacion": "Formato casco + equipo de filtrado, SIN instalación — la coordina el socio o un instalador de su zona.",
        "sin_equipo": "Formato casco SOLO, sin instalación y sin equipo de filtrado — la coordina el socio o un instalador de su zona.",
    }.get(nivel_instalacion, "Instalación incluida.")

    venta = VentaContado(
        cliente_nombre=cliente_nombre,
        cliente_telefono=_normalizar_telefono(data.get("cliente_telefono") or ""),
        cliente_localidad=(data.get("cliente_localidad") or "").strip(),
        producto=(data.get("producto") or "").upper(),
        modelo_especifico=(data.get("modelo_especifico") or "").strip(),
        superficie_m2=data.get("superficie_m2"),
        precio_final=float(data.get("precio_final") or 0),
        forma_pago="CONTADO",
        estado="COORDINADO",
        modalidad_cobro="CONTRAENTREGA",  # se cobra contra la entrega en el domicilio
        cobro_estado="PENDIENTE",
        notas=f"Venta de socio comercial {socio.codigo}. {nota_instalacion} {data.get('notas', '')}".strip(),
        aliado_codigo=socio.codigo,
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    nivel_label = {
        "con": "Con instalación incluida",
        "sin_instalacion": "⚠️ SIN instalación (casco + equipo de filtrado) — la coordina el socio o un instalador de su zona",
        "sin_equipo": "⚠️ SIN instalación y SIN equipo de filtrado (casco solo) — la coordina el socio o un instalador de su zona",
    }.get(nivel_instalacion, "Con instalación incluida")

    notificar_rodrigo(
        db,
        f"🟣 *Nueva venta de contado*\n"
        f"Socio: {socio.codigo} ({socio.nombre}) · WhatsApp {socio.telefono or '—'}\n"
        f"Cliente: {cliente_nombre}\n"
        f"WhatsApp cliente: {venta.cliente_telefono or 'no cargado'}\n"
        f"Localidad: {venta.cliente_localidad or '—'}\n"
        f"Producto: {venta.producto} {venta.modelo_especifico}\n"
        f"Instalación: {nivel_label}\n"
        f"Monto: ${venta.precio_final:,.0f}\n"
        f"Cobro: contraentrega en el domicilio del cliente\n"
        f"⏰ Contactar al cliente dentro de las 48hs para confirmar fecha y detalles.\n"
        f"Venta ID: {venta.id}",
    )

    return {"ok": True, "venta_id": venta.id, "mensaje": "Venta cargada. El equipo va a contactar al cliente dentro de las 48hs."}


@router.post("/api/ventas-contado/{venta_id}/confirmacion-48hs")
async def confirmar_48hs_contado(
    venta_id: int, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
):
    """El equipo confirma que contactó al cliente dentro de las 48hs."""
    _require_gestion_interna(x_api_key, current_user)
    venta = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    venta.confirmacion_48hs_en = datetime.now()
    db.commit()
    _notificar_socio(db, venta.aliado_codigo, f"📞 Ya contactamos a {venta.cliente_nombre} para coordinar la entrega. Podés seguir el estado desde tu panel.")
    return {"ok": True}


@router.post("/api/ventas-contado/{venta_id}/entregada-cobrada")
async def marcar_entregada_cobrada(
    venta_id: int, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Entrega + cobro en el domicilio del cliente. Libera la comisión del socio
    (% configurable desde el panel de admin, ver ComisionConfig) — cuenta
    también para el ranking en este momento.
    """
    _require_gestion_interna(x_api_key, current_user)
    venta = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    venta.cobro_estado = "COBRADO"
    venta.cobro_fecha = datetime.now()
    db.commit()

    if venta.aliado_codigo:
        pct = obtener_porcentaje_comision(db, "contado", venta.producto, venta.modelo_especifico)
        comision = Comision(
            aliado_codigo=venta.aliado_codigo,
            tipo="contado",
            monto=round((venta.precio_final or 0) * pct, 2),
            estado="pendiente",
            venta_contado_id=venta.id,
        )
        db.add(comision)
        db.commit()
        _notificar_socio(db, venta.aliado_codigo, f"✅ Se entregó y cobró la venta de {venta.cliente_nombre}. Se generó tu comisión de ${comision.monto:,.0f}".replace(",", ".") + " — la vas a ver como pendiente en tu panel hasta que te la transfiramos.")
        return {"ok": True, "comision_generada": comision.monto}
    return {"ok": True, "comision_generada": None}


@router.post("/api/socio/ventas/financiado")
async def cargar_venta_financiada(request: Request, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Venta financiada cargada por el socio. El precio/cuota se resuelve SIEMPRE
    contra el catálogo (nunca un número tipeado a mano) para que no haya
    inconsistencias con las fichas oficiales.
    """
    _require_verificado(socio)
    data = await request.json()
    cliente_nombre = (data.get("cliente_nombre") or "").strip()
    cliente_dni = (data.get("cliente_dni") or "").strip()
    producto = (data.get("producto") or "").upper()
    modelo = (data.get("modelo_especifico") or "").strip()
    cantidad_cuotas = int(data.get("cantidad_cuotas") or 0)

    if not cliente_nombre or not cliente_dni or not modelo or not cantidad_cuotas:
        raise HTTPException(400, "Faltan datos obligatorios (cliente, DNI, modelo, cuotas)")

    cat = load_catalogo()
    tipo_norm = "PISCINA" if producto == "PISCINA" else "MODULO"
    precios = cat[tipo_norm.lower() + "s"].get("precios_lista", {})
    precio_lista = precios.get(modelo)
    if not precio_lista:
        raise HTTPException(404, f"Modelo '{modelo}' no encontrado en el catálogo")

    factor = 2.0
    valor_cuota = round(precio_lista / (cantidad_cuotas + factor))
    monto_inscripcion = round(valor_cuota * factor)

    ultimo_scoring = (
        db.query(ScoringBCRA)
        .filter(ScoringBCRA.cliente_dni == cliente_dni, ScoringBCRA.aliado_codigo == socio.codigo)
        .order_by(ScoringBCRA.id.desc()).first()
    )

    venta = VentaFinanciada(
        cliente_nombre=cliente_nombre,
        cliente_dni=cliente_dni,
        cliente_telefono=_normalizar_telefono(data.get("cliente_telefono") or ""),
        cliente_localidad=(data.get("cliente_localidad") or "").strip(),
        cliente_email=(data.get("cliente_email") or "").strip(),
        producto=tipo_norm,
        modelo_especifico=modelo,
        forma_pago="FINANCIADO",
        precio_total=precio_lista,
        monto_inscripcion=monto_inscripcion,
        cantidad_cuotas=cantidad_cuotas,
        valor_cuota=valor_cuota,
        estado_plan="PENDIENTE_INSCRIPCION",
        notas=f"Venta de socio comercial {socio.codigo}.",
        aliado_codigo=socio.codigo,
        scoring_situacion=ultimo_scoring.situacion if ultimo_scoring else None,
        declaracion_jurada_requerida=bool(ultimo_scoring and ultimo_scoring.requiere_declaracion_jurada),
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    notificar_rodrigo(
        db,
        f"🔵 *Nueva venta financiada*\n"
        f"Socio: {socio.codigo} ({socio.nombre}) · WhatsApp {socio.telefono or '—'}\n"
        f"Cliente: {cliente_nombre} (DNI {cliente_dni})\n"
        f"WhatsApp cliente: {venta.cliente_telefono or 'no cargado'}\n"
        f"Localidad: {venta.cliente_localidad or '—'}\n"
        f"Email: {venta.cliente_email or '—'}\n"
        f"Producto: {venta.producto} {venta.modelo_especifico} — {cantidad_cuotas} cuotas\n"
        f"Precio total: ${precio_lista:,.0f} · Inscripción: ${monto_inscripcion:,.0f} · Cuota: ${valor_cuota:,.0f}\n"
        f"{'⚠️ Situación BCRA ' + str(venta.scoring_situacion) + ' — requiere declaración jurada del cliente' if venta.declaracion_jurada_requerida else ''}\n"
        f"→ Falta que el cliente pague la inscripción y confirme el plan.\n"
        f"Venta ID: {venta.id}",
    )

    return {
        "ok": True, "venta_id": venta.id, "precio_lista": precio_lista,
        "cuotas": cantidad_cuotas, "valor_cuota": valor_cuota, "monto_inscripcion": monto_inscripcion,
        "declaracion_jurada_requerida": venta.declaracion_jurada_requerida,
        "mensaje": "Venta cargada. En cuanto el cliente pague la inscripción completa, descargá el contrato desde tu panel.",
    }


def _money(v):
    return f"{(v or 0):,.0f}".replace(",", ".")


async def _generar_contrato_pdf(venta: VentaFinanciada, socio_codigo: str, socio_nombre: str, db: Session) -> str:
    """Genera (o regenera) el PDF del resumen del plan + el link de confirmación. Devuelve el número de solicitud."""
    from utils.documentos import render_html, html_to_pdf

    if not venta.link_confirmacion_token:
        venta.link_confirmacion_token = secrets.token_urlsafe(24)
    venta.contrato_generado_en = datetime.now()
    if not venta.numero_solicitud:
        from routers.aliados import siguiente_numero_solicitud
        venta.numero_solicitud = siguiente_numero_solicitud(db)
    db.commit()

    html = render_html("resumen_plan_socio.html", {
        "numero_solicitud": venta.numero_solicitud,
        "fecha": datetime.now().strftime("%d/%m/%Y"),
        "cliente_nombre": venta.cliente_nombre,
        "cliente_dni": venta.cliente_dni,
        "cliente_telefono": venta.cliente_telefono,
        "cliente_localidad": venta.cliente_localidad,
        "producto": venta.producto,
        "modelo": venta.modelo_especifico,
        "precio_total": _money(venta.precio_total),
        "cantidad_cuotas": venta.cantidad_cuotas,
        "valor_cuota": _money(venta.valor_cuota),
        "monto_inscripcion": _money(venta.monto_inscripcion),
        "cuota_minima_licitacion": _cuota_minima_licitacion(venta.producto),
        "socio_codigo": socio_codigo,
        "socio_nombre": socio_nombre,
    })
    pdf_path = Path("data/contratos") / f"plan_{venta.numero_solicitud.replace('/', '-')}_{venta.id}.pdf"
    await html_to_pdf(html, pdf_path)
    return venta.numero_solicitud


async def _generar_recibo_pdf(venta: VentaFinanciada, db: Session) -> None:
    """Genera el PDF del recibo de inscripción completa."""
    from utils.documentos import render_html, html_to_pdf

    html = render_html("recibo_pago.html", {
        "numero_solicitud": venta.numero_solicitud or str(venta.id),
        "fecha": datetime.now().strftime("%d/%m/%Y"),
        "cliente_nombre": venta.cliente_nombre,
        "cliente_dni": venta.cliente_dni,
        "cliente_telefono": venta.cliente_telefono,
        "cliente_localidad": venta.cliente_localidad,
        "producto": venta.producto,
        "modelo": venta.modelo_especifico,
        "cantidad_cuotas": venta.cantidad_cuotas,
        "valor_cuota": _money(venta.valor_cuota),
        "monto_inscripcion": _money(venta.monto_inscripcion),
    })
    pdf_path = Path("data/contratos") / f"recibo_{(venta.numero_solicitud or str(venta.id)).replace('/', '-')}_{venta.id}.pdf"
    await html_to_pdf(html, pdf_path)


async def _registrar_pago_inscripcion(venta: VentaFinanciada, monto: float, db: Session) -> dict:
    """
    Núcleo compartido: acumula un pago hacia la inscripción (2 cuotas).
    - Primer pago recibido (la seña, cualquier monto a elección del cliente):
      genera el contrato automáticamente y abre un plazo de 30 días para
      completar el 100%.
    - Al alcanzar el 100% del monto_inscripcion: marca la inscripción como
      completa y emite el recibo de ese pago.
    """
    es_primer_pago = venta.primera_sena_en is None
    venta.monto_pagado_inscripcion = (venta.monto_pagado_inscripcion or 0) + monto

    resultado = {
        "monto_pagado_inscripcion": venta.monto_pagado_inscripcion,
        "monto_inscripcion": venta.monto_inscripcion,
        "contrato_generado": False,
        "inscripcion_completa": False,
    }

    if es_primer_pago:
        venta.primera_sena_en = datetime.now()
        venta.sena_vence_en = venta.primera_sena_en + timedelta(days=30)
        db.commit()
        socio_row = db.query(Aliado).filter(Aliado.codigo == venta.aliado_codigo).first()
        await _generar_contrato_pdf(venta, venta.aliado_codigo, socio_row.nombre if socio_row else "", db)
        resultado["contrato_generado"] = True
        _notificar_socio(
            db, venta.aliado_codigo,
            f"📄 Recibimos la seña de {venta.cliente_nombre} (${monto:,.0f}".replace(",", ".") + f"). Ya se generó el contrato — descargalo desde tu panel. Tiene 30 días para completar el 100% de la inscripción.",
        )

    if venta.monto_pagado_inscripcion >= (venta.monto_inscripcion or 0) and not venta.inscripcion_pagada_en:
        venta.inscripcion_pagada_en = datetime.now()
        venta.estado_plan = "ACTIVO"
        db.commit()
        await _generar_recibo_pdf(venta, db)
        venta.recibo_generado_en = datetime.now()
        db.commit()
        resultado["inscripcion_completa"] = True
        _notificar_socio(
            db, venta.aliado_codigo,
            f"✅ {venta.cliente_nombre} completó el 100% de la inscripción. Generamos el recibo y ya podés descargar el contrato (si no lo habías hecho) desde tu panel.",
        )
    elif not es_primer_pago:
        db.commit()
        falta = (venta.monto_inscripcion or 0) - venta.monto_pagado_inscripcion
        _notificar_socio(
            db, venta.aliado_codigo,
            f"💰 Registramos un pago de ${monto:,.0f}".replace(",", ".") + f" de {venta.cliente_nombre}. Lleva ${venta.monto_pagado_inscripcion:,.0f}".replace(",", ".") + f" de ${venta.monto_inscripcion:,.0f}".replace(",", ".") + f" — faltan ${falta:,.0f}".replace(",", "."),
        )

    return resultado


@router.post("/api/ventas-financiadas/{venta_id}/registrar-pago-inscripcion")
async def registrar_pago_inscripcion(
    venta_id: int, request: Request, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    El equipo registra un pago (parcial o total) hacia la inscripción del
    plan — requiere verificar el extracto bancario real, no puede quedar en
    manos del propio socio. El primer pago recibido genera el contrato
    automáticamente (es la seña); al completar el 100% se emite el recibo.
    """
    _require_gestion_interna(x_api_key, current_user)
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    data = await request.json()
    monto = float(data.get("monto") or 0)
    if monto <= 0:
        raise HTTPException(400, "El monto debe ser mayor a 0")
    resultado = await _registrar_pago_inscripcion(venta, monto, db)
    return {"ok": True, **resultado}


@router.post("/api/ventas-financiadas/{venta_id}/inscripcion-pagada")
async def marcar_inscripcion_pagada(
    venta_id: int, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Atajo: confirma de una sola vez el pago del 100% restante de la
    inscripción (equivalente a registrar-pago-inscripcion por el saldo que
    falte) — para cuando el cliente paga todo junto, sin seña previa.
    """
    _require_gestion_interna(x_api_key, current_user)
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    falta = (venta.monto_inscripcion or 0) - (venta.monto_pagado_inscripcion or 0)
    if falta <= 0:
        return {"ok": True, "ya_completa": True}
    resultado = await _registrar_pago_inscripcion(venta, falta, db)
    return {"ok": True, **resultado}


@router.get("/api/socio/ventas/{venta_id}/recibo-pdf")
async def descargar_recibo_pdf(venta_id: int, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id, VentaFinanciada.aliado_codigo == socio.codigo).first()
    if not venta or not venta.recibo_generado_en:
        raise HTTPException(404, "Recibo no disponible todavía")
    pdf_path = Path("data/contratos") / f"recibo_{(venta.numero_solicitud or str(venta.id)).replace('/', '-')}_{venta.id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "Recibo no encontrado")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=pdf_path.name)


@router.post("/api/socio/ventas/{venta_id}/generar-contrato")
async def generar_contrato_socio(venta_id: int, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Descarga manual del contrato — normalmente ya se generó solo al recibir
    la seña (primer pago hacia la inscripción). Este endpoint sirve como
    respaldo si por algún motivo todavía no se generó.
    """
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id, VentaFinanciada.aliado_codigo == socio.codigo).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    if not (venta.primera_sena_en or venta.inscripcion_pagada_en):
        raise HTTPException(409, "Todavía no se registró ningún pago hacia la inscripción")

    await _generar_contrato_pdf(venta, socio.codigo, socio.nombre, db)

    base_url = os.getenv("CRM_BASE_URL", "https://eco-crm-production.up.railway.app")
    link_confirmacion = f"{base_url}/socio/confirmar/{venta.link_confirmacion_token}"

    return {
        "ok": True,
        "numero_solicitud": venta.numero_solicitud,
        "link_confirmacion": link_confirmacion,
        "contrato_pdf_url": f"/api/socio/ventas/{venta.id}/contrato-pdf",
        "declaracion_jurada_requerida": venta.declaracion_jurada_requerida,
        "mensaje": "Descargá el resumen del plan y mandale el link al cliente para que confirme su adhesión.",
    }


@router.get("/api/socio/ventas/{venta_id}/contrato-pdf")
async def descargar_contrato_pdf(venta_id: int, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id, VentaFinanciada.aliado_codigo == socio.codigo).first()
    if not venta or not venta.numero_solicitud:
        raise HTTPException(404, "Venta no encontrada")
    pdf_path = Path("data/contratos") / f"plan_{venta.numero_solicitud.replace('/', '-')}_{venta.id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "Todavía no se generó el PDF — volvé a generar el contrato")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"Plan_{venta.numero_solicitud}.pdf")


# ─── Confirmación pública del cliente (sin login) ─────────────────────────────

@router.get("/socio/confirmar/{token}", response_class=HTMLResponse)
async def pagina_confirmacion_cliente(token: str, request: Request, db: Session = Depends(get_db)):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.link_confirmacion_token == token).first()
    if not venta:
        return HTMLResponse("<h1>Link inválido o vencido</h1>", status_code=404)
    return templates.TemplateResponse("confirmar_plan.html", {"request": request, "venta": venta, "token": token})


@router.post("/api/public/confirmar-plan/{token}")
async def confirmar_plan_cliente(token: str, db: Session = Depends(get_db)):
    """
    El cliente confirma: entendió que es un plan y que debe abonar hasta el
    50% del valor nominal para pedir entrega/instalación. Dispara el aviso
    al equipo para la llamada de bienvenida (auditoría).
    """
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.link_confirmacion_token == token).first()
    if not venta:
        raise HTTPException(404, "Link inválido")
    if venta.link_confirmacion_confirmada_en:
        return {"ok": True, "ya_confirmado": True}

    venta.link_confirmacion_confirmada_en = datetime.now()
    db.commit()

    notificar_rodrigo(
        db,
        f"🟢 *Cliente confirmó su plan — Socio {venta.aliado_codigo}*\n"
        f"Cliente: {venta.cliente_nombre} (DNI {venta.cliente_dni})\n"
        f"WhatsApp cliente: {venta.cliente_telefono or 'no cargado'}\n"
        f"Localidad: {venta.cliente_localidad or '—'}\n"
        f"Producto: {venta.producto} {venta.modelo_especifico} — {venta.cantidad_cuotas} cuotas\n"
        f"Solicitud N° {venta.numero_solicitud}\n"
        f"{'⚠️ Requiere declaración jurada (situación BCRA ' + str(venta.scoring_situacion) + ')' if venta.declaracion_jurada_requerida else ''}\n"
        f"→ Falta la llamada de bienvenida (auditoría) para liberar la comisión.\n"
        f"Venta ID: {venta.id}",
    )
    _notificar_socio(db, venta.aliado_codigo, f"🎉 {venta.cliente_nombre} confirmó su plan. En breve nuestro equipo lo llama para la bienvenida y ahí se libera tu comisión.")
    return {"ok": True}


@router.post("/api/ventas-financiadas/{venta_id}/auditoria-completada")
async def completar_auditoria_bienvenida(
    venta_id: int, db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    El equipo confirma que hizo la llamada de bienvenida: el cliente entendió
    el plan y la condición del 50%. Libera la comisión (% configurable desde
    el panel de admin, ver ComisionConfig; hoy es el 100% de una cuota).
    Si la venta requiere declaración jurada, exige que ya esté confirmada.
    """
    _require_gestion_interna(x_api_key, current_user)
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    if venta.declaracion_jurada_requerida and not venta.declaracion_jurada_confirmada_en:
        raise HTTPException(409, "Falta la declaración jurada del cliente antes de cerrar la auditoría")

    venta.auditoria_bienvenida_en = datetime.now()
    db.commit()

    comision = None
    if venta.aliado_codigo:
        pct = obtener_porcentaje_comision(db, "financiado", venta.producto, venta.modelo_especifico)
        comision = Comision(
            aliado_codigo=venta.aliado_codigo,
            solicitud_numero=venta.numero_solicitud or "",
            tipo="entrada",
            monto=round((venta.valor_cuota or 0) * pct, 2),
            estado="pendiente",
            venta_financiada_id=venta.id,
        )
        db.add(comision)
        db.commit()
        _notificar_socio(db, venta.aliado_codigo, f"✅ Hicimos la bienvenida a {venta.cliente_nombre}. Se liberó tu comisión de ${comision.monto:,.0f}".replace(",", ".") + " — la vas a ver como pendiente en tu panel hasta que te la transfiramos.")

    return {"ok": True, "comision_generada": comision.monto if comision else None}


# ─── Declaración jurada (situación 5 o 6) ─────────────────────────────────────

DECLARACION_JURADA_TEXTO = (
    "Declaro bajo juramento que conozco mi situación crediticia actual ante el Banco Central de la "
    "República Argentina (BCRA) y que, no obstante ello, deseo avanzar con la operación de financiación "
    "descripta en la presente solicitud. Asumo la responsabilidad íntegra por el cumplimiento de las "
    "obligaciones de pago asumidas, y reconozco que esta declaración forma parte integrante del contrato "
    "de financiación suscripto con EcoFiver (Cooperativa de Trabajo Eco Zárate Limitada)."
)


@router.get("/socio/declaracion-jurada/{token}", response_class=HTMLResponse)
async def pagina_declaracion_jurada(token: str, request: Request, db: Session = Depends(get_db)):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.link_confirmacion_token == token).first()
    if not venta or not venta.declaracion_jurada_requerida:
        return HTMLResponse("<h1>Link inválido</h1>", status_code=404)
    return templates.TemplateResponse("declaracion_jurada.html", {
        "request": request, "venta": venta, "token": token, "texto": DECLARACION_JURADA_TEXTO,
    })


@router.post("/api/public/confirmar-declaracion-jurada/{token}")
async def confirmar_declaracion_jurada(token: str, db: Session = Depends(get_db)):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.link_confirmacion_token == token).first()
    if not venta:
        raise HTTPException(404, "Link inválido")
    venta.declaracion_jurada_confirmada_en = datetime.now()
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# LICITACIÓN — entrega anticipada por integración de capital
# ═══════════════════════════════════════════════════════════════════════════════
# Vivienda modular: se puede licitar desde la cuota 6. Piscina: desde la cuota 3.
# El cliente sigue abonando mes a mes hasta terminar el plan — licitar adelanta
# la entrega, no cancela el resto de las cuotas.
CUOTA_MINIMA_LICITACION = {"MODULO": 6, "PISCINA": 3}


def _cuota_minima_licitacion(producto: str) -> int:
    return CUOTA_MINIMA_LICITACION.get((producto or "").upper(), 6)


@router.post("/api/socio/ventas/{venta_id}/solicitar-licitacion")
async def solicitar_licitacion(venta_id: int, socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """El cliente pidió, vía integración de capital, adelantar la entrega de su vivienda/piscina."""
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id, VentaFinanciada.aliado_codigo == socio.codigo).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    umbral = _cuota_minima_licitacion(venta.producto)
    if (venta.cuotas_pagas or 0) < umbral:
        raise HTTPException(409, f"Recién se puede licitar desde la cuota {umbral} — este plan lleva {venta.cuotas_pagas or 0} pagas")
    if venta.licitacion_solicitada_en:
        return {"ok": True, "ya_solicitada": True}

    venta.licitacion_solicitada_en = datetime.now()
    db.commit()
    notificar_rodrigo(
        db,
        f"🏗️ *Pedido de licitación — Socio {socio.codigo}*\n"
        f"Cliente: {venta.cliente_nombre} (DNI {venta.cliente_dni})\n"
        f"WhatsApp cliente: {venta.cliente_telefono or 'no cargado'}\n"
        f"Localidad: {venta.cliente_localidad or '—'}\n"
        f"Producto: {venta.producto} {venta.modelo_especifico} — cuota {venta.cuotas_pagas}/{venta.cantidad_cuotas}\n"
        f"Solicita integración de capital para adelantar la entrega.\n"
        f"Venta ID: {venta.id}",
    )
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# COLAS INTERNAS — los 3 puntos humanos, con lista para operar desde el panel
# (antes solo existían como endpoints de acción, sin ninguna pantalla para verlos)
# ═══════════════════════════════════════════════════════════════════════════════

def _venta_fin_dict(v: VentaFinanciada) -> dict:
    return {
        "id": v.id, "aliado_codigo": v.aliado_codigo, "cliente_nombre": v.cliente_nombre,
        "cliente_dni": v.cliente_dni, "cliente_telefono": v.cliente_telefono,
        "cliente_localidad": v.cliente_localidad, "cliente_email": v.cliente_email,
        "producto": v.producto, "modelo_especifico": v.modelo_especifico,
        "cantidad_cuotas": v.cantidad_cuotas, "valor_cuota": v.valor_cuota,
        "precio_total": v.precio_total, "monto_inscripcion": v.monto_inscripcion,
        "monto_pagado_inscripcion": v.monto_pagado_inscripcion or 0,
        "primera_sena_en": v.primera_sena_en.isoformat() if v.primera_sena_en else None,
        "sena_vence_en": v.sena_vence_en.isoformat() if v.sena_vence_en else None,
        "numero_solicitud": v.numero_solicitud,
        "declaracion_jurada_requerida": v.declaracion_jurada_requerida,
        "declaracion_jurada_confirmada": bool(v.declaracion_jurada_confirmada_en),
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _venta_cont_dict(v: VentaContado) -> dict:
    return {
        "id": v.id, "aliado_codigo": v.aliado_codigo, "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono, "cliente_localidad": v.cliente_localidad,
        "producto": v.producto, "modelo_especifico": v.modelo_especifico,
        "precio_final": v.precio_final, "notas": v.notas or "",
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.get("/api/ventas-financiadas/pendientes-inscripcion")
async def pendientes_inscripcion(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Ventas financiadas cargadas por un socio, esperando que se confirme el pago de la seña."""
    _require_gestion_interna(x_api_key, current_user)
    ventas = (db.query(VentaFinanciada)
              .filter(VentaFinanciada.aliado_codigo.isnot(None), VentaFinanciada.inscripcion_pagada_en.is_(None))
              .order_by(VentaFinanciada.created_at.asc()).all())
    return {"total": len(ventas), "ventas": [_venta_fin_dict(v) for v in ventas]}


@router.get("/api/ventas-financiadas/pendientes-auditoria")
async def pendientes_auditoria(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Clientes que ya confirmaron su plan por el link — falta la llamada de bienvenida."""
    _require_gestion_interna(x_api_key, current_user)
    ventas = (db.query(VentaFinanciada)
              .filter(VentaFinanciada.link_confirmacion_confirmada_en.isnot(None), VentaFinanciada.auditoria_bienvenida_en.is_(None))
              .order_by(VentaFinanciada.link_confirmacion_confirmada_en.asc()).all())
    return {"total": len(ventas), "ventas": [_venta_fin_dict(v) for v in ventas]}


@router.get("/api/ventas-contado/pendientes-confirmacion")
async def pendientes_confirmacion_48hs(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Ventas de contado cargadas por un socio, esperando el contacto de las 48hs."""
    _require_gestion_interna(x_api_key, current_user)
    ventas = (db.query(VentaContado)
              .filter(VentaContado.aliado_codigo.isnot(None), VentaContado.confirmacion_48hs_en.is_(None))
              .order_by(VentaContado.created_at.asc()).all())
    return {"total": len(ventas), "ventas": [_venta_cont_dict(v) for v in ventas]}


@router.get("/api/ventas-contado/pendientes-entrega")
async def pendientes_entrega_cobro(
    db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Ventas de contado ya confirmadas, esperando registrar entrega + cobro."""
    _require_gestion_interna(x_api_key, current_user)
    ventas = (db.query(VentaContado)
              .filter(VentaContado.aliado_codigo.isnot(None), VentaContado.confirmacion_48hs_en.isnot(None), VentaContado.cobro_estado != "COBRADO")
              .order_by(VentaContado.confirmacion_48hs_en.asc()).all())
    return {"total": len(ventas), "ventas": [_venta_cont_dict(v) for v in ventas]}


# ═══════════════════════════════════════════════════════════════════════════════
# MIS VENTAS Y MIS COMISIONES (autoservicio)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/socio/ventas")
async def mis_ventas(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    contado = db.query(VentaContado).filter(VentaContado.aliado_codigo == socio.codigo).order_by(VentaContado.created_at.desc()).all()
    financiado = db.query(VentaFinanciada).filter(VentaFinanciada.aliado_codigo == socio.codigo).order_by(VentaFinanciada.created_at.desc()).all()
    return {
        "contado": [{
            "id": v.id, "cliente_nombre": v.cliente_nombre, "producto": v.producto,
            "modelo_especifico": v.modelo_especifico, "precio_final": v.precio_final,
            "cobro_estado": v.cobro_estado,
            "confirmacion_48hs": bool(v.confirmacion_48hs_en),
            "created_at": v.created_at.isoformat() if v.created_at else None,
        } for v in contado],
        "financiado": [{
            "id": v.id, "cliente_nombre": v.cliente_nombre, "producto": v.producto,
            "modelo_especifico": v.modelo_especifico, "cantidad_cuotas": v.cantidad_cuotas,
            "valor_cuota": v.valor_cuota, "estado_plan": v.estado_plan,
            "cuotas_pagas": v.cuotas_pagas or 0,
            "cuota_minima_licitacion": _cuota_minima_licitacion(v.producto),
            "puede_licitar": (v.cuotas_pagas or 0) >= _cuota_minima_licitacion(v.producto),
            "licitacion_solicitada": bool(v.licitacion_solicitada_en),
            "monto_inscripcion": v.monto_inscripcion,
            "monto_pagado_inscripcion": v.monto_pagado_inscripcion or 0,
            "sena_recibida": bool(v.primera_sena_en),
            "sena_vence_en": v.sena_vence_en.isoformat() if v.sena_vence_en else None,
            "inscripcion_pagada": bool(v.inscripcion_pagada_en),
            "recibo_generado": bool(v.recibo_generado_en),
            "contrato_generado": bool(v.contrato_generado_en),
            "link_confirmacion_token": v.link_confirmacion_token,
            "cliente_confirmo": bool(v.link_confirmacion_confirmada_en),
            "declaracion_jurada_requerida": v.declaracion_jurada_requerida,
            "declaracion_jurada_confirmada": bool(v.declaracion_jurada_confirmada_en),
            "auditoria_completada": bool(v.auditoria_bienvenida_en),
            "numero_solicitud": v.numero_solicitud,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        } for v in financiado],
    }


def _tabla_comisiones_vigentes(db: Session) -> list:
    """Tabla resuelta (con overrides aplicados) para PISCINA y MODULO — lo que
    ve el socio en el modal de aceptación y en 'Mis comisiones'."""
    filas = []
    for producto, label in (("PISCINA", "Piscinas"), ("MODULO", "Módulos")):
        pct_contado = obtener_porcentaje_comision(db, "contado", producto)
        pct_financiado = obtener_porcentaje_comision(db, "financiado", producto)
        filas.append({
            "producto": producto, "producto_label": label,
            "contado_pct": round(pct_contado * 100, 2),
            "contado_texto": f"{round(pct_contado * 100, 2):g}% del precio de venta, contra entrega y cobro.",
            "financiado_pct": round(pct_financiado * 100, 2),
            "financiado_texto": f"{round(pct_financiado * 100, 2):g}% del valor de la primera cuota, al confirmar la llamada de bienvenida.",
        })
    return filas


@router.get("/api/socio/comisiones/vigentes")
async def comisiones_vigentes(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """Porcentajes de comisión vigentes por producto — para el modal de
    aceptación del primer ingreso y para consulta permanente en el panel."""
    return {"tabla": _tabla_comisiones_vigentes(db), "aceptadas": bool(socio.comisiones_aceptadas_en)}


@router.post("/api/socio/comisiones/aceptar")
async def aceptar_comisiones(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """Marca que el socio vio y aceptó las condiciones de comisión vigentes —
    obligatorio antes de poder operar el panel."""
    if not socio.comisiones_aceptadas_en:
        socio.comisiones_aceptadas_en = datetime.now()
        db.commit()
    return {"ok": True}


@router.get("/api/admin/comisiones/config")
async def admin_listar_comisiones_config(
    x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista toda la configuración de comisiones (defaults + excepciones por
    producto/modelo) para el panel de admin."""
    _require_gestion_interna(x_api_key, current_user)
    filas = db.query(ComisionConfig).order_by(
        ComisionConfig.tipo_venta, ComisionConfig.producto.is_(None).desc(), ComisionConfig.modelo.is_(None).desc()
    ).all()
    return {"config": [{
        "id": c.id, "tipo_venta": c.tipo_venta, "producto": c.producto, "modelo": c.modelo,
        "porcentaje": c.porcentaje, "porcentaje_pct": round(c.porcentaje * 100, 2),
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    } for c in filas], "vigentes": _tabla_comisiones_vigentes(db)}


@router.put("/api/admin/comisiones/config")
async def admin_actualizar_comision_config(
    request: Request, x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Crea o actualiza una fila de configuración de comisión. Body:
    {tipo_venta: 'contado'|'financiado', producto?: 'PISCINA'|'MODULO'|...,
     modelo?: str, porcentaje_pct: number (ej. 5 para 5%)}.
    producto=null aplica como default general de ese tipo_venta; modelo=null
    aplica a todo el producto.
    """
    _require_gestion_interna(x_api_key, current_user)
    data = await request.json()
    tipo_venta = (data.get("tipo_venta") or "").strip().lower()
    if tipo_venta not in ("contado", "financiado"):
        raise HTTPException(400, "tipo_venta debe ser 'contado' o 'financiado'")
    producto = (data.get("producto") or "").strip().upper() or None
    modelo = (data.get("modelo") or "").strip() or None
    if modelo and not producto:
        raise HTTPException(400, "Un modelo específico requiere indicar el producto")
    try:
        porcentaje = float(data.get("porcentaje_pct")) / 100.0
    except (TypeError, ValueError):
        raise HTTPException(400, "porcentaje_pct inválido")
    if not (0 <= porcentaje <= 2):
        raise HTTPException(400, "El porcentaje debe estar entre 0% y 200%")

    row = db.query(ComisionConfig).filter(
        ComisionConfig.tipo_venta == tipo_venta,
        ComisionConfig.producto == producto,
        ComisionConfig.modelo == modelo,
    ).first()
    if row:
        row.porcentaje = porcentaje
    else:
        row = ComisionConfig(tipo_venta=tipo_venta, producto=producto, modelo=modelo, porcentaje=porcentaje)
        db.add(row)
    db.commit()
    return {"ok": True, "id": row.id, "porcentaje_pct": round(porcentaje * 100, 2)}


@router.delete("/api/admin/comisiones/config/{config_id}")
async def admin_borrar_comision_config(
    config_id: int, x_api_key: Optional[str] = Header(None), current_user: Optional[Usuario] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Borra una excepción (nunca el default global: producto y modelo NULL)."""
    _require_gestion_interna(x_api_key, current_user)
    row = db.query(ComisionConfig).filter(ComisionConfig.id == config_id).first()
    if not row:
        raise HTTPException(404, "No encontrado")
    if row.producto is None and row.modelo is None:
        raise HTTPException(409, "No se puede borrar el default general — editalo en su lugar")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/api/socio/comisiones")
async def mis_comisiones(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    comisiones = db.query(Comision).filter(Comision.aliado_codigo == socio.codigo).order_by(Comision.id.desc()).all()
    return {
        "monto_pendiente": round(sum(c.monto or 0 for c in comisiones if c.estado == "pendiente"), 2),
        "monto_liquidado": round(sum(c.monto or 0 for c in comisiones if c.estado == "liquidada"), 2),
        "comisiones": [{
            "id": c.id, "tipo": c.tipo, "monto": c.monto, "estado": c.estado,
            "solicitud_numero": c.solicitud_numero or "",
            "factura_cargada": bool(c.factura_path),
            "fecha_liquidacion": c.fecha_liquidacion.isoformat() if c.fecha_liquidacion else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        } for c in comisiones],
    }


@router.get("/api/socio/comisiones/exportar")
async def exportar_comisiones(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """Exporta las comisiones propias en CSV, para la contabilidad del socio."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    comisiones = db.query(Comision).filter(Comision.aliado_codigo == socio.codigo).order_by(Comision.id.desc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Solicitud", "Tipo", "Monto", "Estado", "Fecha liquidación", "Fecha carga"])
    for c in comisiones:
        writer.writerow([
            c.solicitud_numero or "", c.tipo, c.monto or 0, c.estado,
            c.fecha_liquidacion.strftime("%d/%m/%Y") if c.fecha_liquidacion else "",
            c.created_at.strftime("%d/%m/%Y") if c.created_at else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=comisiones_{socio.codigo}.csv"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CHECKLIST DE PROGRESO — motivación para completar el onboarding
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/socio/progreso")
async def mi_progreso(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    tiene_venta = db.query(VentaFinanciada).filter(VentaFinanciada.aliado_codigo == socio.codigo).first() is not None \
        or db.query(VentaContado).filter(VentaContado.aliado_codigo == socio.codigo).first() is not None
    tiene_comision_liberada = db.query(Comision).filter(Comision.aliado_codigo == socio.codigo).first() is not None
    pasos = [
        {"paso": "Registrado", "hecho": True},
        {"paso": "WhatsApp verificado", "hecho": socio.whatsapp_verificado},
        {"paso": "Datos de cobro cargados (CBU/alias)", "hecho": bool(socio.cbu_alias)},
        {"paso": "Documentación cargada (Monotributo o DNI)", "hecho": bool(socio.doc_monotributo_path or socio.doc_dni_path)},
        {"paso": "Primera venta cargada", "hecho": tiene_venta},
        {"paso": "Primera comisión generada", "hecho": tiene_comision_liberada},
    ]
    completados = sum(1 for p in pasos if p["hecho"])
    return {"pasos": pasos, "completados": completados, "total": len(pasos)}


# ═══════════════════════════════════════════════════════════════════════════════
# CENTRO DE AYUDA — preguntas frecuentes
# ═══════════════════════════════════════════════════════════════════════════════

FAQ_SOCIOS = [
    {"pregunta": "¿Cómo empiezo a vender?", "respuesta": "Mirá el catálogo y el simulador de cuotas en tu panel para conocer precios y planes. Después, andá a la guía \"Cómo empezar a vender\" en la Biblioteca de contenidos."},
    {"pregunta": "¿Necesito aprobación para arrancar?", "respuesta": "No. Apenas te registrás y verificás tu WhatsApp, tu cuenta queda activa. No hay ningún paso de aprobación."},
    {"pregunta": "¿Cómo cargo una venta?", "respuesta": "Desde la sección \"Cargar venta\" de tu panel, elegís contado o financiado y completás los datos del cliente."},
    {"pregunta": "¿Cuándo cobro mi comisión?", "respuesta": "Financiado: cuando el equipo hace la llamada de bienvenida al cliente. Contado: cuando se entrega y se cobra el producto. En ambos casos vas a ver la comisión como \"pendiente\" hasta que te la transfiramos."},
    {"pregunta": "¿Puedo vender en cualquier parte del país?", "respuesta": "Sí, el programa opera en todo el territorio nacional. Fuera del área de cobertura de instalación directa, el producto se entrega en formato casco y la instalación queda a cargo tuyo o de un instalador de tu zona — ideal si trabajás junto a instaladores."},
    {"pregunta": "¿Qué pasa si mi cliente tiene mala situación crediticia?", "respuesta": "Si el Scoring da situación 5 o 6, no se bloquea la venta — se le pide al cliente una declaración jurada adicional antes de la auditoría."},
    {"pregunta": "¿Qué es la licitación?", "respuesta": "Desde la cuota 6 (vivienda) o la cuota 3 (piscina), tu cliente puede pedir adelantar la entrega mediante una integración de capital. Ese aporte se descuenta del saldo total, y el cliente sigue abonando el saldo restante mes a mes hasta completarlo."},
    {"pregunta": "¿Necesito Monotributo?", "respuesta": "Eventualmente sí, para poder facturar tus comisiones. Podés cargar la constancia después desde tu perfil."},
    {"pregunta": "¿Con quién hablo si tengo una duda?", "respuesta": "Comunicate al WhatsApp del programa de Socios Comerciales — el equipo te responde consultas de precio, estado de tus ventas y comisiones."},
    {"pregunta": "¿Cuáles son los 3 precios de contado de una piscina y cuándo uso cada uno?", "respuesta": "\"Con instalación\" es el precio estándar dentro del área de cobertura directa — usalo siempre que puedas. \"Casco + equipo, sin instalación\" y \"casco solo, sin instalación ni equipo\" son para clientes fuera de esa zona: el producto se entrega igual a cualquier parte del país, pero la instalación la coordinás vos, tu equipo, o un instalador de la zona del cliente."},
    {"pregunta": "¿Qué es la inscripción de una venta financiada?", "respuesta": "El equivalente a 2 cuotas del plan elegido. El cliente puede pagarla completa de una vez, o en partes: la primera parte (la seña, el monto que el cliente elija) genera el contrato automáticamente, y tiene 30 días para completar el 100% — recién ahí se emite el recibo y el plan queda activo."},
    {"pregunta": "¿Qué pasa si el cliente no completa la inscripción dentro de los 30 días?", "respuesta": "El plazo queda registrado en tu panel para que hagas el seguimiento con el cliente. Escribinos si necesitás una excepción puntual."},
    {"pregunta": "¿Cómo le explico el plan de pagos a un cliente nuevo?", "respuesta": "Mostrale el catálogo con el precio de lista y usá el Simulador de cuotas para calcular la cuota exacta según el plazo que elija. El plan queda formalizado con el contrato, que se genera automáticamente en cuanto el cliente hace su primer pago hacia la inscripción."},
    {"pregunta": "¿Puedo cargar una venta de cualquier categoría del catálogo?", "respuesta": "De contado, sí — piscinas, módulos, combos, hidromasajes, bañeras, receptáculos, accesorios, baños químicos, garitas, cuchas, reposeras y depósitos de jardín. Financiado está disponible solo para piscinas y módulos, que es donde ofrecemos financiación propia."},
    {"pregunta": "¿Cómo sé si mi perfil está \"Verificado\"?", "respuesta": "Vas a ver un tilde ✓ junto a tu nombre en el panel y en el ranking. Se activa automáticamente cuando completás tu DNI y zona, y verificás tu WhatsApp — recién ahí podés cargar ventas y empezar a generar comisiones."},
    {"pregunta": "¿La foto que subo del catálogo o de una entrega la puede usar cualquier socio?", "respuesta": "Sí. Todo el material de la Biblioteca (fotos del catálogo, contenido de marketing, fotos de entregas reales, copys y guías) está disponible para todos los socios verificados, listo para usar en tus publicaciones."},
]


@router.get("/api/socio/faq")
async def socio_faq(socio: Aliado = Depends(require_socio)):
    return {"faq": FAQ_SOCIOS}


@router.get("/api/socio/capacitacion")
async def socio_capacitacion(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    """
    Guías propias de EcoFiver — a propósito separadas de la Biblioteca de
    marketing (esa es para contenido reusable en publicaciones; esto es
    para aprender a operar). No exige estar verificado: es justamente lo
    que ayuda a un socio nuevo a llegar a estarlo.
    """
    guias = (
        db.query(MaterialSocio)
        .filter(MaterialSocio.tipo == "guia", MaterialSocio.activo == True)
        .order_by(MaterialSocio.orden, MaterialSocio.id)
        .all()
    )
    return {"guias": [_material_dict(g) for g in guias]}


# ═══════════════════════════════════════════════════════════════════════════════
# RANKING — solo ventas con plata real ya movida
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/socio/ranking")
async def ranking_socios(
    periodo: str = "mes", db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    socio: Optional[Aliado] = Depends(get_current_socio),
):
    """
    Ranking nacional: nombre + inicial de apellido, zona, monto facturado.
    Accesible con sesión de socio (panel) O con la API key (Franco, para el
    resumen de los viernes) — nunca sin ninguna de las dos.
    Cuenta financiado con inscripción ya pagada, y contado ya cobrado —
    no hace falta esperar la auditoría/48hs para aparecer en el ranking.
    """
    if not socio and not (x_api_key and x_api_key == API_KEY):
        raise HTTPException(401, "No autenticado")

    dias = {"semana": 7, "mes": 30, "trimestre": 90, "año": 365}.get(periodo, 30)
    desde = datetime.now() - timedelta(days=dias)

    filas = {}
    for a in db.query(Aliado).filter(Aliado.estado == "activo").all():
        partes = a.nombre.strip().split()
        nombre_mostrado = partes[0] if len(partes) == 1 else f"{partes[0]} {partes[-1][0]}."
        filas[a.codigo] = {
            "codigo": a.codigo, "nombre": nombre_mostrado, "zona": a.zona or "",
            "monto_facturado": 0.0, "verificado": _esta_verificado(a),
        }

    for v in db.query(VentaFinanciada).filter(VentaFinanciada.aliado_codigo.isnot(None), VentaFinanciada.inscripcion_pagada_en.isnot(None), VentaFinanciada.inscripcion_pagada_en >= desde).all():
        if v.aliado_codigo in filas:
            filas[v.aliado_codigo]["monto_facturado"] += (v.precio_total or 0)

    for v in db.query(VentaContado).filter(VentaContado.aliado_codigo.isnot(None), VentaContado.cobro_estado == "COBRADO", VentaContado.cobro_fecha.isnot(None), VentaContado.cobro_fecha >= desde).all():
        if v.aliado_codigo in filas:
            filas[v.aliado_codigo]["monto_facturado"] += (v.precio_final or 0)

    ranking = sorted(filas.values(), key=lambda x: x["monto_facturado"], reverse=True)
    medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, f in enumerate(ranking, 1):
        f["puesto"] = i
        f["monto_facturado"] = round(f["monto_facturado"], 2)
        f["medalla"] = medallas.get(i)
    return {"periodo": periodo, "ranking": ranking}


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA DEL PANEL
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/panel-socio", response_class=HTMLResponse)
async def panel_socio_page(request: Request):
    return templates.TemplateResponse("panel_socio.html", {"request": request})


@router.get("/terminos-socios-comerciales", response_class=HTMLResponse)
async def terminos_socios_page(request: Request):
    return templates.TemplateResponse("terminos_socios.html", {"request": request})
