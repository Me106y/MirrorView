# MirrorView Web

Phase A Week 1 web MVP for MirrorView.

## Run

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
npm run preview
```

## Notes

- Uses unified model settings (platform / BYOK).
- Consent gate is stored locally in browser storage.
- High-cost requests send `runtime` and `turnstile_token` payload fields.
