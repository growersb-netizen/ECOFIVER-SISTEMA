#!/bin/bash
# ============================================================
# transfer.sh — Transfiere el proyecto completo al servidor
# Corre desde tu PC local (Windows con Git Bash / WSL)
# Primero hay que bajar la SSH key del Cloud Shell:
#   En Cloud Shell: cat ~/.ssh/eco-server  (copia la clave privada)
#   En local: pegar en C:/Users/PC/.ssh/eco-server
# ============================================================

SERVER_IP="${1:-PONER_IP_AQUI}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/eco-server}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Transfiriendo proyecto a ubuntu@${SERVER_IP}..."
echo "Proyecto: $PROJECT_ROOT"

# Excluye venvs, __pycache__, .git, etc.
rsync -avz --progress \
  --exclude='eco-crm/venv/' \
  --exclude='**/__pycache__/' \
  --exclude='**/*.pyc' \
  --exclude='.git/' \
  --exclude='*.db' \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
  "$PROJECT_ROOT/" \
  "ubuntu@${SERVER_IP}:~/eco-stack/"

echo ""
echo "✅ Transferencia completa"
echo ""
echo "Próximos pasos en el servidor:"
echo "  ssh -i $SSH_KEY ubuntu@${SERVER_IP}"
echo "  cd ~/eco-stack && bash oracle-deploy/setup-server.sh"
echo "  # Editar .env files:"
echo "  nano ~/eco-stack/oracle-deploy/.env.multiagente"
echo "  nano ~/eco-stack/oracle-deploy/.env.crm"
echo "  bash ~/eco-stack/oracle-deploy/deploy.sh"
