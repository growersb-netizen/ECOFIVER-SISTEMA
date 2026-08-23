"""
Endpoints de autenticación: registro, login, refresh, me.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.workspace import Workspace, Membership, Subscription, MemberRole

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    workspace_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Registra usuario + crea su workspace inicial con plan Starter.
    """
    # Verificar email único
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # Crear usuario
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()

    # Crear workspace
    slug = payload.workspace_name.lower().replace(" ", "-")[:50]
    workspace = Workspace(name=payload.workspace_name, slug=f"{slug}-{user.id}")
    db.add(workspace)
    await db.flush()

    # Membresía como owner
    membership = Membership(workspace_id=workspace.id, user_id=user.id, role=MemberRole.owner)
    db.add(membership)

    # Suscripción Starter por defecto
    subscription = Subscription(
        workspace_id=workspace.id,
        plan_name="starter",
    )
    db.add(subscription)
    await db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
    }
