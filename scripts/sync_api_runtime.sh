#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

rm -rf api/server api/utils api/client api/skills
mkdir -p api

cp -R server api/server

mkdir -p api/utils
cp -R utils/* api/utils/

mkdir -p api/client
cp client/__init__.py api/client/__init__.py
mkdir -p api/client/core
cp client/core/__init__.py api/client/core/__init__.py
cp client/core/resume_craft_report.py api/client/core/resume_craft_report.py
cp client/core/resume_match_report.py api/client/core/resume_match_report.py
cp client/core/skill_prefill_policy.py api/client/core/skill_prefill_policy.py

mkdir -p api/skills/CareerForge
cp -R skills/CareerForge/skills api/skills/CareerForge/skills

# Remove local-only and sensitive artifacts from runtime mirror.
rm -f api/server/config.json
rm -rf api/server/instance
rm -rf api/server/uploads

# Strip caches and local compiled artifacts.
find api/server api/utils api/client api/skills -type d -name "__pycache__" -prune -exec rm -rf {} +
find api/server api/utils api/client api/skills -type f -name "*.pyc" -delete
find api/server api/utils api/client api/skills -type f -name "*.pyo" -delete
find api/server api/utils api/client api/skills -type f \( -name "*.db" -o -name "*.db-journal" -o -name "*.db-wal" -o -name "*.sqlite" -o -name "*.sqlite3" \) -delete

echo "api runtime synced (components):"
du -sh api/server api/utils api/client api/skills
