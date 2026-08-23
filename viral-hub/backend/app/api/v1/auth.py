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
from app.models.channel import ChannelGroup

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    workspace_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "is_superadmin": user.is_superadmin,
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Registra usuario + crea su workspace inicial con plan Starter.
    """
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()

    slug = payload.workspace_name.lower().replace(" ", "-")[:50]
    workspace = Workspace(name=payload.workspace_name, slug=f"{slug}-{user.id}")
    db.add(workspace)
    await db.flush()

    membership = Membership(workspace_id=workspace.id, user_id=user.id, role=MemberRole.owner)
    db.add(membership)

    subscription = Subscription(workspace_id=workspace.id, plan_name="starter")
    db.add(subscription)

    # Grupo "Todas" por defecto
    todos_group = ChannelGroup(
        workspace_id=workspace.id,
        name="Todas",
        is_system=True,
    )
    db.add(todos_group)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _user_dict(user),
    }


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": _user_dict(user),
    }


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return _user_dict(current_user)
