# setup.ps1 — Configura el entorno de desarrollo de Viral Hub en Windows
# Ejecutar desde: viral-hub/backend/
# Requiere Python 3.11+ y pip

Write-Host "=== Viral Hub — Setup de desarrollo ===" -ForegroundColor Cyan

# 1. Crear entorno virtual
if (-not (Test-Path ".venv")) {
    Write-Host "Creando entorno virtual..." -ForegroundColor Yellow
    python -m venv .venv
}

# 2. Activar entorno virtual
Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
Write-Host "Instalando dependencias Python..." -ForegroundColor Yellow
pip install -r requirements.txt

# 4. Verificar .env
if (-not (Test-Path "..\\.env")) {
    Write-Host "Copiando .env.example → .env" -ForegroundColor Yellow
    Copy-Item "..\\.env.example" "..\\.env"
    Write-Host "IMPORTANTE: Editar .env con las variables de Railway antes de continuar" -ForegroundColor Red
    Write-Host "  DATABASE_URL  → PostgreSQL URL de Railway" -ForegroundColor Yellow
    Write-Host "  DATABASE_SYNC_URL → Igual pero con 'postgresql://' en lugar de 'postgresql+asyncpg://'" -ForegroundColor Yellow
    Write-Host "  REDIS_URL     → Redis URL de Railway" -ForegroundColor Yellow
    Write-Host "  SECRET_KEY    → Generar con: python -c `"import secrets; print(secrets.token_hex(32))`"" -ForegroundColor Yellow
    Write-Host "  JWT_SECRET_KEY → Igual" -ForegroundColor Yellow
    Write-Host "  ENCRYPTION_KEY → Generar con: python -c `"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`"" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Presiná Enter cuando hayas completado el .env..." -ForegroundColor Cyan
    Read-Host
}

# 5. Generar migración y aplicar
Write-Host "Generando migración inicial..." -ForegroundColor Yellow
alembic revision --autogenerate -m "initial_schema"

Write-Host "Aplicando migraciones..." -ForegroundColor Yellow
alembic upgrade head

# 6. Crear admin
Write-Host "Creando usuario admin..." -ForegroundColor Yellow
python scripts/seed_admin.py

Write-Host ""
Write-Host "=== Setup completado ===" -ForegroundColor Green
Write-Host "Para iniciar el servidor: uvicorn app.main:app --reload --port 8000" -ForegroundColor Cyan
