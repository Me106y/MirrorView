#!/usr/bin/env bash
set -euo pipefail

# One-click public deployment helper for MirrorView.
# Run this script on your local machine.
#
# Required env vars:
#   SERVER_IP          e.g. 203.0.113.10
#   SERVER_USER        e.g. root or ubuntu
#   DEEPSEEK_API_KEY   your platform key
#
# Optional env vars:
#   DOMAIN             default: mirrorview.dpdns.org
#   BRANCH             default: main
#   REMOTE_DIR         default: /opt/mirrorview
#   SOURCE_MODE        default: local (local | git)
#   REPO_URL           required when SOURCE_MODE=git
#   PLATFORM_PROVIDER  default: deepseek
#   PLATFORM_MODEL     default: deepseek-chat
#   TURNSTILE_SITE_KEY default: ""
#   TURNSTILE_SECRET_KEY default: ""
#   TURNSTILE_ENFORCE  default: false
#   RATE_LIMIT_ENFORCE default: true
#   RATE_LIMIT_REQUESTS default: 30
#   RATE_LIMIT_WINDOW_SECONDS default: 60

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

require_var SERVER_IP
require_var SERVER_USER
require_var DEEPSEEK_API_KEY

DOMAIN="${DOMAIN:-mirrorview.dpdns.org}"
BRANCH="${BRANCH:-main}"
REMOTE_DIR="${REMOTE_DIR:-/opt/mirrorview}"
SOURCE_MODE="${SOURCE_MODE:-local}"
REPO_URL="${REPO_URL:-}"
PLATFORM_PROVIDER="${PLATFORM_PROVIDER:-deepseek}"
PLATFORM_MODEL="${PLATFORM_MODEL:-deepseek-chat}"
TURNSTILE_SITE_KEY="${TURNSTILE_SITE_KEY:-}"
TURNSTILE_SECRET_KEY="${TURNSTILE_SECRET_KEY:-}"
TURNSTILE_ENFORCE="${TURNSTILE_ENFORCE:-false}"
RATE_LIMIT_ENFORCE="${RATE_LIMIT_ENFORCE:-true}"
RATE_LIMIT_REQUESTS="${RATE_LIMIT_REQUESTS:-30}"
RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-60}"

TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cat >"$TMP_ENV" <<EOF
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
PLATFORM_PROVIDER=${PLATFORM_PROVIDER}
PLATFORM_MODEL=${PLATFORM_MODEL}
TURNSTILE_SITE_KEY=${TURNSTILE_SITE_KEY}
TURNSTILE_SECRET_KEY=${TURNSTILE_SECRET_KEY}
TURNSTILE_ENFORCE=${TURNSTILE_ENFORCE}
RATE_LIMIT_ENFORCE=${RATE_LIMIT_ENFORCE}
RATE_LIMIT_REQUESTS=${RATE_LIMIT_REQUESTS}
RATE_LIMIT_WINDOW_SECONDS=${RATE_LIMIT_WINDOW_SECONDS}
EOF

echo "[1/4] Upload environment file to server ..."
scp "$TMP_ENV" "${SERVER_USER}@${SERVER_IP}:/tmp/mirrorview.env"

if [[ "${SOURCE_MODE}" == "local" ]]; then
  echo "[2/4] Upload local source bundle ..."
  TMP_SRC="$(mktemp /tmp/mirrorview-src.XXXXXX.tgz)"
  trap 'rm -f "$TMP_ENV" "$TMP_SRC"' EXIT
  tar -C "${REPO_ROOT}" \
    --exclude='.git' \
    --exclude='.conda' \
    --exclude='node_modules' \
    --exclude='web/node_modules' \
    --exclude='.pycache' \
    --exclude='.pytest_cache' \
    --exclude='log' \
    --exclude='output' \
    --exclude='test-output' \
    -czf "${TMP_SRC}" .
  scp "${TMP_SRC}" "${SERVER_USER}@${SERVER_IP}:/tmp/mirrorview-src.tgz"
elif [[ "${SOURCE_MODE}" == "git" ]]; then
  if [[ -z "${REPO_URL}" ]]; then
    echo "SOURCE_MODE=git requires REPO_URL" >&2
    exit 1
  fi
else
  echo "Invalid SOURCE_MODE: ${SOURCE_MODE} (expected local or git)" >&2
  exit 1
fi

echo "[3/4] Bootstrap server, build web, and start containers ..."
ssh "${SERVER_USER}@${SERVER_IP}" \
  "DOMAIN='${DOMAIN}' BRANCH='${BRANCH}' REMOTE_DIR='${REMOTE_DIR}' REPO_URL='${REPO_URL}' SOURCE_MODE='${SOURCE_MODE}' bash -s" <<'REMOTE'
set -euo pipefail

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl git
fi

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

if ! docker compose version >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y docker-compose-plugin
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi
fi

sudo mkdir -p "${REMOTE_DIR}"
sudo chown -R "${USER}:${USER}" "${REMOTE_DIR}"

if [[ "${SOURCE_MODE}" == "local" ]]; then
  rm -rf "${REMOTE_DIR:?}/"*
  tar -xzf /tmp/mirrorview-src.tgz -C "${REMOTE_DIR}"
else
  if [[ ! -d "${REMOTE_DIR}/.git" ]]; then
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${REMOTE_DIR}"
  else
    cd "${REMOTE_DIR}"
    git fetch origin
    git checkout "${BRANCH}"
    git pull --ff-only origin "${BRANCH}"
  fi
fi

cd "${REMOTE_DIR}"
cp /tmp/mirrorview.env .env

if [[ -f "deploy/nginx/default.conf" ]]; then
  sed -i "s/server_name .*/server_name ${DOMAIN};/" deploy/nginx/default.conf
fi

cd web
npm install
npm run build

cd "${REMOTE_DIR}/deploy"
sudo docker compose -f docker-compose.prod.yml down || true
sudo docker compose -f docker-compose.prod.yml up -d --build

if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 80/tcp || true
  sudo ufw allow 443/tcp || true
fi

echo "SERVER_DEPLOY_OK"
REMOTE

echo "[4/4] Validate origin HTTP ..."
ssh "${SERVER_USER}@${SERVER_IP}" "curl -sS -I http://127.0.0.1 | head -n 1"

cat <<MSG
DNS + HTTPS (Cloudflare) manual step:
1) Add A record:
   Name: ${DOMAIN}
   Type: A
   Content: ${SERVER_IP}
2) Enable proxy (orange cloud).
3) Cloudflare SSL/TLS mode set to Flexible (quickest) or Full (if origin cert is configured).
4) Open: https://${DOMAIN}

Deploy completed.
MSG
