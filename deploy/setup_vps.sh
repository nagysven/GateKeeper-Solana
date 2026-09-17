#!/usr/bin/env bash
# ==============================================================================
# Project Gatekeeper - Additive Non-Destructive VPS Provisioning Script
# Target OS: Ubuntu 22.04 / 24.04 LTS, Debian 12
# Safe for co-existence alongside existing production services (e.g. ai-futures-bot.pro)
# ==============================================================================

set -euo pipefail

echo "========================================================="
echo "   Starting Project Gatekeeper Production Setup (Safe)   "
echo "   Coexistence Mode: Dedicated Port 8001 & Subdomain     "
echo "========================================================="

# 1. Root privilege verification
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root (use sudo)."
   exit 1
fi

# 2. System updates & additive package installation
echo "[1/6] Installing necessary system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    python3-venv \
    python3-pip \
    nginx \
    sqlite3 \
    curl \
    git

# 3. Additive Firewall configuration (Never resets or flushes existing rules)
if command -v ufw >/dev/null 2>&1; then
    echo "[2/6] Additively verifying UFW Firewall rules..."
    ufw allow 22/tcp comment 'SSH' || true
    ufw allow 80/tcp comment 'HTTP' || true
    ufw allow 443/tcp comment 'HTTPS' || true
    echo "Firewall rules confirmed for 22, 80, 443. Existing rules remain untouched."
else
    echo "[2/6] UFW not detected, skipping firewall modification."
fi

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

# Create non-colliding .env with port 8001 if not already present
if [[ ! -f "$APP_DIR/.env" ]]; then
    GENERATED_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
    cat <<EOF > "$APP_DIR/.env"
# Gatekeeper Server Binding
GATEKEEPER_HOST=127.0.0.1
GATEKEEPER_PORT=8001

# Authentication
GATEKEEPER_API_KEY=gk_${GENERATED_KEY}
GATEKEEPER_LOG_LEVEL=INFO

# Storage & Cluster
GATEKEEPER_DATABASE_PATH=/opt/gatekeeper/gatekeeper_audit.db
GATEKEEPER_ENABLE_WAL_MODE=True
GATEKEEPER_RPC_URL=https://api.mainnet-beta.solana.com
GATEKEEPER_WSS_URL=wss://api.mainnet-beta.solana.com
EOF
    chown gatekeeper:gatekeeper "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "Created /opt/gatekeeper/.env on port 8001 with generated master API key."
else
    echo "Existing .env found. Keeping current configuration."
fi

# 6. Additive Systemd & Nginx configuration (No existing sites touched)
echo "[5/6] Deploying Systemd Service & Subdomain Nginx Site..."
if [[ -f "$APP_DIR/deploy/gatekeeper.service" ]]; then
    cp "$APP_DIR/deploy/gatekeeper.service" /etc/systemd/system/gatekeeper.service
    systemctl daemon-reload
    systemctl enable gatekeeper
fi

if [[ -f "$APP_DIR/deploy/nginx_gatekeeper.conf" ]]; then
    cp "$APP_DIR/deploy/nginx_gatekeeper.conf" /etc/nginx/sites-available/gatekeeper.conf
    # Additive symlink: does NOT delete or overwrite existing enabled sites
    ln -sf /etc/nginx/sites-available/gatekeeper.conf /etc/nginx/sites-enabled/gatekeeper.conf
    
    # Test Nginx syntax safely before reloading
    if nginx -t; then
        systemctl reload nginx
        echo "Nginx successfully reloaded with dedicated Gatekeeper subdomain site."
    else
        echo "[WARNING] Nginx syntax test failed. Please inspect /etc/nginx/sites-available/gatekeeper.conf."
    fi
fi

echo "[6/6] Starting Gatekeeper service on port 8001..."
systemctl restart gatekeeper

echo "========================================================="
echo "   Gatekeeper successfully provisioned in coexistence!   "
echo "   Internal Address: 127.0.0.1:8001                      "
echo "   Subdomain:        gk.ai-futures-bot.pro               "
echo "   Gatekeeper Unit:  $(systemctl is-active gatekeeper)   "
echo "========================================================="
