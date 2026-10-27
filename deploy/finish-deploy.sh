#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_DIR="/home/saell/ekursy-mcp"
ENV_FILE="${APP_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

if ! grep -q '^CREDENTIAL_ENCRYPTION_KEY=.' "${ENV_FILE}"; then
  printf '\nCREDENTIAL_ENCRYPTION_KEY=%s\n' "$(openssl rand -hex 32)" >>"${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "Generated the persistent credential encryption key."
fi

read -r -p "GitHub OAuth client ID: " GITHUB_CLIENT_ID
read -r -s -p "GitHub OAuth client secret: " GITHUB_CLIENT_SECRET
echo

if [[ -z "${GITHUB_CLIENT_ID}" || -z "${GITHUB_CLIENT_SECRET}" ]]; then
  echo "Both values are required." >&2
  exit 1
fi

TEMP_ENV="$(mktemp "${APP_DIR}/.env.XXXXXX")"
awk '!/^OAUTH_GITHUB_CLIENT_ID=/ && !/^OAUTH_GITHUB_CLIENT_SECRET=/' \
  "${ENV_FILE}" >"${TEMP_ENV}"
printf 'OAUTH_GITHUB_CLIENT_ID=%s\n' "${GITHUB_CLIENT_ID}" >>"${TEMP_ENV}"
printf 'OAUTH_GITHUB_CLIENT_SECRET=%s\n' "${GITHUB_CLIENT_SECRET}" >>"${TEMP_ENV}"
chmod 600 "${TEMP_ENV}"
mv "${TEMP_ENV}" "${ENV_FILE}"

cd "${APP_DIR}"
docker compose up -d

for _ in {1..30}; do
  CONTAINER_ID="$(docker compose ps -q ekursy-mcp)"
  STATUS="$(docker inspect --format '{{.State.Health.Status}}' "${CONTAINER_ID}" 2>/dev/null || true)"
  if [[ "${STATUS}" == "healthy" ]]; then
    break
  fi
  sleep 1
done

docker compose ps
curl --fail --silent --show-error \
  http://127.0.0.1:6969/.well-known/oauth-protected-resource/mcp
echo
echo "Application is running on loopback. Next run the nginx/Certbot script with sudo."
