# Pairing dialog
**Feature:** find, pair, connect and disconnect a TV.
- Discovered TV list `#tvList` (from `discover.py`), 6-char pairing code `#code`, Pair / Rescan / Close / Disconnect.
- Manual add: brand select (`android`, `roku`, `samsung`, `lg`) + IP, `#dlgAdd`.
- API: `GET /api/status`, `POST /api/connect`, `/api/pair/start`, `/api/pair/finish`, `/api/disconnect`.
- Last TV is remembered in `data/settings.json` (git-ignored).
