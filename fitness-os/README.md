# FITNESS BUSINESS OS

Sistema operativo completo para un negocio de productos digitales de fitness.  
Multi-tenant · Ecommerce · CRM · WhatsApp · IA · MercadoLibre · Redes Sociales

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Admin (puerto 3000) | Next.js 14, TypeScript, Tailwind |
| Web / Tienda (puerto 3002) | Next.js 14, TypeScript, Tailwind |
| API (puerto 3001) | Fastify 4, TypeScript |
| Base de datos | PostgreSQL 16 + Prisma 5 |
| Cola de trabajos | BullMQ + Redis 7 |
| IA | OpenRouter (único gateway) |
| Pagos | Mercado Pago |
| Storage | Cloudflare R2 |
| Email | Resend + React Email |
| Auth | Auth.js v5 |
| Deploy | Vercel (frontends) + Railway (API + workers) |

---

## Inicio rápido

```bash
# Instalar dependencias
pnpm install

# Levantar PostgreSQL + Redis
docker compose up -d postgres redis

# Aplicar migración inicial
pnpm --filter @fitness-os/database db:migrate

# Generar cliente Prisma
pnpm --filter @fitness-os/database db:generate

# Seed (tenant + admin user)
pnpm --filter @fitness-os/database run seed

# Iniciar todos los servicios en modo dev
pnpm dev
```

O con Make:
```bash
make setup   # primera vez (install + db-up + migrate + generate)
make dev     # levantar todo
```

---

## Servicios

| Servicio | URL |
|---------|-----|
| Admin Panel | http://localhost:3000 |
| Tienda Pública | http://localhost:3002 |
| API | http://localhost:3001 |
| Health Check | http://localhost:3001/api/v1/health |
| Prisma Studio | http://localhost:5555 |
| Redis Commander | http://localhost:8081 |

---

## Variables de entorno

Copiar `.env.example` a `.env` y completar:

```bash
cp .env.example .env
```

Obligatorias para empezar:
- `DATABASE_URL` — PostgreSQL
- `REDIS_URL` — Redis
- `AUTH_SECRET` — mínimo 32 caracteres

Para IA:
- `OPENROUTER_API_KEY` — único gateway de IA  
  ⚠️ NO incluir `ANTHROPIC_API_KEY` en producción

---

## Estructura

```
fitness-os/
├── apps/
│   ├── admin/          # Panel de administración (Next.js, :3000)
│   ├── web/            # Tienda pública (Next.js, :3002)
│   └── api/            # REST API (Fastify, :3001)
├── packages/
│   ├── database/       # Prisma schema + cliente
│   └── shared/         # Tipos, constantes, utilidades
└── workers/
    ├── fulfillment-worker/  # Entrega de productos digitales
    ├── ai-worker/           # Generación de contenido con IA
    └── sync-worker/         # Sincronización ML / redes sociales
```

---

## Fases de implementación

| # | Fase | Estado |
|---|------|--------|
| 00 | Arquitectura base | ✅ En curso |
| 01 | Core (Auth, Tenants, RBAC) | ⏳ Pendiente |
| 02 | Productos y catálogo | ⏳ Pendiente |
| 03 | Ecommerce (checkout, pagos) | ⏳ Pendiente |
| 04 | Fulfillment digital | ⏳ Pendiente |
| 05 | IA (generación de contenido) | ⏳ Pendiente |
| 06 | CRM (leads, conversaciones) | ⏳ Pendiente |
| 07 | WhatsApp Business | ⏳ Pendiente |
| 08 | MercadoLibre | ⏳ Pendiente |
| 09 | Redes sociales | ⏳ Pendiente |
| 10 | Blog y email marketing | ⏳ Pendiente |
| 11 | Catálogo de 200 productos | ⏳ Pendiente |
| 12 | Programa de afiliados | ⏳ Pendiente |
| 13 | Portal de coaches | ⏳ Pendiente |
| 14 | Internacionalización | ⏳ Pendiente |
| 15 | Hardening y QA | ⏳ Pendiente |

---

## Reglas de IA

- **OpenRouter es el único gateway** — `ANTHROPIC_API_KEY` no existe en producción
- **Generar ≠ publicar** — todo contenido generado queda en `DRAFT` hasta aprobación humana
- **La IA no tiene control autónomo** — no puede cambiar precios, crear/eliminar productos ni publicar
- **Autopilot deshabilitado por defecto** — todos los canales arrancan en modo `MANUAL`

---

## Multi-tenancy

Aislamiento a nivel fila (Row-Level Isolation). Cada entidad tiene `tenantId` y el middleware Fastify lo inyecta automáticamente. La función `prismaWithTenant(tenantId)` fuerza el filtro en todas las queries.

---

## Diseño

Estética dark-first con neon:
- 🟢 Neon verde `#00FF87`
- 🔵 Cyan `#00F5FF`
- 🩷 Pink `#FF2D9C`
- 🟡 Amarillo `#FFE234`
- Tipografías: Barlow Condensed (display) + DM Sans (texto)
