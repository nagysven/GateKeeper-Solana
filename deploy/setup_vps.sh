#!/usr/bin/env bash
# ==============================================================================
# Project Gatekeeper - Automated VPS Provisioning & Hardening Script
# Target OS: Ubuntu 22.04 / 24.04 LTS, Debian 12
# ==============================================================================

set -euo pipefail

echo "========================================================="
echo "   Starting Project Gatekeeper Production VPS Setup      "
echo "========================================================="

# 1. Root privilege verification
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root (use sudo)."
   exit 1
fi

# 2. System updates & package installation
echo "[1/6] Updating system packages & installing dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    python3-venv \
    python3-pip \
    nginx \
    ufw \
    sqlite3 \
    curl \
    git

# 3. UFW Firewall Hardening
echo "[2/6] Configuring UFW Firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
# Explicitly ensure backend port 8000 is blocked from external interfaces
ufw deny 8000/tcp comment 'Block Direct Middleware Port'
ufw --force enable
echo "Firewall active: SSH(22), HTTP(80), HTTPS(443) enabled."

# 4. Service user & directory creation
echo "[3/6] Setting up service user and application directories..."
if ! id -u gatekeeper >/dev/null 2>&1; then
    useradd -m -s /bin/bash gatekeeper
fi

APP_DIR="/opt/gatekeeper"
mkdir -p "$APP_DIR"
chown -R gatekeeper:gatekeeper "$APP_DIR"

# 5. Python virtualenv & dependencies setup
echo "[4/6] Creating Python virtual environment..."
sudo -u gatekeeper python3 -m venv "$APP_DIR/.venv"
sudo -u gatekeeper "$APP_DIR/.venv/bin/pip" install --upgrade pip setuptools wheel

if [[ -f "$APP_DIR/pyproject.toml" ]]; then
    echo "Installing Gatekeeper dependencies into virtual environment..."
    sudo -u gatekeeper "$APP_DIR/.venv/bin/pip" install -e "$APP_DIR"
fi

# Generate random secure master API key if .env does not exist
if [[ ! -f "$APP_DIR/.env" ]]; then
    GENERATED_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
    cat <<EOF > "$APP_DIR/.env"
GATEKEEPER_API_KEY=gk_${GENERATED_KEY}
GATEKEEPER_LOG_LEVEL=INFO
GATEKEEPER_DATABASE_PATH=/opt/gatekeeper/gatekeeper_audit.db
GATEKEEPER_ENABLE_WAL_MODE=True
GATEKEEPER_RPC_URL=https://api.mainnet-beta.solana.com
GATEKEEPER_WSS_URL=wss://api.mainnet-beta.solana.com
EOF
    chown gatekeeper:gatekeeper "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "Created /opt/gatekeeper/.env with generated master API key."
fi

# 6. Systemd & Nginx configuration
echo "[5/6] Deploying Systemd Service & Nginx Reverse Proxy..."
if [[ -f "$APP_DIR/deploy/gatekeeper.service" ]]; then
    cp "$APP_DIR/deploy/gatekeeper.service" /etc/systemd/system/gatekeeper.service
    systemctl daemon-reload
    systemctl enable gatekeeper
fi

if [[ -f "$APP_DIR/deploy/nginx_gatekeeper.conf" ]]; then
    cp "$APP_DIR/deploy/nginx_gatekeeper.conf" /etc/nginx/sites-available/gatekeeper.conf
    ln -sf /etc/nginx/sites-available/gatekeeper.conf /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl restart nginx
fi

echo "[6/6] Starting Gatekeeper service..."
systemctl restart gatekeeper

echo "========================================================="
echo "   Gatekeeper Middleware successfully provisioned!       "
echo "   Service status: $(systemctl is-active gatekeeper)    "
echo "   Nginx status:   $(systemctl is-active nginx)         "
echo "========================================================="
