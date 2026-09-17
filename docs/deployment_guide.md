# Project Gatekeeper – Schluesselfertiges VPS Rollout-Paket

**Ziel-Server**: `85.215.195.247`  
**Subdomain**: `gk.ai-futures-bot.pro`  
**Bestehender Dienst**: `https://ai-futures-bot.pro/` (bleibt zu 100 % unberuehrt)  
**Interner Port**: `127.0.0.1:8001`  
**Service-User**: `www-data`  

---

## 1. DNS-Voraussetzung pruefen

Stelle sicher, dass der DNS A-Record fuer die Subdomain gesetzt ist:
```bash
# Von lokalem Rechner aus testen:
dig +short gk.ai-futures-bot.pro
# Muss 85.215.195.247 zurueckgeben
```

---

## 2. Nummerierte Rollout-Befehlsliste (Direkt auf dem VPS als root ausfuehren)

### Schritt 1: Projektverzeichnis anlegen und Code bereitstellen

```bash
# Verzeichnis anlegen
mkdir -p /opt/gatekeeper

# Option A: Falls Git-Repo verfuegbar
# git clone <REPO_URL> /opt/gatekeeper

# Option B: Per Rsync von lokalem Entwicklungsrechner uebertragen (vom lokalen PC ausfuehren):
# rsync -avz --exclude '.git' --exclude '.pytest_cache' --exclude '__pycache__' F:/GateKeeper/ root@85.215.195.247:/opt/gatekeeper/
```

---

### Schritt 2: Berechtigungen & Python Virtualenv einrichten

```bash
# Eigentuemer auf www-data setzen
chown -R www-data:www-data /opt/gatekeeper

# Python 3 venv als www-data anlegen
sudo -u www-data python3 -m venv /opt/gatekeeper/.venv

# Pip aktualisieren und Gatekeeper-Paket installieren
sudo -u www-data /opt/gatekeeper/.venv/bin/pip install --upgrade pip setuptools wheel
sudo -u www-data /opt/gatekeeper/.venv/bin/pip install -e /opt/gatekeeper
```

---

### Schritt 3: Produktions-Umgebungsvariablen konfigurieren (`.env`)

Erzeuge die Konfigurationsdatei `/opt/gatekeeper/.env` mit einem sicheren Master-API-Key:

```bash
# Zufalls-API-Key erzeugen und .env schreiben
API_SECRET=$(openssl rand -hex 24)

cat <<EOF > /opt/gatekeeper/.env
GATEKEEPER_HOST=127.0.0.1
GATEKEEPER_PORT=8001
GATEKEEPER_API_KEY=gk_${API_SECRET}
GATEKEEPER_LOG_LEVEL=INFO
GATEKEEPER_DATABASE_PATH=/opt/gatekeeper/gatekeeper_audit.db
GATEKEEPER_ENABLE_WAL_MODE=True
GATEKEEPER_RPC_URL=https://api.mainnet-beta.solana.com
GATEKEEPER_WSS_URL=wss://api.mainnet-beta.solana.com
GATEKEEPER_JUPITER_API_URL=https://quote-api.jup.ag/v6
GATEKEEPER_DIRECT_SWAP_CLAMPING_BUFFER=1.12
GATEKEEPER_MULTI_HOP_CLAMPING_BUFFER=1.20
GATEKEEPER_DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS=50000
GATEKEEPER_DEFAULT_JITO_TIP_LAMPORTS=10000
EOF

# Rechte strikt auf www-data beschraenken
chown www-data:www-data /opt/gatekeeper/.env
chmod 600 /opt/gatekeeper/.env

echo "Gatekeeper API-Key erstellt: gk_${API_SECRET}"
```

---

### Schritt 4: Systemd-Dienst registrieren und starten

```bash
# Service-Unit kopieren
cp /opt/gatekeeper/deploy/gatekeeper.service /etc/systemd/system/gatekeeper.service

# Daemon neu laden und Dienst aktivieren
systemctl daemon-reload
systemctl enable gatekeeper
systemctl restart gatekeeper

# Status pruefen
systemctl status gatekeeper --no-pager
```

---

### Schritt 5: Internen Healthcheck auf Port 8001 testen

```bash
# Direkte Pruefung auf dem internen Loopback
curl -i http://127.0.0.1:8001/health
```
**Erwartete Ausgabe**: `HTTP/1.1 200 OK` mit `{"status":"healthy","service":"gatekeeper","version":"0.1.0"}`.

---

### Schritt 6: Nginx-Subdomain isoliert anbinden (Rein Additiv!)

```bash
# 1. Konfiguration fuer gk.ai-futures-bot.pro in sites-available kopieren
cp /opt/gatekeeper/deploy/gk.ai-futures-bot.pro /etc/nginx/sites-available/gk.ai-futures-bot.pro

# 2. Additive Verlinkung in sites-enabled (beruehrt keine bestehenden Sites!)
ln -sf /etc/nginx/sites-available/gk.ai-futures-bot.pro /etc/nginx/sites-enabled/gk.ai-futures-bot.pro

# 3. ZWINGENDE SYNTAX-PRUEFUNG vor jedem Reload!
nginx -t
```
> [!IMPORTANT]
> Führe den nächsten Befehl nur aus, wenn `nginx -t` mit `syntax is ok` und `test is successful` antwortet!

```bash
# 4. Nginx sicher remappen ohne Ausfallzeit bestehender Verbindungen
systemctl reload nginx
```

---

### Schritt 7: SSL-Zertifikat mit Certbot rein für die Subdomain abrufen

```bash
# Certbot ausschließlich fuer die Subdomain ausfuehren
certbot --nginx -d gk.ai-futures-bot.pro --redirect
```

---

### Schritt 8: End-to-End Verifikation & Smoke-Tests

Führe abschließend diese 3 Prüfbefehle aus:

```bash
# 1. Oeffentlicher HTTPS-Healthcheck (ohne Authentifizierung)
curl -i https://gk.ai-futures-bot.pro/health

# 2. Sicherheitspruefung: Geschuetzter Endpunkt ohne API-Key (Muss 401 Unauthorized liefern)
curl -i https://gk.ai-futures-bot.pro/api/v1/metrics/savings

# 3. Authentifizierte Metriken-Abfrage mit Header
API_KEY=$(grep GATEKEEPER_API_KEY /opt/gatekeeper/.env | cut -d '=' -f2)
curl -i -H "X-Gatekeeper-Key: $API_KEY" https://gk.ai-futures-bot.pro/api/v1/metrics/savings
```

---

## 3. Direkte Anbindung des bestehenden Trading-Bots (`ai-futures-bot.pro`)

Der bereits auf demselben VPS laufende Bot kann Gatekeeper **lokal über Loopback** ohne Latenz oder SSL-Overhead ansprechen:

- **Lokale URL**: `http://127.0.0.1:8001/api/v1/intent/evaluate`
- **Header**: `X-Gatekeeper-Key: <DEIN_API_KEY>`
- **Netzwerk-Latenz**: $<0.15$ ms
