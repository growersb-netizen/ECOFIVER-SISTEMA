import json
import re
import os
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Usuario

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SECRET_KEY = os.getenv("SECRET_KEY", "eco-crm-secret-key-dev-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_roles(user: Usuario) -> List[str]:
    try:
        return json.loads(user.roles_json or "[]")
    except Exception:
        return []


def get_current_user_from_token(token: str, db: Session) -> Optional[Usuario]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub"))
        user = db.query(Usuario).filter(Usuario.id == user_id, Usuario.activo == True).first()
        return user
    except Exception:
        return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[Usuario]:
    # Try bearer token first
    if token:
        user = get_current_user_from_token(token, db)
        if user:
            return user
    # Try cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        user = get_current_user_from_token(cookie_token, db)
        if user:
            return user
    return None


def require_auth(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> Usuario:
    user = get_current_user(request, db, token)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def require_roles(*roles):
    def checker(user: Usuario = Depends(require_auth)) -> Usuario:
        user_roles = get_user_roles(user)
        if "ADMIN" in user_roles:
            return user
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=403, detail="Sin permisos")
        return user
    return checker


# ─── LOGIN PAGE ───────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).filter(Usuario.email == email, Usuario.activo == True).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Email o contraseña incorrectos"
        })
    token = create_access_token({"sub": str(user.id)})
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=86400)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


# ─── API TOKEN ────────────────────────────────────────────────────────────────

@router.post("/api/auth/token")
async def api_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).filter(Usuario.email == form_data.username, Usuario.activo == True).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


ROLES_DISPONIBLES = [
    ("ADMIN",                 "Admin total"),
    ("COORDINADOR_OPERATIVO", "Coordinador Operativo"),
    ("ASESOR_APERTURA",       "Asesor de Ventas"),
    ("SUPERVISOR_CIERRE",     "Supervisor / Cierre"),
    ("COBRANZAS",             "Cobranzas"),
    ("FABRICA",               "Fábrica"),
    ("ADMINISTRACION",        "Administración"),
]


def _require_gestion(user: Usuario = Depends(require_auth)) -> Usuario:
    roles = get_user_roles(user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin permisos para gestión de usuarios")
    return user


# ─── USER MANAGEMENT API ─────────────────────────────────────────────────────

@router.get("/api/usuarios")
async def list_usuarios(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_gestion),
):
    users = db.query(Usuario).order_by(Usuario.id).all()
    return [{
        "id": u.id,
        "nombre": u.nombre,
        "email": u.email,
        "roles": get_user_roles(u),
        "activo": u.activo,
        "es_agente_ia": getattr(u, "es_agente_ia", False),
        "agente_key": getattr(u, "agente_key", None),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    } for u in users]


@router.get("/api/usuarios/me")
async def me(current_user: Usuario = Depends(require_auth)):
    return {
        "id": current_user.id,
        "nombre": current_user.nombre,
        "email": current_user.email,
        "roles": get_user_roles(current_user),
    }


@router.post("/api/usuarios")
async def create_usuario(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_gestion),
):
    data = await request.json()
    caller_roles = get_user_roles(current_user)
    es_admin = "ADMIN" in caller_roles
    roles = data.get("roles", [])

    if "ADMIN" in roles and not es_admin:
        raise HTTPException(403, "Solo un ADMIN puede asignar el rol ADMIN")
    if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", data.get("email", "")):
        raise HTTPException(400, "Email inválido")
    if db.query(Usuario).filter(Usuario.email == data["email"].lower().strip()).first():
        raise HTTPException(400, "Email ya existe")
    if len(data.get("password", "")) < 6:
        raise HTTPException(400, "Contraseña mínimo 6 caracteres")

    user = Usuario(
        nombre=data["nombre"].strip(),
        email=data["email"].lower().strip(),
        password_hash=hash_password(data["password"]),
        roles_json=json.dumps(roles),
        activo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"ok": True, "id": user.id}


@router.put("/api/usuarios/{user_id}")
async def update_usuario(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_gestion),
):
    target = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not target:
        raise HTTPException(404, "Usuario no encontrado")

    caller_roles = get_user_roles(current_user)
    es_admin = "ADMIN" in caller_roles
    target_roles = get_user_roles(target)

    if "ADMIN" in target_roles and not es_admin:
        raise HTTPException(403, "No podés editar a un usuario ADMIN")

    data = await request.json()

    if "nombre" in data:
        target.nombre = data["nombre"].strip()
    if "email" in data:
        email = data["email"].lower().strip()
        dup = db.query(Usuario).filter(Usuario.email == email, Usuario.id != user_id).first()
        if dup:
            raise HTTPException(400, "Email ya en uso")
        target.email = email
    if "password" in data and data["password"]:
        if len(data["password"]) < 6:
            raise HTTPException(400, "Contraseña mínimo 6 caracteres")
        target.password_hash = hash_password(data["password"])
    if "roles" in data:
        if "ADMIN" in data["roles"] and not es_admin:
            raise HTTPException(403, "Solo ADMIN puede asignar rol ADMIN")
        target.roles_json = json.dumps(data["roles"])
    if "activo" in data:
        target.activo = data["activo"]
    if "es_agente_ia" in data and es_admin:
        target.es_agente_ia = bool(data["es_agente_ia"])
        # Si se activa como agente IA, generar api key automáticamente si no tiene
        if target.es_agente_ia and not target.agente_key:
            import secrets
            target.agente_key = f"agt_{secrets.token_urlsafe(24)}"
    if "agente_key" in data and es_admin:
        target.agente_key = data["agente_key"] or None

    db.commit()
    return {
        "ok": True,
        "agente_key": target.agente_key if target.es_agente_ia else None,
    }


@router.put("/api/usuarios/me/password")
async def change_my_password(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    if not verify_password(data.get("password_actual", ""), current_user.password_hash):
        raise HTTPException(400, "Contraseña actual incorrecta")
    nueva = data.get("password_nueva", "")
    if len(nueva) < 6:
        raise HTTPException(400, "La nueva contraseña debe tener al menos 6 caracteres")
    current_user.password_hash = hash_password(nueva)
    db.commit()
    return {"ok": True}


@router.delete("/api/usuarios/{user_id}")
async def delete_usuario(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    caller_roles = get_user_roles(current_user)
    if "ADMIN" not in caller_roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar usuarios")
    if user_id == current_user.id:
        raise HTTPException(400, "No podés eliminarte a vos mismo")
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    db.delete(user)
    db.commit()
    return {"ok": True}


# ─── PÁGINAS ──────────────────────────────────────────────────────────────────

@router.get("/perfil", response_class=HTMLResponse)
async def perfil_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("perfil.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


@router.get("/usuarios-admin", response_class=HTMLResponse)
async def usuarios_admin_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_gestion),
):
    roles = get_user_roles(current_user)
    es_admin = "ADMIN" in roles
    return templates.TemplateResponse("usuarios_admin.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "roles_disponibles": ROLES_DISPONIBLES,
        "es_admin": es_admin,
    })
