#!/usr/bin/env bash
set -euo pipefail

# Prepare Python runtime mirror for the Vercel API function.
rm -rf api/_runtime
mkdir -p api/_runtime

cp -R server api/_runtime/server

mkdir -p api/_runtime/utils
cp -R utils/* api/_runtime/utils/

mkdir -p api/_runtime/client
cp client/__init__.py api/_runtime/client/__init__.py
cp -R client/core api/_runtime/client/core

mkdir -p api/_runtime/skills/CareerForge
cp -R skills/CareerForge/skills api/_runtime/skills/CareerForge/skills

# Build frontend static output.
cd web
npm ci
npm run build
