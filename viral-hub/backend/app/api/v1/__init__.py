from fastapi import APIRouter
from app.api.v1 import auth, channels, publications, groups, media, workspace

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(workspace.router)
router.include_router(channels.router)
router.include_router(groups.router)
router.include_router(media.router)
router.include_router(publications.router)
