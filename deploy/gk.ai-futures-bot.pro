# ==============================================================================
# Nginx Configuration for gk.ai-futures-bot.pro (Subdomain)
# Dedicated isolated server block for Gatekeeper Middleware
# Target upstream: http://127.0.0.1:8001
# ==============================================================================

limit_req_zone $binary_remote_addr zone=gatekeeper_subdomain_limit:10m rate=50r/s;

upstream gatekeeper_upstream_8001 {
    server 127.0.0.1:8001;
    keepalive 32;
}

server {
    listen 80;
    server_name gk.ai-futures-bot.pro;

    # Payload limits
    client_max_body_size 2M;
    client_body_buffer_size 128k;

    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Public Healthcheck
    location /health {
        proxy_pass http://gatekeeper_upstream_8001;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        access_log off;
    }

    # Protected Gatekeeper API
    location / {
        limit_req zone=gatekeeper_subdomain_limit burst=20 nodelay;

        proxy_pass http://gatekeeper_upstream_8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
        proxy_send_timeout 15s;
    }
}
