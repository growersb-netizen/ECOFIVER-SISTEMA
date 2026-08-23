# Viral Hub

> Tu contenido. Todos tus canales. Un solo lugar.

SaaS de distribución masiva de contenido corto para creadores, streamers y operadores de redes de clips.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui |
| Backend | FastAPI (Python) + SQLAlchemy async + Alembic |
| Queue | Celery + Redis (worker por plataforma) |
| Base de datos | PostgreSQL 16 |
| Storage | Cloudflare R2 (S3-compatible) |
| Monitoreo workers | Flower |
| Deploy frontend | Vercel (Next.js nativo) |
| Deploy backend | Railway (FastAPI + Workers + PostgreSQL + Redis) |

## Levantar en desarrollo

### Requisitos
- Docker y Docker Compose
- Node.js 20+
- Python 3.12+

### 1. Variables de entorno
```bash
cp .env.example .env
# Editar .env con tus valores reales
```

### 2. Levantar con Docker Compose
```bash
docker compose up -d db redis
# Esperar healthy, luego:
docker compose up -d
```

### 3. Correr migraciones
```bash
docker compose exec api alembic upgrade head
```

### 4. Accesos locales
| Servicio | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| Docs API | http://localhost:8000/docs |
| Flower (workers) | http://localhost:5555 |

## Deploy en producción

### Frontend → Vercel
1. Conectar repo en vercel.com
2. Root Directory: `frontend`
3. Variables de entorno: `NEXT_PUBLIC_API_URL=https://tu-api.railway.app`

### Backend → Railway
1. Nuevo proyecto en railway.app
2. Agregar servicios: PostgreSQL, Redis (desde templates)
3. Agregar servicio desde repo → root: `backend/`
4. Para cada worker, crear un servicio adicional con start command:
   `celery -A app.workers.celery_app worker -Q instagram -c 4`
5. Configurar variables de entorno (ver `.env.example`)

## Estructura del proyecto

```
viral-hub/
├── backend/
│   ├── app/
│   │   ├── main.py              # Entrada FastAPI
│   │   ├── core/                # Config, DB, seguridad
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── api/v1/             # Rutas REST
│   │   ├── providers/           # Adapters por plataforma
│   │   │   ├── base.py          # SocialProvider abstracto
│   │   │   ├── instagram.py
│   │   │   ├── tiktok.py
│   │   │   ├── youtube.py
│   │   │   └── facebook.py
│   │   ├── workers/             # Celery tasks
│   │   └── services/            # Lógica de negocio
│   ├── alembic/                 # Migraciones DB
│   └── requirements.txt
├── frontend/
│   └── src/app/
│       ├── (auth)/              # Login / Registro
│       └── (dashboard)/         # App principal
├── docker-compose.yml
└── .env.example
```

## Plataformas soportadas (MVP)

| Red | Capacidad |
|---|---|
| Instagram | Reels (Direct Post via Meta Graph API) |
| Facebook | Video en páginas |
| TikTok | Video corto (Content Posting API) |
| YouTube | YouTube Shorts (Data API v3) |

## Arquitectura de publicación

```
Usuario → POST /publications
         ↓
         PublicationService
         ↓
         Crea N PublicationJobs (uno por canal destino)
         ↓
         Envía a Celery queue por plataforma
         ↓
         Worker[instagram|tiktok|youtube|facebook]
         ↓
         API oficial de la plataforma
         ↓
         Actualiza estado del job (published/failed/retrying)
```

## Guía de desarrollo

- Agregar una nueva red social → implementar `SocialProvider` en `backend/app/providers/`
- Los límites de plan **no se hardcodean** → se leen de `workspace.plan_config` (JSON)
- Todo job es **idempotente** — verificar antes de reintentar
- Secretos y tokens OAuth → **siempre cifrados** con Fernet
