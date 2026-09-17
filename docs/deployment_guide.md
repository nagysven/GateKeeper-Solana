# Project Gatekeeper – VPS Production Deployment Guide

Dieser Leitfaden beschreibt die schlüsselfertige Inbetriebnahme von **Project Gatekeeper** auf einem frischen VPS (Ubuntu 22.04 / 24.04 LTS oder Debian 12).

---

## 1. Voraussetzungen

- Frischer VPS mit Root-Zugriff (z. B. Hetzner, DigitalOcean, OVH oder AWS EC2).
- Mindestens 1 vCPU, 2 GB RAM, 20 GB NVMe-Speicher.
- Eine Domain oder Subdomain (optional, für SSL via Let's Encrypt).

---

## 2. Schnelle Ersteinrichtung via Script (Empfohlen)

Führe als `root` auf dem VPS folgende Schritte aus:

```bash
# 1. Repository nach /opt/gatekeeper klonen
sudo git clone https://github.com/your-org/gatekeeper.git /opt/gatekeeper
cd /opt/gatekeeper

# 2. Ausführungsrechte für das Setup-Script setzen
chmod +x deploy/setup_vps.sh

# 3. Setup ausführen (konfiguriert UFW Firewall, Virtualenv, Nginx & Systemd)
sudo ./deploy/setup_vps.sh
```

Das Skript generiert automatisch eine sichere `.env`-Datei unter `/opt/gatekeeper/.env` mit einem zufälligen Master-API-Key.

---

## 3. Konfiguration anpassen (`.env`)

Öffne die Konfigurationsdatei, um deine eigene RPC-URL und den API-Key einzusehen oder anzupassen:

```bash
sudo nano /opt/gatekeeper/.env
```

Beispielkonfiguration:
```ini
# Authentifizierung
GATEKEEPER_API_KEY=gk_7f8c9b3a4e5d6f1a2b3c4d5e6f7a8b9c

# RPC & Cluster (Private Nodes wie Helius, QuickNode oder Triton empfohlen)
GATEKEEPER_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_RPC_KEY
GATEKEEPER_WSS_URL=wss://mainnet.helius-rpc.com/?api-key=YOUR_RPC_KEY
GATEKEEPER_COMMITMENT=confirmed

# Clamping-Puffer & Limits
GATEKEEPER_DIRECT_SWAP_CLAMPING_BUFFER=1.12
GATEKEEPER_MULTI_HOP_CLAMPING_BUFFER=1.20
GATEKEEPER_DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS=50000
GATEKEEPER_DEFAULT_JITO_TIP_LAMPORTS=10000

# VPS Speicher
GATEKEEPER_DATABASE_PATH=/opt/gatekeeper/gatekeeper_audit.db
GATEKEEPER_ENABLE_WAL_MODE=True
GATEKEEPER_LOG_LEVEL=INFO
```

Nach Änderungen den Service neu starten:
```bash
sudo systemctl restart gatekeeper
```

---

## 4. Service-Management & Live-Logs

```bash
# Status der Gatekeeper Middleware prüfen
sudo systemctl status gatekeeper

# Live-Logs der Intent-Evaluierung in Echtzeit verfolgen
sudo journalctl -u gatekeeper -f

# Nginx Logs prüfen
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## 5. Optional: Kostenloses SSL-Zertifikat mit Certbot einrichten

Falls eine Domain auf den VPS zeigt:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d gatekeeper.deine-domain.com
```
Certbot konfiguriert die HTTPS-Weiterleitung und SSL-Zertifikats-Erneuerung automatisch.

---

## 6. Verifikation der Endpunkte von außen

```bash
# 1. Öffentlichen Health-Check testen (benötigt keinen API-Key)
curl -i http://<DEINE-VPS-IP>/health

# 2. Geschützten Endpunkt ohne Key aufrufen (muss HTTP 401 liefern)
curl -i http://<DEINE-VPS-IP>/api/v1/metrics/savings

# 3. Geschützten Endpunkt mit gültigem Key aufrufen (liefert JSON Metriken)
curl -i -H "X-Gatekeeper-Key: <DEIN_API_KEY>" http://<DEINE-VPS-IP>/api/v1/metrics/savings
```
