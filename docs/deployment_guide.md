# Project Gatekeeper – VPS Production Deployment Guide

Dieser Leitfaden beschreibt die schlüsselfertige Inbetriebnahme von **Project Gatekeeper** auf einem Produktions-VPS, auf dem bereits bestehende Dienste laufen (z. B. `https://ai-futures-bot.pro/`).

---

## 1. Koexistenz mit bestehenden Diensten auf dem VPS (ai-futures-bot.pro)

Gatekeeper ist so konzipiert, dass es **vollkommen isoliert und kollisionsfrei** neben existierenden Trading-Bots und Webdiensten arbeitet:

1. **Eigener interner Port (127.0.0.1:8001)**:
   - Während Standard-Bots meist auf Port 8000 laufen, bindet Gatekeeper fest an Port `8001`.
   - Der bestehende Dienst auf Port 8000 oder anderen Ports wird nicht berührt.
2. **Eigenständiger Nginx Server-Block (`gk.ai-futures-bot.pro`)**:
   - Gatekeeper erhält eine eigene Konfigurationsdatei `/etc/nginx/sites-available/gatekeeper.conf`.
   - Die bestehende Konfiguration für `ai-futures-bot.pro` bleibt zu 100 % unberührt.
3. **Rein additiver Setup-Prozess**:
   - `deploy/setup_vps.sh` löscht **keine** existierenden Nginx-Sites und setzt keine UFW-Firewall-Regeln blind zurück.
4. **Lokale Hochgeschwindigkeits-Anbindung für den Bot**:
   - Der auf demselben Server laufende Trading-Bot kann Gatekeeper extrem schnell über den lokalen Loopback ansprechen:
     $$\text{Endpoint}: \texttt{http://127.0.0.1:8001/api/v1/intent/evaluate}$$
     *(Latenz: < 0.2 Millisekunden, kein SSL-Overhead auf dem internen Loopback!)*

---

## 2. DNS-Vorbereitung für die Subdomain

Erstelle bei deinem Domain-Provider für `ai-futures-bot.pro` einen DNS A-Record:

| Typ | Host / Name | Wert / Ziel | TTL |
|---|---|---|---|
| **A** | `gk` | `<VPS-IP-Adresse>` | 300 (oder Auto) |

Damit löst `gk.ai-futures-bot.pro` auf deinen VPS auf.

---

## 3. Installation auf dem VPS

Führe als `root` (oder via `sudo`) auf dem Server folgende Schritte aus:

```bash
# 1. Repository nach /opt/gatekeeper klonen
sudo git clone https://github.com/your-org/gatekeeper.git /opt/gatekeeper
cd /opt/gatekeeper

# 2. Ausführungsrechte für das additive Setup-Script setzen
chmod +x deploy/setup_vps.sh

# 3. Additive Ersteinrichtung starten
sudo ./deploy/setup_vps.sh
```

Das Skript:
- Installiert fehlende Systempakete additiv.
- Richtet einen isolierten Service-User `gatekeeper` und Python `.venv` ein.
- Erzeugt eine geschützte `.env`-Datei auf Port `8001` mit einem generierten 32-Byte API-Key.
- Aktiviert den Systemd-Dienst `gatekeeper.service` und verlinkt `gatekeeper.conf` in Nginx.

---

## 4. Konfiguration anpassen (`/opt/gatekeeper/.env`)

```bash
sudo nano /opt/gatekeeper/.env
```

Beispielkonfiguration:
```ini
# Server-Binding
GATEKEEPER_HOST=127.0.0.1
GATEKEEPER_PORT=8001

# Authentifizierung
GATEKEEPER_API_KEY=gk_dein_geheimer_schluessel_hier

# Solana RPC & Cluster
GATEKEEPER_RPC_URL=https://mainnet.helius-rpc.com/?api-key=DEIN_RPC_KEY
GATEKEEPER_WSS_URL=wss://mainnet.helius-rpc.com/?api-key=DEIN_RPC_KEY
GATEKEEPER_COMMITMENT=confirmed

# Clamping-Puffer
GATEKEEPER_DIRECT_SWAP_CLAMPING_BUFFER=1.12
GATEKEEPER_MULTI_HOP_CLAMPING_BUFFER=1.20
GATEKEEPER_DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS=50000
GATEKEEPER_DEFAULT_JITO_TIP_LAMPORTS=10000

# VPS SQLite Ledger
GATEKEEPER_DATABASE_PATH=/opt/gatekeeper/gatekeeper_audit.db
GATEKEEPER_ENABLE_WAL_MODE=True
GATEKEEPER_LOG_LEVEL=INFO
```

Dienst neu starten:
```bash
sudo systemctl restart gatekeeper
```

---

## 5. Kostenloses SSL-Zertifikat für die Subdomain einrichten

Certbot holt ein separates Zertifikat ausschließlich für die neue Subdomain, ohne das bestehende Zertifikat von `ai-futures-bot.pro` zu überschreiben:

```bash
sudo certbot --nginx -d gk.ai-futures-bot.pro
```

---

## 6. Überprüfung & Funktionsprüfung

```bash
# 1. Systemd Status & Live-Logs prüfen
sudo systemctl status gatekeeper
sudo journalctl -u gatekeeper -f

# 2. Lokalen Health-Check auf Port 8001 testen
curl -i http://127.0.0.1:8001/health

# 3. Externen Zugriff über die Subdomain prüfen
curl -i https://gk.ai-futures-bot.pro/health

# 4. Geschützten Endpunkt mit API-Key testen
curl -i -H "X-Gatekeeper-Key: <DEIN_API_KEY>" https://gk.ai-futures-bot.pro/api/v1/metrics/savings
```
