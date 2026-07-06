#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

rm -rf api/_runtime
mkdir -p api/_runtime

cp -R server api/_runtime/server

mkdir -p api/_runtime/utils
cp -R utils/* api/_runtime/utils/

mkdir -p api/_runtime/client
cp client/__init__.py api/_runtime/client/__init__.py
mkdir -p api/_runtime/client/core
cp client/core/__init__.py api/_runtime/client/core/__init__.py
cp client/core/resume_craft_report.py api/_runtime/client/core/resume_craft_report.py
cp client/core/resume_match_report.py api/_runtime/client/core/resume_match_report.py
cp client/core/skill_prefill_policy.py api/_runtime/client/core/skill_prefill_policy.py

mkdir -p api/_runtime/skills/CareerForge
cp -R skills/CareerForge/skills api/_runtime/skills/CareerForge/skills

# Remove local-only and sensitive artifacts from runtime mirror.
rm -f api/_runtime/server/config.json
rm -rf api/_runtime/server/instance
rm -rf api/_runtime/server/uploads

# Strip caches and local compiled artifacts.
find api/_runtime -type d -name "__pycache__" -prune -exec rm -rf {} +
find api/_runtime -type f -name "*.pyc" -delete
find api/_runtime -type f -name "*.pyo" -delete
find api/_runtime -type f \( -name "*.db" -o -name "*.db-journal" -o -name "*.db-wal" -o -name "*.sqlite" -o -name "*.sqlite3" \) -delete

echo "api runtime synced: $(du -sh api/_runtime | awk '{print $1}')"
