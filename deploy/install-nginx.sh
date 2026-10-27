#!/usr/bin/env bash
set -euo pipefail

DOMAIN="mk.uni.markrz0.dev"
UPSTREAM="http://127.0.0.1:6969"
CONFIG_PATH="/etc/nginx/conf.d/${DOMAIN}.conf"
CERTBOT_EMAIL="${1:-}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo: sudo bash $0 you@example.com" >&2
  exit 1
fi

if [[ -z "${CERTBOT_EMAIL}" ]]; then
  echo "Usage: sudo bash $0 you@example.com" >&2
  exit 1
fi

cat >"${CONFIG_PATH}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    client_max_body_size 2m;

    location / {
        proxy_pass ${UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

nginx -t
systemctl reload nginx

certbot --nginx \
  --domain "${DOMAIN}" \
  --redirect \
  --non-interactive \
  --agree-tos \
  --email "${CERTBOT_EMAIL}"

nginx -t
systemctl reload nginx
echo "HTTPS proxy installed for https://${DOMAIN}/mcp"
