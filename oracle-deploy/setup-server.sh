#!/bin/bash
# ============================================================
# setup-server.sh — Bootstrap eco-server en Oracle Cloud ARM
# Corre UNA SOLA VEZ como ubuntu en el servidor nuevo
# ============================================================
set -e

echo "=== [1/6] Actualizando sistema ==="
sudo apt-get update -q && sudo apt-get upgrade -y -q

echo "=== [2/6] Instalando Docker ==="
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# Para aplicar el grupo sin cerrar sesión:
newgrp docker <<'DOCKERGRP'

echo "=== [3/6] Instalando Docker Compose plugin ==="
sudo apt-get install -y docker-compose-plugin
docker compose version

echo "=== [4/6] Instalando herramientas útiles ==="
sudo apt-get install -y git curl wget rsync htop unzip

echo "=== [5/6] Configurando firewall interno ==="
# Oracle tiene su propio Security List, pero habilitamos ufw también
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "=== [6/6] Creando estructura de directorios ==="
mkdir -p ~/eco-stack
mkdir -p ~/eco-stack/oracle-deploy

echo ""
echo "============================================"
echo "✅ Servidor listo para recibir el proyecto"
echo "Próximo paso: transferir los archivos con:"
echo "  rsync -avz -e 'ssh -i ~/.ssh/eco-server' \\"
echo "    ./  ubuntu@<IP>:~/eco-stack/"
echo "============================================"
DOCKERGRP
