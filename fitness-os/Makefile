# FITNESS BUSINESS OS — Makefile
# Comandos comunes para desarrollo

.PHONY: install dev db-up db-down db-migrate db-reset db-studio clean

## Instalar dependencias
install:
	pnpm install

## Levantar servicios de desarrollo (PostgreSQL + Redis)
db-up:
	docker compose up -d postgres redis
	@echo "⏳ Esperando que PostgreSQL esté listo..."
	@until docker compose exec postgres pg_isready -U fitness -d fitness_dev > /dev/null 2>&1; do sleep 1; done
	@echo "✅ PostgreSQL listo en localhost:5432"
	@echo "✅ Redis listo en localhost:6379"

## Detener servicios
db-down:
	docker compose down

## Aplicar migraciones
db-migrate:
	pnpm --filter @fitness-os/database db:migrate

## Resetear DB (⚠️ elimina todos los datos)
db-reset:
	pnpm --filter @fitness-os/database db:reset

## Abrir Prisma Studio
db-studio:
	pnpm --filter @fitness-os/database studio

## Iniciar todo para desarrollo local
dev: db-up
	pnpm dev

## Limpiar node_modules y builds
clean:
	find . -name "node_modules" -type d -prune -exec rm -rf {} +
	find . -name ".next" -type d -prune -exec rm -rf {} +
	find . -name "dist" -type d -prune -exec rm -rf {} +
	find . -name ".turbo" -type d -prune -exec rm -rf {} +
	@echo "✅ Limpieza completa"

## Generar cliente Prisma
db-generate:
	pnpm --filter @fitness-os/database db:generate

## Seed de desarrollo
seed:
	pnpm --filter @fitness-os/database run seed

## Ver logs de la DB
db-logs:
	docker compose logs -f postgres redis

## Setup inicial completo (primera vez)
setup: install db-up db-migrate db-generate
	@echo ""
	@echo "🚀 Fitness OS listo para desarrollo"
	@echo "   Admin:  http://localhost:3000"
	@echo "   Web:    http://localhost:3002"
	@echo "   API:    http://localhost:3001"
	@echo "   DB:     postgresql://fitness:fitness@localhost:5432/fitness_dev"
	@echo "   Redis:  redis://localhost:6379"
	@echo ""
	@echo "▶  Ejecutar: make dev"
