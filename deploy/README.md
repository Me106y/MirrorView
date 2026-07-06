# Deploy Baseline

This folder provides a same-domain baseline for Phase A:

- `default.conf`: Serve web static app on `/` and reverse-proxy backend API on `/api/*`
- `docker-compose.prod.yml`: API + Web containers

## Usage

1. Build web assets:
   ```bash
   cd web
   npm install
   npm run build
   ```
2. Start stack from `deploy/`:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

For production HTTPS, add TLS certs and update Nginx config accordingly.
