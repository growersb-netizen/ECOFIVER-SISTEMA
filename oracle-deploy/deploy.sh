#!/bin/bash
# ============================================================
# deploy.sh — Corre en el servidor Oracle para levantar stack
# Requiere que setup-server.sh ya haya corrido
# Corre desde ~/eco-stack/oracle-deploy/
# ============================================================
set -e

cd "$(dirname "$0")"

echo "=== Verificando .env files ==="
if grep -q "CAMBIAR" .env.multiagente .env.crm 2>/dev/null; then
  echo "⚠️  ATENCIÓN: hay valores 'CAMBIAR_...' en los .env"
  echo "   Editá .env.multiagente y .env.crm antes de continuar"
  read -p "¿Continuar de todos modos? (s/N) " -n 1 -r
  echo
  [[ $REPLY =~ ^[Ss]$ ]] || exit 1
fi

echo "=== Exportando dominios para Caddyfile ==="
# Dominio principal del multiagente
export MULTIAGENTE_DOMAIN="${MULTIAGENTE_DOMAIN:-api.ecomodulosypiscinas.com.ar}"
# Dominio del CRM
export CRM_DOMAIN="${CRM_DOMAIN:-crm.ecomodulosypiscinas.com.ar}"

echo "  Multiagente: $MULTIAGENTE_DOMAIN"
echo "  CRM:         $CRM_DOMAIN"

# Reescribir el Caddyfile con los dominios reales
envsubst < Caddyfile > Caddyfile.rendered && mv Caddyfile.rendered Caddyfile

echo "=== Build y deploy ==="
docker compose -f docker-compose.yml pull caddy 2>/dev/null || true
docker compose -f docker-compose.yml build --no-cache
docker compose -f docker-compose.yml up -d

echo "=== Estado ==="
docker compose -f docker-compose.yml ps

echo ""
echo "============================================"
echo "✅ Stack desplegado"
echo "Logs: docker compose logs -f"
echo "Reiniciar: docker compose restart"
echo "Detener: docker compose down"
echo "============================================"
